# Delivery checklist — Email Assistant

Status as of the latest code commit. CI passing does not prove live provider or cloud deployment.

| Area | Status | Notes |
|---|---|---|
| React dashboard and FastAPI API | Built | Cloud Run image serves both on one origin. |
| PostgreSQL-compatible database layer | Built | Accepts Neon pooled PostgreSQL URL and adds TLS when absent. |
| User login and encrypted mailbox credentials | Built | PBKDF2 password hashing, HttpOnly/Secure/SameSite session cookie in production, encrypted provider credentials and single-user bootstrap. |
| Login and browser-origin protections | Built | Persistent lockout after five failed sign-ins for 15 minutes; production state-changing browser requests require the exact configured Origin. Apple device-token routes use their separate token authentication. |
| iCloud IMAP inbox import | Built | Initial 90 days; resumable 500-message batches. |
| Gmail OAuth + Gmail API | Built | Google OAuth Web client and redirect URI still need setup. |
| Incremental sync and deduplication | Built | Persisted provider cursors/page tokens. |
| iCloud UID handling for no-Message-ID mail | Built | Stored UID is bound to mailbox UIDVALIDITY; stale IDs are blocked. |
| Provider-confirmed read/unread and Trash | Built | Read and unread write-back plus Trash require provider confirmation before local state is changed. Real-account validation pending. |
| Reply All drafts and send approval | Built | To/CC/BCC; From locked; editable internal draft; explicit approval; check Sent after uncertain response. |
| New outbound composer and send approval | Built | Sender selection is mandatory with no default From; drafts are stored internally and require final approval; uncertain provider results block blind retries. |
| Forward drafts and approval | Built | Separate internal draft; source-account From; optional original attachments; sent outside original thread; explicit approval and uncertain-send protection. |
| Follow-ups workspace | Built | All/Action Required/Awaiting Response filters, overdue state, open source email, manual creation from the dashboard or selected email, edit, snooze, complete and remove tracking item without changing the email. |
| Follow-up lifecycle tests | Built | API integration test covers edit, snooze visibility, unsnooze, complete, remove and retention of source email. |
| Linked email conversations | Built | Authenticated link/unlink controls; backfills existing thread, appends future syncs once, retains history and deduplication ledger after unlink; Gmail native thread IDs and iCloud References/In-Reply-To root keys. |
| Email conversation sync tests | Built | API test covers backfill, no duplicates, worker append-once, unlink stop, relink without duplicates and destination conflict; iCloud root-key resolution test. |
| Full provider-thread retrieval | Built | On-demand iCloud/Gmail retrieval includes available messages from Sent and Inbox, chronologically; returns scan diagnostics and discloses when completeness cannot be confirmed. Live provider acceptance pending. |
| Conversation-length handoff | Built | `docs/continuation-handoff.md` records architecture, verified state, pending owner actions and next engineering steps. |
| User-editable sync times and missed-slot catch-up | Built | Uses timezone-aware due-slot state and unique schedule-run keys. |
| Bounded worker retries and stale-job recovery | Built | Retries at 5/10-minute intervals; requeues interrupted jobs. |
| Singleton background worker lease | Built | Neon-backed 20-minute lease prevents overlapping Cloud Run Job runs and expires after interrupted execution. |
| Sync job visibility in dashboard | Built | Recent job activity shown under Accounts & Settings. |
| Cloud Run dashboard/API deployment | Prepared | Deployment script is ready. No completed Cloud Run deployment is recorded in the repository; confirm GCP project and billing state in the console. |
| Cloud Run one-shot worker job | Prepared | Uses same container image and Neon/field-key secrets. Runtime service identity and scheduler identity each receive job-scoped run invoker permission. |
| Immediate manual worker trigger | Built in main | Sync Now and first account sync request the Cloud Run worker immediately after the queue commit; the 15-minute scheduler remains the fallback. Live cloud IAM acceptance pending. |
| Cloud Scheduler background trigger | Prepared | One job every 15 minutes in Asia/Kolkata; can run with laptop off. |
| Neon database | Created | Free-tier Email Assistant project and production branch are ready. Direct inspection on 16 Nov 2026 found no application tables; first successful app startup should initialise them. |
| Per-email card actions | Built in main | Each email card has its own View Original, Prepare Reply, Read/Unread, Delete, Block Sender, Summarise Entire Thread and Ask a Question controls. AI actions report the approval blocker without returning fabricated output. |
| Provider-confirmed read and unread | Built in main | Both directions update iCloud/Gmail first; local state changes only after provider confirmation. |
| No notifications | Built | No proactive notification delivery in current implementation. |
| AI summaries/replies/task execution | Blocked pending approval | ChatGPT Go can be eligible in participating commercial apps, but this app has no commercial SIWC approval. Official open-source DevKit is noncommercial and is not used for business email processing. No API/credits fallback. |
| Attachments | Partially built | Original attachments can be listed, viewed and downloaded from the provider. AI extraction/analysis and Office-format previews are not implemented. |
| Apple Notes/Reminders | Queue and device APIs built; Shortcut acceptance pending | Device enrolment, command queue, polling, idempotency and result receipts are implemented. A real Shortcut still needs setup and live testing on an enrolled Mac/iPhone. |
| OpenAI commercial SIWC approval | Pending | Owner must request approval; do not embed the noncommercial DevKit for business use. |
| Live provider acceptance test | Pending | Must test with non-critical mailbox. |
| Initial authentication security controls | Built | Persistent five-failure/15-minute login lockout and production Origin validation are covered by automated tests. |
| Production audit and backups/restore | Pending | Independent security review, backup/restore procedure and live deployment hardening remain necessary before relying on critical business email. |

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
