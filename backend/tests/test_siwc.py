import json
import os
import stat
from urllib.parse import parse_qs

import httpx
import pytest

from app import siwc


def _record(**updates):
    payload = {
        "issuer": siwc.OPENAI_ISSUER,
        "subject": "test-openai-subject",
        "client_id": "oaiapp_test-client",
        "ext_agent_host_id": "urn:uuid:11111111-2222-4333-8444-555555555555",
        "id_token": "id-token-placeholder",
        "access_token": "access-token-old",
        "refresh_token": "refresh-token-old",
        "token_type": "Bearer",
        "expires_in": 3600,
        "expires_at": 9999999999,
        "scopes": [
            "openid", "profile", "email", "offline_access",
            "resource.invoke", siwc.REQUIRED_PLAN_SCOPE,
        ],
        "token_endpoint": siwc.OPENAI_TOKEN_FALLBACK,
    }
    payload.update(updates)
    return payload


def _save(path, **updates):
    return siwc.save_credentials(path, _record(**updates))


def test_credentials_are_saved_atomically_with_owner_only_permissions(tmp_path):
    path = tmp_path / "private" / "siwc.json"
    payload = _record()

    siwc.save_credentials(path, payload)

    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert siwc.load_credentials(path) == payload

    path.chmod(0o640)
    with pytest.raises(siwc.SIWCError, match="permissions"):
        siwc.load_credentials(path)


def test_credentials_reject_symlinks_and_non_owner_files(tmp_path):
    real = tmp_path / "real.json"
    siwc.save_credentials(real, _record())
    link = tmp_path / "linked.json"
    link.symlink_to(real)

    with pytest.raises(siwc.SIWCError, match="symbolic link"):
        siwc.load_credentials(link)


def test_plan_inference_is_blocked_without_direct_usage_scope(tmp_path):
    path = tmp_path / "siwc.json"
    _save(path, scopes=["openid", "profile", "email"])

    def fail_if_requested(request):
        raise AssertionError("A token request must not occur without the direct plan-use scope.")

    client = httpx.Client(transport=httpx.MockTransport(fail_if_requested))
    try:
        with pytest.raises(siwc.SIWCPlanUsageDisabled):
            siwc.get_access_token(path, http_client=client)
    finally:
        client.close()


def test_unexpired_access_token_is_used_without_refresh(tmp_path):
    path = tmp_path / "siwc.json"
    _save(path, expires_at=5000)

    def fail_if_requested(request):
        raise AssertionError("No HTTP request is needed for a valid access token.")

    client = httpx.Client(transport=httpx.MockTransport(fail_if_requested))
    try:
        assert siwc.get_access_token(path, now=1000, http_client=client) == "access-token-old"
    finally:
        client.close()


def test_refresh_rotates_access_and_refresh_tokens_atomically(tmp_path):
    path = tmp_path / "siwc.json"
    _save(path, expires_at=900)

    def handler(request):
        assert request.url == httpx.URL(siwc.OPENAI_TOKEN_FALLBACK)
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["refresh_token"]
        assert form["client_id"] == ["oaiapp_test-client"]
        assert form["refresh_token"] == ["refresh-token-old"]
        assert form["resource"] == [siwc.OPENAI_RESOURCE]
        assert "scope" not in form
        return httpx.Response(200, json={
            "access_token": "access-token-new",
            "refresh_token": "refresh-token-rotated",
            "expires_in": 3600,
            "scope": "openid profile email offline_access resource.invoke " + siwc.REQUIRED_PLAN_SCOPE,
            "token_type": "Bearer",
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        token = siwc.get_access_token(path, now=1000, http_client=client)
    finally:
        client.close()

    saved = siwc.load_credentials(path)
    assert token == "access-token-new"
    assert saved["access_token"] == "access-token-new"
    assert saved["refresh_token"] == "refresh-token-rotated"
    assert saved["expires_at"] == 4600
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_invalid_refresh_token_requires_reauthentication_and_clears_local_file(tmp_path):
    path = tmp_path / "siwc.json"
    _save(path, expires_at=1)

    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(siwc.SIWCReauthenticationRequired):
            siwc.get_access_token(path, now=1000, http_client=client)
    finally:
        client.close()
    assert not path.exists()


def test_responses_request_uses_store_false_stream_true_and_waits_for_completed(tmp_path):
    path = tmp_path / "siwc.json"
    _save(path, expires_at=9999999999)

    def handler(request):
        assert request.method == "POST"
        assert request.url == httpx.URL(siwc.OPENAI_RESPONSES_URL)
        assert request.headers["Authorization"] == "Bearer access-token-old"
        body = json.loads(request.content)
        assert body["model"] == "model-from-user-catalogue"
        assert body["store"] is False
        assert body["stream"] is True
        assert body["input"] == [{"role": "user", "content": "Summarise the email thread."}]
        events = [
            {"type": "response.created", "response": {"id": "resp_test"}},
            {"type": "response.output_text.delta", "delta": "Supplier "},
            {"type": "response.output_text.delta", "delta": "confirmed the price."},
            {"type": "response.completed", "response": {"id": "resp_test", "status": "completed"}},
        ]
        body = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = siwc.create_response(
            "Summarise the email thread.",
            model="model-from-user-catalogue",
            path=path,
            http_client=client,
        )
    finally:
        client.close()

    assert result == {
        "text": "Supplier confirmed the price.",
        "response_id": "resp_test",
        "completed": True,
    }


def test_responses_stream_usage_limit_pauses_instead_of_generic_failure(tmp_path):
    path = tmp_path / "siwc.json"
    _save(path, expires_at=9999999999)

    def handler(request):
        event = {
            "type": "response.failed",
            "response": {
                "id": "resp_limited",
                "error": {"code": "subscription_sharing_usage_limit_exceeded"},
            },
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream", "x-request-id": "req_test_123"},
            content="data: " + json.dumps(event) + "\n\n",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(siwc.SIWCUsageLimitReached) as caught:
            siwc.create_response("Ask a question.", model="model-a", path=path, http_client=client)
    finally:
        client.close()

    assert caught.value.error_code == "subscription_sharing_usage_limit_exceeded"
    assert caught.value.request_id == "req_test_123"


def test_responses_stream_without_completed_event_is_not_reported_as_success(tmp_path):
    path = tmp_path / "siwc.json"
    _save(path, expires_at=9999999999)

    def handler(request):
        event = {"type": "response.output_text.delta", "delta": "partial"}
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content="data: " + json.dumps(event) + "\n\n",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(siwc.SIWCRequestError, match="without response.completed"):
            siwc.create_response("Ask a question.", model="model-a", path=path, http_client=client)
    finally:
        client.close()


def test_models_endpoint_returns_only_models_visible_to_user(tmp_path):
    path = tmp_path / "siwc.json"
    _save(path, expires_at=9999999999)

    def handler(request):
        assert request.method == "GET"
        assert request.url == httpx.URL(siwc.OPENAI_MODELS_URL)
        return httpx.Response(200, json={"models": [
            {"slug": "shown-model", "display_name": "Shown", "visibility": "list"},
            {"slug": "hidden-model", "display_name": "Hidden", "visibility": "hidden"},
            {"slug": "no-visibility-model", "display_name": "No visibility"},
        ]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        models = siwc.list_models(path, http_client=client)
    finally:
        client.close()
    assert models == [{"slug": "shown-model", "display_name": "Shown"}]


def test_disconnect_always_removes_local_token_and_reports_remote_revocation(tmp_path):
    path = tmp_path / "siwc.json"
    _save(path)

    def handler(request):
        if request.url == httpx.URL(siwc.OPENAI_DISCOVERY_URL):
            return httpx.Response(200, json={
                "issuer": siwc.OPENAI_ISSUER,
                "revocation_endpoint": "https://auth.openai.com/oauth/revoke",
            })
        assert request.url == httpx.URL("https://auth.openai.com/oauth/revoke")
        form = parse_qs(request.content.decode())
        assert form["token"] == ["refresh-token-old"]
        assert form["token_type_hint"] == ["refresh_token"]
        assert form["client_id"] == ["oaiapp_test-client"]
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        assert siwc.revoke_credentials(path, http_client=client) is True
    finally:
        client.close()
    assert not path.exists()
