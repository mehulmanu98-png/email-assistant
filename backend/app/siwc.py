"""Independent Sign in with ChatGPT open-source client primitives.

SIWC credentials are deliberately stored only in a local file owned by the runtime.
This module must not write them to PostgreSQL, Secret Manager, environment files,
browser storage, logs, or source control.
"""
from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import httpx
from jose import JWTError, jwt

OPENAI_ISSUER = "https://auth.openai.com"
OPENAI_DISCOVERY_URL = OPENAI_ISSUER + "/.well-known/openid-configuration"
OPENAI_RESOURCE = "https://api.openai.com/v1"
OPENAI_TOKEN_FALLBACK = OPENAI_ISSUER + "/api/accounts/oauth/token"
OPENAI_RESPONSES_URL = OPENAI_RESOURCE + "/responses"
OPENAI_MODELS_URL = OPENAI_RESOURCE + "/models"
REQUIRED_PLAN_SCOPE = "chatgpt.tokens.use.direct"
ALLOWED_ID_TOKEN_ALGORITHMS = {"RS256", "ES256"}


class SIWCError(RuntimeError):
    """Base exception for the local SIWC runtime."""


class SIWCCredentialsMissing(SIWCError):
    pass


class SIWCPlanUsageDisabled(SIWCError):
    pass


class SIWCReauthenticationRequired(SIWCError):
    pass


class SIWCRequestError(SIWCError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id


class SIWCUsageLimitReached(SIWCRequestError):
    pass


class SIWCPlanUsageUnavailable(SIWCRequestError):
    pass


def default_credentials_path() -> Path:
    configured = os.environ.get("SIWC_CREDENTIALS_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".config" / "email-assistant" / "siwc" / "credentials.json"


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.expanduser()
    _private_directory(path.parent)
    fd, temp_name = tempfile.mkstemp(prefix=".siwc-", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        temp_path.unlink(missing_ok=True)
        raise


def save_credentials(path: str | Path, payload: dict[str, Any]) -> Path:
    """Save one protected credential record atomically with owner-only permissions."""
    required = {
        "issuer", "subject", "client_id", "ext_agent_host_id",
        "id_token", "access_token", "refresh_token", "scopes",
    }
    missing = sorted(key for key in required if not payload.get(key))
    if missing:
        raise ValueError("Credential record is missing required fields: " + ", ".join(missing))
    target = Path(path).expanduser()
    _atomic_write_json(target, payload)
    return target


def load_credentials(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path else default_credentials_path()
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
        if mode & 0o077:
            raise SIWCError("SIWC credential file permissions are too broad; require mode 0600.")
        with target.open("r", encoding="utf-8") as stream:
            record = json.load(stream)
    except FileNotFoundError as exc:
        raise SIWCCredentialsMissing(
            "ChatGPT plan credentials are not installed on this runtime."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SIWCError("The local SIWC credential file is not valid JSON.") from exc
    if not isinstance(record, dict):
        raise SIWCError("The local SIWC credential record has an invalid structure.")
    if not record.get("client_id") or not record.get("access_token"):
        raise SIWCError("The local SIWC credential record is incomplete.")
    return record


@contextmanager
def _credential_lock(path: Path) -> Iterator[None]:
    _private_directory(path.parent)
    lock_path = path.with_name(path.name + ".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "r+") as lock_stream:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _scope_set(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(item) for item in value}
    if isinstance(value, str):
        return {item for item in value.split() if item}
    return set()


def verify_id_token(
    id_token: str,
    *,
    client_id: str,
    nonce: str,
    issuer: str = OPENAI_ISSUER,
    discovery: dict[str, Any] | None = None,
    jwks: dict[str, Any] | None = None,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Validate signature, issuer, audience, expiry and nonce for an SIWC ID token."""
    if not id_token or not client_id or not nonce:
        raise ValueError("ID token, issued client ID and expected nonce are required.")
    client = http_client or httpx.Client(timeout=20)
    owns_client = http_client is None
    try:
        if discovery is None:
            response = client.get(OPENAI_DISCOVERY_URL)
            response.raise_for_status()
            discovery = response.json()
        discovered_issuer = str(discovery.get("issuer") or "")
        if discovered_issuer != issuer:
            raise SIWCError("OpenAI OIDC discovery returned an unexpected issuer.")
        jwks_uri = discovery.get("jwks_uri")
        if not jwks_uri:
            raise SIWCError("OpenAI OIDC discovery did not provide a JWKS URI.")
        if jwks is None:
            response = client.get(str(jwks_uri))
            response.raise_for_status()
            jwks = response.json()

        header = jwt.get_unverified_header(id_token)
        algorithm = str(header.get("alg") or "")
        if algorithm not in ALLOWED_ID_TOKEN_ALGORITHMS:
            raise SIWCError("The ID token uses an unsupported signing algorithm.")
        kid = header.get("kid")
        matches = [
            key for key in (jwks.get("keys") or [])
            if key.get("kid") == kid and (not key.get("alg") or key.get("alg") == algorithm)
        ]
        if len(matches) != 1:
            raise SIWCError("The ID token signing key could not be uniquely identified.")
        claims = jwt.decode(
            id_token,
            matches[0],
            algorithms=[algorithm],
            audience=client_id,
            issuer=issuer,
            options={"verify_at_hash": False},
        )
        actual_nonce = str(claims.get("nonce") or "")
        if not actual_nonce or not __import__("hmac").compare_digest(actual_nonce, nonce):
            raise SIWCError("The ID token nonce did not match this sign-in attempt.")
        if not claims.get("sub"):
            raise SIWCError("The ID token has no validated subject.")
        return claims
    except JWTError as exc:
        raise SIWCError("The OpenAI ID token could not be validated.") from exc
    finally:
        if owns_client:
            client.close()


def _response_error(response: httpx.Response) -> SIWCRequestError:
    error_code = None
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                error_code = error.get("code")
            if not error_code and isinstance(payload.get("code"), str):
                error_code = payload.get("code")
    except ValueError:
        pass
    request_id = response.headers.get("x-request-id")
    message = f"ChatGPT plan request failed with HTTP {response.status_code}."
    if response.status_code == 429 or error_code == "subscription_sharing_usage_limit_exceeded":
        return SIWCUsageLimitReached(
            message + " Pause plan-usage requests and check ChatGPT Settings > Usage.",
            status_code=response.status_code,
            error_code=str(error_code) if error_code else None,
            request_id=request_id,
        )
    if error_code in {"subscription_sharing_usage_unavailable", "insufficient_scope"}:
        return SIWCPlanUsageUnavailable(
            message + " ChatGPT plan usage is unavailable for this session; reconnect or review account access.",
            status_code=response.status_code,
            error_code=str(error_code),
            request_id=request_id,
        )
    return SIWCRequestError(
        message,
        status_code=response.status_code,
        error_code=str(error_code) if error_code else None,
        request_id=request_id,
    )


def get_access_token(
    path: str | Path | None = None,
    *,
    now: float | None = None,
    http_client: httpx.Client | None = None,
) -> str:
    """Return a valid plan-use access token, serializing and persisting token refresh."""
    target = Path(path).expanduser() if path else default_credentials_path()
    clock = time.time() if now is None else float(now)
    client = http_client or httpx.Client(timeout=30)
    owns_client = http_client is None
    try:
        with _credential_lock(target):
            record = load_credentials(target)
            scopes = _scope_set(record.get("scopes"))
            if REQUIRED_PLAN_SCOPE not in scopes:
                raise SIWCPlanUsageDisabled(
                    "ChatGPT plan usage was not granted during sign-in. Reconnect and enable plan use."
                )
            try:
                expires_at = float(record.get("expires_at") or 0)
            except (TypeError, ValueError):
                expires_at = 0
            if record.get("access_token") and expires_at > clock + 120:
                return str(record["access_token"])

            refresh_token = str(record.get("refresh_token") or "")
            if not refresh_token:
                raise SIWCReauthenticationRequired("The ChatGPT session has no refresh token. Sign in again.")
            discovery = record.get("token_endpoint")
            if not discovery:
                try:
                    discovery_doc = client.get(OPENAI_DISCOVERY_URL)
                    discovery_doc.raise_for_status()
                    discovery = discovery_doc.json().get("token_endpoint")
                except httpx.HTTPError as exc:
                    raise SIWCRequestError("OpenAI token discovery is temporarily unavailable.") from exc
            token_endpoint = str(discovery or OPENAI_TOKEN_FALLBACK)
            response = client.post(
                token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "client_id": str(record["client_id"]),
                    "refresh_token": refresh_token,
                    "resource": OPENAI_RESOURCE,
                },
                timeout=30,
            )
            if response.status_code >= 400:
                try:
                    details = response.json()
                except ValueError:
                    details = {}
                code = str(details.get("error") or "") if isinstance(details, dict) else ""
                if code in {"invalid_grant", "invalid_refresh_token", "token_expired",
                            "refresh_token_expired", "refresh_token_invalidated",
                            "refresh_token_reused"}:
                    target.unlink(missing_ok=True)
                    raise SIWCReauthenticationRequired(
                        "The saved ChatGPT session is no longer renewable. Complete Sign in with ChatGPT again."
                    )
                raise _response_error(response)

            token_data = response.json()
            new_access = token_data.get("access_token")
            new_refresh = token_data.get("refresh_token")
            if not new_access or not new_refresh:
                raise SIWCError("OpenAI refresh response did not include rotated access and refresh tokens.")
            try:
                expires_in = int(token_data.get("expires_in") or 0)
            except (TypeError, ValueError):
                expires_in = 0
            if expires_in <= 0:
                raise SIWCError("OpenAI refresh response did not include a valid token lifetime.")
            refreshed_scopes = _scope_set(token_data.get("scope")) or scopes
            record.update({
                "access_token": str(new_access),
                "refresh_token": str(new_refresh),
                "expires_in": expires_in,
                "expires_at": clock + expires_in,
                "scopes": sorted(refreshed_scopes),
                "saved_at": clock,
            })
            if token_data.get("id_token"):
                record["id_token"] = str(token_data["id_token"])
            _atomic_write_json(target, record)
            if REQUIRED_PLAN_SCOPE not in refreshed_scopes:
                raise SIWCPlanUsageDisabled(
                    "The refreshed ChatGPT session no longer grants plan usage. AI work is paused."
                )
            return str(record["access_token"])
    finally:
        if owns_client:
            client.close()


def revoke_credentials(
    path: str | Path | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> bool:
    """Remove local credentials and attempt remote refresh-token revocation.

    Returns True only when OpenAI confirms remote revocation. An explicit local
    disconnect always removes the VM's local credential file, even if the
    remote revocation endpoint cannot be reached; False means remote revocation
    was not confirmed and must be disclosed to the user.
    """
    target = Path(path).expanduser() if path else default_credentials_path()
    client = http_client or httpx.Client(timeout=20)
    owns_client = http_client is None
    remote_revoked = False
    try:
        with _credential_lock(target):
            try:
                record = load_credentials(target)
            except SIWCCredentialsMissing:
                return True
            refresh_token = str(record.get("refresh_token") or "")
            if refresh_token:
                try:
                    discovery = client.get(OPENAI_DISCOVERY_URL)
                    discovery.raise_for_status()
                    endpoint = discovery.json().get("revocation_endpoint")
                    if endpoint:
                        response = client.post(
                            str(endpoint),
                            data={
                                "token": refresh_token,
                                "token_type_hint": "refresh_token",
                                "client_id": str(record.get("client_id") or ""),
                            },
                            timeout=20,
                        )
                        remote_revoked = response.status_code == 200
                except httpx.HTTPError:
                    remote_revoked = False
            target.unlink(missing_ok=True)
            return remote_revoked
    finally:
        if owns_client:
            client.close()


def list_models(
    path: str | Path | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> list[dict[str, str]]:
    client = http_client or httpx.Client(timeout=30)
    owns_client = http_client is None
    try:
        access_token = get_access_token(path, http_client=client)
        response = client.get(
            OPENAI_MODELS_URL,
            headers={"Authorization": "Bearer " + access_token},
            timeout=30,
        )
        if response.status_code >= 400:
            raise _response_error(response)
        payload = response.json()
        return [
            {"slug": str(item["slug"]), "display_name": str(item.get("display_name") or item["slug"])}
            for item in payload.get("models", [])
            if isinstance(item, dict) and item.get("slug") and item.get("visibility") == "list"
        ]
    finally:
        if owns_client:
            client.close()


def create_response(
    prompt: str,
    *,
    model: str,
    path: str | Path | None = None,
    http_client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Run one non-persisted streamed Responses request and await response.completed."""
    if not prompt.strip():
        raise ValueError("A non-empty prompt is required.")
    if not model.strip():
        raise ValueError("Select a model from the connected ChatGPT account.")
    client = http_client or httpx.Client(timeout=httpx.Timeout(180, connect=30))
    owns_client = http_client is None
    try:
        access_token = get_access_token(path, http_client=client)
        with client.stream(
            "POST",
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": "Bearer " + access_token,
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": [{"role": "user", "content": prompt}],
                "store": False,
                "stream": True,
            },
            timeout=httpx.Timeout(180, connect=30),
        ) as response:
            if response.status_code >= 400:
                body = response.read()
                try:
                    parsed = json.loads(body.decode("utf-8"))
                    error = parsed.get("error", {}) if isinstance(parsed, dict) else {}
                    code = error.get("code") if isinstance(error, dict) else None
                except (ValueError, UnicodeDecodeError):
                    code = None
                request_id = response.headers.get("x-request-id")
                if response.status_code == 429 or code == "subscription_sharing_usage_limit_exceeded":
                    raise SIWCUsageLimitReached(
                        "ChatGPT plan usage limit reached. Pause AI work and check ChatGPT Settings > Usage.",
                        status_code=response.status_code,
                        error_code=str(code) if code else None,
                        request_id=request_id,
                    )
                raise SIWCRequestError(
                    f"ChatGPT plan request failed with HTTP {response.status_code}.",
                    status_code=response.status_code,
                    error_code=str(code) if code else None,
                    request_id=request_id,
                )

            pieces: list[str] = []
            response_id = None
            completed = False
            failure_code = None
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                event_type = event.get("type")
                if event_type == "response.output_text.delta":
                    pieces.append(str(event.get("delta") or ""))
                elif event_type == "response.failed":
                    result = event.get("response") or {}
                    error = result.get("error") or {}
                    failure_code = str(error.get("code") or "response_failed")
                    if failure_code == "subscription_sharing_usage_limit_exceeded":
                        raise SIWCUsageLimitReached(
                            "ChatGPT plan usage limit reached. Pause AI work and check ChatGPT Settings > Usage.",
                            request_id=response.headers.get("x-request-id"),
                            error_code=failure_code,
                        )
                    if failure_code == "subscription_sharing_usage_unavailable":
                        raise SIWCPlanUsageUnavailable(
                            "ChatGPT plan usage is unavailable for this session. AI work is paused.",
                            request_id=response.headers.get("x-request-id"),
                            error_code=failure_code,
                        )
                    raise SIWCRequestError("ChatGPT response failed: " + failure_code,
                                           request_id=response.headers.get("x-request-id"),
                                           error_code=failure_code)
                elif event_type == "response.incomplete":
                    raise SIWCRequestError("ChatGPT response ended incomplete.",
                                           request_id=response.headers.get("x-request-id"),
                                           error_code="response_incomplete")
                elif event_type == "response.completed":
                    result = event.get("response") or {}
                    response_id = result.get("id")
                    completed = True
                    break

            if not completed:
                raise SIWCRequestError("ChatGPT stream ended without response.completed.",
                                       request_id=response.headers.get("x-request-id"),
                                       error_code="stream_incomplete")
            text = "".join(pieces).strip()
            if not text:
                raise SIWCRequestError("ChatGPT completed without output text.",
                                       request_id=response.headers.get("x-request-id"),
                                       error_code="empty_output")
            return {"text": text, "response_id": response_id, "completed": True}
    finally:
        if owns_client:
            client.close()
