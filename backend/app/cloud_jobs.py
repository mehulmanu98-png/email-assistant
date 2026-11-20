"""Trigger the mailbox worker after user-approved jobs are committed.

Cloud Run is preferred when configured. On the free Render deployment, a
fine-grained GitHub token can dispatch a send-only Actions run so approved
outgoing mail does not wait for the five-minute scheduled poll.
"""
from __future__ import annotations

import httpx

from .config import settings

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)


def trigger_mailbox_worker() -> bool:
    """Trigger a worker execution; return False if no trigger is configured."""
    project = settings.cloud_project_id.strip()
    region = settings.cloud_region.strip()
    job = settings.mail_worker_job.strip()
    if project and region and job:
        token_response = httpx.get(
            _METADATA_TOKEN_URL,
            headers={"Metadata-Flavor": "Google"},
            timeout=4.0,
        )
        token_response.raise_for_status()
        access_token = str(token_response.json().get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("Cloud Run runtime identity returned no access token.")
        url = (
            "https://run.googleapis.com/v2/projects/"
            f"{project}/locations/{region}/jobs/{job}:run"
        )
        response = httpx.post(
            url,
            content=b"",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Cloud Run rejected the worker trigger (HTTP {response.status_code}).")
        return True

    token = settings.github_worker_token.strip()
    repository = settings.github_repository.strip()
    ref = settings.github_worker_ref.strip() or "main"
    if not token:
        return False
    if not repository or "/" not in repository:
        raise RuntimeError("GITHUB_REPOSITORY must use owner/repository format.")
    url = f"https://api.github.com/repos/{repository}/actions/workflows/mail-sync.yml/dispatches"
    response = httpx.post(
        url,
        json={"ref": ref, "inputs": {"send_only": "true"}},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=12.0,
    )
    if response.status_code != 204:
        raise RuntimeError(f"GitHub Actions rejected the immediate send trigger (HTTP {response.status_code}).")
    return True
