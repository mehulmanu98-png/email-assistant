#!/usr/bin/env python3
"""Complete Sign in with ChatGPT OAuth locally and save a protected credential file.

Run on the user's Mac. The host ID must belong to the target self-hosted VM and
must have been created there first. This script never prints token values.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import secrets
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.siwc import (  # noqa: E402
    OPENAI_DISCOVERY_URL,
    OPENAI_ISSUER,
    OPENAI_RESOURCE,
    REQUIRED_PLAN_SCOPE,
    save_credentials,
    verify_id_token,
)

IDENTITY_SCOPES = "openid profile email"
PLAN_SCOPES = "offline_access resource.invoke chatgpt.tokens.use.direct"
CALLBACK_PATH = "/auth/callback"


class CallbackError(RuntimeError):
    pass


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _callback_server(port: int, expected_state: str) -> tuple[http.server.HTTPServer, dict]:
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_error(404)
                return
            query = parse_qs(parsed.query, keep_blank_values=True)
            state = (query.get("state") or [""])[0]
            if not state or not secrets.compare_digest(state, expected_state):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Sign-in state validation failed. Return to the terminal.")
                return
            result.update({key: values[0] for key, values in query.items() if values})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(
                b"<!doctype html><title>Email Assistant</title>"
                b"<p>Sign-in response received. You can return to the Email Assistant terminal.</p>"
            )

        def log_message(self, fmt: str, *args) -> None:
            # Do not log callback query values or authorization codes.
            return

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    return server, result


def _wait_for_callback(server: http.server.HTTPServer, result: dict, timeout_seconds: int = 600) -> dict:
    deadline = time.monotonic() + timeout_seconds
    try:
        while not result and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if not result:
        raise CallbackError("Timed out waiting for the local OAuth callback.")
    if result.get("error"):
        raise CallbackError("Sign in was not completed: " + str(result["error"]))
    if not result.get("code"):
        raise CallbackError("The OAuth callback did not include an authorization code.")
    return result


def _existing_registration(path: Path, target_host_id: str) -> dict | None:
    if not path.exists():
        return None
    try:
        from app.siwc import load_credentials
        record = load_credentials(path)
    except Exception as exc:
        raise CallbackError("An existing SIWC file could not be safely read; inspect it locally before proceeding.") from exc
    if record.get("ext_agent_host_id") != target_host_id:
        raise CallbackError("The existing credential file belongs to a different host ID.")
    if not record.get("client_id") or not record.get("id_token"):
        raise CallbackError("The existing credential file cannot be used for account reauthorization.")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign in with ChatGPT for the Email Assistant self-hosted AI VM.")
    parser.add_argument("--host-id", required=True,
                        help="Stable host ID created on the target VM (copy only this non-secret ID to the Mac).")
    parser.add_argument("--output", default=str(Path.home() / ".config/email-assistant/siwc/credentials.json"),
                        help="Protected credential file path on this Mac.")
    parser.add_argument("--port", type=int, default=1455, help="Loopback callback port (default: 1455).")
    parser.add_argument("--new-registration", action="store_true",
                        help="Register a new SIWC client rather than reauthorising an existing credential file.")
    args = parser.parse_args()

    if not args.host_id.startswith(("urn:uuid:", "urn:ietf:params:oauth:jwk-thumbprint:", "did:key:")):
        parser.error("--host-id must be a supported opaque host ID URI.")
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535.")

    output_path = Path(args.output).expanduser()
    existing = None if args.new_registration else _existing_registration(output_path, args.host_id)

    with httpx.Client(timeout=30) as client:
        discovery_response = client.get(OPENAI_DISCOVERY_URL)
        discovery_response.raise_for_status()
        discovery = discovery_response.json()
        if discovery.get("issuer") != OPENAI_ISSUER:
            raise CallbackError("OpenAI OIDC discovery returned an unexpected issuer.")
        auth_endpoint = discovery.get("authorization_endpoint")
        token_endpoint = discovery.get("token_endpoint")
        jwks_uri = discovery.get("jwks_uri")
        if not auth_endpoint or not token_endpoint or not jwks_uri:
            raise CallbackError("OpenAI OIDC discovery is missing required endpoints.")

        state = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(48)
        verifier, challenge = _pkce_pair()
        redirect_uri = f"http://127.0.0.1:{args.port}{CALLBACK_PATH}"
        client_id = str(existing["client_id"]) if existing else "dynamic_agent_client"

        params = {
            "client_id": client_id,
            "ext_agent_host_id": args.host_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": IDENTITY_SCOPES + " " + PLAN_SCOPES,
            "resource": OPENAI_RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        if existing:
            params["id_token_hint"] = str(existing["id_token"])
            if existing.get("email"):
                params["login_hint"] = str(existing["email"])
        else:
            params["agent_name_hint"] = "Email Assistant"

        server, result = _callback_server(args.port, state)
        authorization_url = str(auth_endpoint) + "?" + urlencode(params)
        print("A local sign-in listener is ready on 127.0.0.1.")
        print("Complete the OpenAI sign-in and review the requested permissions in your browser.")
        webbrowser.open(authorization_url, new=1, autoraise=True)
        callback = _wait_for_callback(server, result)

        returned_client_id = callback.get("client_id")
        if existing:
            if returned_client_id and returned_client_id != client_id:
                raise CallbackError("OpenAI returned a different client ID; the saved registration was not changed.")
        else:
            if not returned_client_id or returned_client_id == "dynamic_agent_client":
                raise CallbackError("New registration did not return an issued client ID.")
            client_id = str(returned_client_id)

        token_response = client.post(
            str(token_endpoint),
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": str(callback["code"]),
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
                "resource": OPENAI_RESOURCE,
            },
        )
        if token_response.status_code != 200:
            raise CallbackError(
                f"OpenAI token exchange failed with HTTP {token_response.status_code}. "
                "The authorization code is single-use; start a fresh sign-in."
            )
        token_data = token_response.json()
        if token_data.get("client_id") and token_data["client_id"] != client_id:
            raise CallbackError("Token response client ID did not match the selected registration.")
        id_token = token_data.get("id_token")
        if not id_token:
            raise CallbackError("OpenAI token response did not include an ID token.")
        jwks_response = client.get(str(jwks_uri))
        jwks_response.raise_for_status()
        claims = verify_id_token(
            str(id_token), client_id=client_id, nonce=nonce,
            issuer=OPENAI_ISSUER, discovery=discovery,
            jwks=jwks_response.json(), http_client=client,
        )
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = int(token_data.get("expires_in") or 0)
        if not access_token or not refresh_token or expires_in <= 0:
            raise CallbackError("OpenAI did not return a renewable token set. No credentials were saved.")
        scope_value = str(token_data.get("scope") or "")
        scopes = sorted(set(scope_value.split()))
        saved_at = time.time()
        credential = {
            "email": claims.get("email") if claims.get("email_verified") else None,
            "issuer": OPENAI_ISSUER,
            "subject": str(claims["sub"]),
            "client_id": client_id,
            "ext_agent_host_id": args.host_id,
            "id_token": str(id_token),
            "access_token": str(access_token),
            "refresh_token": str(refresh_token),
            "token_type": str(token_data.get("token_type") or "Bearer"),
            "expires_in": expires_in,
            "expires_at": saved_at + expires_in,
            "scopes": scopes,
            "token_endpoint": str(token_endpoint),
            "saved_at": saved_at,
        }
        save_credentials(output_path, credential)

    print("Protected SIWC credential file saved locally:")
    print(str(output_path))
    print("Granted ChatGPT plan-use scope: " + ("yes" if REQUIRED_PLAN_SCOPE in scopes else "no"))
    if REQUIRED_PLAN_SCOPE not in scopes:
        print("Identity sign-in succeeded, but plan usage was not granted. Do not enable AI inference.")
    else:
        print("Transfer this file securely to the dedicated VM. Do not upload it to GitHub, Neon, Secret Manager or ChatGPT.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nSign-in cancelled.", file=sys.stderr)
        raise SystemExit(130)
    except (httpx.HTTPError, CallbackError, ValueError) as exc:
        print("Sign-in did not complete: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
