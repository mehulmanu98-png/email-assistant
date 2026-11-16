import httpx

from app import cloud_jobs


def test_cloud_worker_trigger_uses_runtime_metadata_token(monkeypatch):
    monkeypatch.setattr(cloud_jobs.settings, "cloud_project_id", "email-assistant-project")
    monkeypatch.setattr(cloud_jobs.settings, "cloud_region", "asia-south1")
    monkeypatch.setattr(cloud_jobs.settings, "mail_worker_job", "email-assistant-mail-worker")

    calls = {}

    def fake_get(url, headers=None, timeout=None, **kwargs):
        calls["metadata"] = {"url": url, "headers": headers, "timeout": timeout}
        return httpx.Response(200, json={"access_token": "test-runtime-token"})

    def fake_post(url, headers=None, content=None, timeout=None, **kwargs):
        calls["run"] = {
            "url": url,
            "headers": headers,
            "content": content,
            "timeout": timeout,
        }
        return httpx.Response(200, json={"name": "operations/worker-start"})

    monkeypatch.setattr(cloud_jobs.httpx, "get", fake_get)
    monkeypatch.setattr(cloud_jobs.httpx, "post", fake_post)

    assert cloud_jobs.trigger_mailbox_worker() is True
    assert calls["metadata"]["url"] == cloud_jobs._METADATA_TOKEN_URL
    assert calls["metadata"]["headers"] == {"Metadata-Flavor": "Google"}
    assert calls["run"]["url"] == (
        "https://run.googleapis.com/v2/projects/email-assistant-project/"
        "locations/asia-south1/jobs/email-assistant-mail-worker:run"
    )
    assert calls["run"]["headers"]["Authorization"] == "Bearer test-runtime-token"
    assert calls["run"]["content"] == b""


def test_cloud_worker_trigger_is_disabled_without_cloud_configuration(monkeypatch):
    monkeypatch.setattr(cloud_jobs.settings, "cloud_project_id", "")
    monkeypatch.setattr(cloud_jobs.settings, "cloud_region", "asia-south1")
    monkeypatch.setattr(cloud_jobs.settings, "mail_worker_job", "email-assistant-mail-worker")

    def unexpected_request(*args, **kwargs):
        raise AssertionError("Local development must not contact the Cloud Run metadata server.")

    monkeypatch.setattr(cloud_jobs.httpx, "get", unexpected_request)
    assert cloud_jobs.trigger_mailbox_worker() is False
