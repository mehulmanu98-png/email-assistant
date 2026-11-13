# Delivery checklist — Email Assistant

This status is intentionally conservative. **Built** means code is present and automated checks cover the feature where appropriate. OAuth approval, provider behaviour and real-world delivery still require testing with a test mailbox.

## Backend

| Requirement | Status | Notes |
|---|---|---|
| FastAPI service, health endpoint and account-scoped routes | Built | |
| PostgreSQL persistence and additive draft-send-state upgrade | Built | Not a full Alembic migration framework. |
| Single-user bootstrap, password hashing and signed HTTP-only session | Built | |
| Encrypted provider credentials | Built | Fernet-derived field key; keep the generated key stable. |
| iCloud IMAP initial Inbox import | Built | 90-day window, maximum 500 messages per sync; no full-folder sync. |
| Gmail Google OAuth + PKCE + offline token refresh | Built | Requires Google Cloud OAuth Web client, consent and real-account verification. |
| Gmail API Inbox incremental sync | Built | Inbox-only query; capped per run. |
| Manual mailbox sync worker | Built | |
| Scheduled mailbox sync | Built | Default 08:00, 12:00 and 17:00 IST. Mailbox sync only, no AI review. |
| Unified Inbox records, account filtering and local search | Built | |
| Provider-confirmed read state | Built | Gmail modify API and iCloud IMAP UID flags; real-account test required. |
| Provider-side move to Trash | Built | Gmail Trash API; iCloud UID MOVE depends on server support; real-account test required. |
| App-level sender block | Built | Hides matching sender in this application only, not at provider level. |
| Internal reply drafts | Built | Database-backed, idempotent creation per source message. |
| Reply All defaults, editable To/CC/BCC and locked source From | Built | Depends on recipient headers available from the provider. |
| Explicit send approval, source-account enforcement and duplicate guard | Built | Gmail API / iCloud SMTP; uncertain outcome blocks retry. Verify with test mailboxes. |
| Forward composer and forward action | Not built | |
| Attachment download, viewer and content extraction | Not built | Only attachment presence is detected. |
| AI mail/thread summaries, priority assessment and reply drafting | Not available | AI disabled; current Go plan is not eligible for official plan usage integration. |
| Follow-up create, edit, snooze, complete and remove | Built | Manual entry only; no AI extraction. |
| Task records, priority overrides and Hard/Target deadline rules | Built | Deadline policy unit tests included. |
| Scheduled task execution, dependencies, leases/checkpoints and three-slot queue | Partial | Task records and scheduled-start field exist; task executor is not active. |
| App-managed AI conversation persistence | Built | Stores user messages; no AI response generation. |
| Official ChatGPT-plan/SIWC integration | Not available for current plan | No API-billing fallback or session-cookie workaround. |
| Apple Notes/Reminders Shortcut bridge | Not built | Requires device bridge and real-device validation. |
| Full audit trail, rate limiting, full migrations and backup/restore test | Not built | Required before remote production. |

## Frontend

| Requirement | Status | Notes |
|---|---|---|
| Responsive React dashboard and four sections | Built | Inbox, Follow-ups, AI Assistant, Accounts & Settings. |
| Single-user login/session flow | Built | |
| Inbox search, list and message detail | Built | |
| Original email body display | Built | Shows safe text; does not execute message HTML. |
| Manual Sync Now and per-account sync | Built | |
| Add iCloud account | Built | Apple app-specific password. |
| Gmail connect via Google OAuth redirect | Built | Requires OAuth client credentials in private .env. |
| Internal reply draft editor | Built | To, CC, BCC, subject, body and locked From. |
| Approve and send | Built | Confirmation and draft snapshot check. |
| Move to Trash and app-only sender block | Built | Confirmation before provider action. |
| Attachment viewing/downloading | Not built | |
| Follow-up completion/removal | Built | Rich edit/snooze UI remains partial. |
| Persistent app-managed chat list and local messages | Built | No model-generated responses. |
| AI task list, priorities and deadlines | Built | Tasks are saved but not executed. |
| Account list, status and disconnect | Built | |
| Editable sync schedule in UI | Not built | Schedule is server environment configuration. |
| Mobile layout | Built | Device QA remains necessary. |

## One-time setup and acceptance test

1. Install Docker Desktop and Docker Compose v2.
2. If using Gmail, create a Google Cloud project, enable the Gmail API, configure the consent screen, create a Web application OAuth client, and register `http://localhost:8080/api/oauth/gmail/callback`. Keep its client ID and secret available for the setup script.
3. Clone the repository and run `bash scripts/setup-local.sh`. Enter your dashboard login and, when prompted, the optional Google OAuth client ID and secret. If you do not configure Gmail, leave both blank.
4. Connect a test iCloud mailbox with an Apple app-specific password and/or connect the test Gmail account through Google's consent screen.
5. Test initial sync, manual sync, scheduled sync, read-state write-back, Trash and a reply to an address you control. Check the Sent folder after sending. Do not start with a primary business mailbox.
6. Verify the latest GitHub Actions run is green. Automated CI cannot replace real Apple/Google account tests or iPhone/Mac device testing.

## Not included in this release

AI email review and AI-generated summaries/replies/follow-ups/task execution, forwarded email, attachment content processing, Apple Notes/Reminders integration, editable in-app schedule, remote cloud deployment and production-grade audit/rate-limit/backup hardening remain outstanding.

No notifications are configured.
