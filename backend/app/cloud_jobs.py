"""Optional Cloud Run worker trigger.

The free hosted deployment deliberately leaves Cloud Run unconfigured. Manual sync
requests are durably queued in Neon and the GitHub Actions worker drains that queue
on its scheduled cadence. This function returns False unless a Cloud Run deployment
is explicitly configured in a separately approved environment.
"""
from __future__ import annotations

import httpx

from .config import settings

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)


def trigger_mailbox_worker() -> bool:
    """Request one Cloud Run Job execution using the attached runtime identity.

    Returns False in local development when cloud execution is not configured.
    Raises on a configured but unsuccessful trigger; the API layer logs only the
    exception type and leaves the durable queue untouched for scheduled retry.
    """
    project = settings.cloud_project_id.strip()
    region = settings.cloud_region.strip()
    job = settings.mail_worker_job.strip()
    if not project or not region or not job:
        return False

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
