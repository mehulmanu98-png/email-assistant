# Delivery checklist — Email Assistant

Status as of the latest code commit. CI passing does not prove live provider or cloud deployment.

| Area | Status | Notes |
|---|---|---|
| React dashboard and FastAPI API | Built | Cloud Run image serves both on one origin. |
| PostgreSQL-compatible database layer | Built | Accepts Neon pooled PostgreSQL URL and adds TLS when absent. |
| User login and encrypted mailbox credentials | Built | Production secrets required; single-user bootstrap. |
| iCloud IMAP inbox import | Built | Initial 90 days; resumable 500-message batches. |
| Gmail OAuth + Gmail API | Built | Google OAuth Web client and redirect URI still need setup. |
| Incremental sync and deduplication | Built | Persisted provider cursors/page tokens. |
| iCloud UID handling for no-Message-ID mail | Built | Stored UID is bound to mailbox UIDVALIDITY; stale IDs are blocked. |
| Provider-confirmed read and Trash | Built | Real-account validation pending. |
| Reply All drafts and send approval | Built | To/CC/BCC; From locked; check Sent after uncertain response. |
| Follow-ups workspace | Built | All/Action Required/Awaiting Response filters, overdue state, open source email, edit, snooze, complete and remove tracking item without changing the email. |
| Follow-up lifecycle tests | Built | API integration test covers edit, snooze visibility, unsnooze, complete, remove and retention of source email. |
| Conversation-length handoff | Built | `docs/continuation-handoff.md` records architecture, verified state, pending owner actions and next engineering steps. |
| User-editable sync times and missed-slot catch-up | Built | Uses timezone-aware due-slot state and unique schedule-run keys. |
| Bounded worker retries and stale-job recovery | Built | Retries at 5/10-minute intervals; requeues interrupted jobs. |
| Singleton background worker lease | Built | Neon-backed 20-minute lease prevents overlapping Cloud Run Job runs and expires after interrupted execution. |
| Sync job visibility in dashboard | Built | Recent job activity shown under Accounts & Settings. |
| Cloud Run dashboard/API deployment | Prepared | Deployment script is ready. No completed Cloud Run deployment is recorded in the repository; confirm GCP project and billing state in the console. |
| Cloud Run one-shot worker job | Prepared | Uses same container image and Neon/field-key secrets. |
| Cloud Scheduler background trigger | Prepared | One job every 15 minutes in Asia/Kolkata; can run with laptop off. |
| Neon database | Created | Free-tier Email Assistant project and production branch are ready. Direct inspection on 16 Nov 2026 found no application tables; first successful app startup should initialise them. |
| No notifications | Built | No proactive notification delivery. |
| AI summaries/replies/task execution | Blocked pending approval | ChatGPT Go can be eligible in supported apps, but this app has no commercial SIWC approval. Official open-source DevKit is noncommercial and is not used for business email processing. No API/credits fallback. |
| Attachments and Apple Notes/Reminders | Not built | |
| OpenAI commercial SIWC approval | Pending | Owner must request approval; do not embed the noncommercial DevKit for business use. |
| Live provider acceptance test | Pending | Must test with non-critical mailbox. |
| Production audit, backups/restore, rate limits and independent security review | Pending | Complete before relying on critical business email. |

## Deployment acceptance

1. Create a Google Cloud project and link a billing account; review pricing and create a budget alert.
2. Run `bash scripts/deploy-cloud-run.sh` from the repository root in Google Cloud Shell or a machine with gcloud CLI. The script prompts for Neon connection and dashboard login; secrets are entered privately and stored in Google Secret Manager.
3. Confirm the deployment script's initial Cloud Run Job execution succeeds against Neon.
4. Add the printed Google OAuth callback URI to the Google OAuth Web client; set up OAuth credentials if Gmail is being connected.
5. Sign into the Cloud Run dashboard and connect a non-critical test iCloud mailbox and/or Gmail account.
6. Confirm Cloud Scheduler job `email-assistant-mail-sync` is enabled, and Cloud Run worker job executions complete; use manual Execute for a test rather than waiting for a scheduled interval.
7. Check that emails appear, read/Trash actions update the provider, and a test reply reaches a mailbox you control.
8. Review Google Cloud billing and Neon usage after initial operation. Free allowances are limits, not an assurance of zero cost.

No live deployment or mailbox access is claimed until account/credential setup and real-provider tests succeed.
