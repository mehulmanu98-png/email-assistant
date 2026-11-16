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
| iCloud UID handling for no-Message-ID mail | Built | Uses stored IMAP UID for supported actions. |
| Provider-confirmed read and Trash | Built | Real-account validation pending. |
| Reply All drafts and send approval | Built | To/CC/BCC; From locked; check Sent after uncertain response. |
| User-editable sync times and missed-slot catch-up | Built | Uses timezone-aware due-slot state and unique schedule-run keys. |
| Bounded worker retries and stale-job recovery | Built | Retries at 5/10-minute intervals; requeues interrupted jobs. |
| Sync job visibility in dashboard | Built | Recent job activity shown under Accounts & Settings. |
| Cloud Run dashboard/API deployment | Prepared | No Google Cloud project/deployment yet. |
| Cloud Run one-shot worker job | Prepared | Uses same container image and Neon/field-key secrets. |
| Cloud Scheduler background trigger | Prepared | One job every 15 minutes in Asia/Kolkata; can run with laptop off. |
| Neon database | User setup completed | Project created; GitHub NEON_DATABASE_URL secret saved. Connection has not yet been tested by app. |
| No notifications | Built | No proactive notification delivery. |
| AI summaries/replies/task execution | Disabled | No AI API billing or paid fallback. |
| Attachments and Apple Notes/Reminders | Not built | |
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
