# Delivery checklist — Email Assistant

Status is conservative. **Built** means code is present and automated checks cover the feature where appropriate. Real Apple/Google account tests and cloud deployment have not been completed.

## Working code

| Area | Status | Notes |
|---|---|---|
| FastAPI backend, React dashboard, PostgreSQL and worker | Built | Docker Compose services are included. |
| Single-user login and encrypted provider credentials | Built | Production secrets must be configured privately. |
| iCloud connection | Built | Apple app-specific password; test with a non-critical mailbox. |
| Gmail OAuth with PKCE and refresh token | Built | Requires Google Cloud OAuth web client and consent approval. |
| Initial 90-day Inbox import | Built | iCloud/Gmail sync uses 500-message resumable batches. |
| Incremental mailbox sync | Built | Dedupe and provider cursor state are persisted. |
| Scheduled sync | Built | Default 08:00, 11:00, 14:00 and 17:00 IST; editable in dashboard. |
| Manual sync and per-account sync | Built | Jobs are processed by the background worker. |
| Provider-confirmed read state and Trash | Built | IMAP/Gmail actions still need live account testing. |
| Reply All draft editor | Built | To/CC/BCC editable; From locked to source mailbox. |
| Explicit send approval and duplicate protection | Built | Provider acceptance is not proof of final delivery. |
| Follow-ups and task/conversation records | Partial | Manual records only; AI extraction/execution disabled. |
| Original email hidden until requested | Built | User can select Show original email. |
| No-notification preference | Built | No notification delivery code configured. |
| Attachment preview/download and Notes/Reminders bridge | Not built | |
| AI summaries, reply generation and auto-follow-up extraction | Disabled | No AI API billing or paid fallback. |
| Production backup/restore, audit, rate limits and security review | Not complete | Required before storing sensitive production mail. |

## Background operation

- **Local laptop run:** Docker services run only while the Mac and Docker are running.
- **Cloud run:** Requires deployment of frontend, API, PostgreSQL and worker to an always-on server/container host with persistent storage. HTTPS and private secrets are required.
- **Current state:** Repository code only. No cloud provider account, server, domain, secret store or live deployment has been provisioned. A free host that sleeps cannot guarantee 24/7 execution.

## One-time setup and acceptance test

1. Install Docker Desktop and Docker Compose v2 for local testing, or select an always-on cloud host for remote operation.
2. For Gmail, create a Google Cloud project, enable Gmail API, configure consent and create a Web OAuth client; use the app's exact HTTPS redirect URI for cloud or localhost URI for local testing.
3. Run `bash scripts/setup-local.sh` locally or configure the private production environment on the cloud host.
4. Connect a test iCloud mailbox using an Apple app-specific password and/or connect Gmail through Google's OAuth screen.
5. Check first import, pagination, incremental sync, scheduled worker operation, provider read-state, Trash and a reply sent to an address you control.
6. Confirm the GitHub Actions run is green. CI cannot replace real-provider tests.

## Not yet complete

Cloud deployment, AI execution, attachment processing, Apple Notes/Reminders, forwarded-email workflow, and production hardening remain outstanding. No notification delivery is configured.
