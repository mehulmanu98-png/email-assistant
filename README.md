# Email Assistant

Private single-user dashboard for iCloud Mail and Gmail. It includes a React interface, FastAPI backend, Neon PostgreSQL storage, provider sync, reply drafts and a cloud-scheduled mailbox worker.

## Background architecture

- **Neon PostgreSQL** stores accounts, encrypted provider credentials, messages, drafts, settings and sync jobs.
- **Google Cloud Run** hosts the dashboard and API from one container. The dashboard can cold-start after idle time; scheduled mailbox jobs are independent of the dashboard.
- **Google Cloud Run Jobs + Cloud Scheduler** wake the one-shot worker every 15 minutes. Each run checks the saved review slots, drains durable queued jobs, and recovers interrupted work; it does **not** sync every 15 minutes. The 15-minute cadence also allows bounded 5/10-minute retries and stale-job recovery. Cloud Scheduler uses `Asia/Kolkata` and a dedicated service account. It does not require the MacBook or a GitHub workflow to be active.
- The worker reads the saved mailbox schedule and queues any due slots not yet processed that day; it also handles manually queued Sync Now jobs. A Neon-backed 20-minute singleton lease prevents overlapping Cloud Run Job executions. Interrupted jobs are requeued after the 25-minute stale-job threshold; both the lease and recovery are persisted in Neon.
- Default mailbox sync times are **08:00, 12:00 and 17:00 Asia/Kolkata**. The in-app settings can change these times.
- No proactive notifications are configured.
- GitHub Actions is used for CI. An optional manual mailbox diagnostic workflow exists, but it is not the primary scheduler.

## Deployment status

Repository source and CI: https://github.com/mehulmanu98-png/email-assistant

The Neon project `Email Assistant` exists on the free-tier organisation with a ready `production` branch and `neondb` database. A direct database inspection on 16 November 2026 found no application tables yet; the FastAPI startup routine creates them on the first successful application startup. The repository's deployment record does not show a completed Cloud Run deployment, and the GCP project/billing state has not been independently verified in this session. Check the Google Cloud console before assuming those setup steps are complete. The GitHub `NEON_DATABASE_URL` secret was previously recorded as saved; it is not used by the primary Cloud Run deployment path.

Cloud Run requires a Google Cloud billing account. Cloud Run has a monthly free usage allowance based on resource usage, and Cloud Scheduler includes three jobs per billing account free each month. This deployment uses one scheduler job. These allowances are not a guarantee of zero cost; review current pricing, create a billing budget alert and monitor actual usage. <https://cloud.google.com/run/pricing> <https://cloud.google.com/scheduler/pricing>

## Deploy

Prerequisites: your Neon project (already created), a Google Cloud project with billing enabled, the Google Cloud CLI, and OpenSSL. A browser-based Google Cloud Shell also works because it comes with the Cloud CLI.

1. In Neon, make sure you have the **pooled** PostgreSQL connection URI available. Keep it private.
2. Create a Google Cloud project, link a billing account and open Google Cloud Shell, or install the Google Cloud CLI locally and authenticate with `gcloud auth login`.
3. Clone this repository in the terminal and enter its folder:
   `git clone https://github.com/mehulmanu98-png/email-assistant.git && cd email-assistant`
4. Run `bash scripts/deploy-cloud-run.sh`. It asks for the project ID, Neon connection URI, dashboard login email/password and optional Google OAuth Web client credentials. It generates random application secrets on first deployment and stores them in Google Secret Manager. On redeployment it preserves the existing dashboard bootstrap login, JWT signing key and mailbox-encryption key so saved provider credentials remain decryptable.
5. The script deploys the dashboard/API and one-shot Cloud Run worker, tests the worker's Neon connection, grants the scheduler and dashboard runtime identities permission to invoke the worker, and creates one Cloud Scheduler job. The 15-minute cadence checks saved mailbox slots, due retries and stale jobs; actual scheduled email syncs still occur only at your saved times (default 08:00, 12:00 and 17:00 IST).
6. Before reporting success, the script checks the public dashboard route and calls `/api/health` to verify the API can reach Neon. If that check fails, inspect Cloud Run logs and database connectivity rather than connecting a mailbox.
7. The script prints the dashboard URL and Gmail OAuth callback URI. Add that exact callback URI to your Google OAuth Web application client. Gmail OAuth cannot connect until the matching Google OAuth client credentials are configured.
8. If you left the Google OAuth fields blank on first deployment, create the Web OAuth client and redeploy with its ID/secret. The script preserves the Neon URL, dashboard login, JWT key and mailbox-encryption key on redeployment.
9. Open the dashboard, sign in and connect a non-critical iCloud mailbox using an Apple app-specific password, and/or approve Gmail through Google's OAuth screen.
10. Check Cloud Scheduler job **email-assistant-mail-sync** and Cloud Run job **email-assistant-mail-worker** in Google Cloud Console. Confirm successful executions and messages appearing in the dashboard.

The GitHub `NEON_DATABASE_URL` secret you saved earlier is not used by the primary Cloud Scheduler route; you may leave it there. The app's database URL is stored in Google Secret Manager for Cloud Run and the scheduled worker.

## Local development

Requires Docker Desktop with Docker Compose v2. Run `bash scripts/setup-local.sh` from the repository root and open http://localhost:8080. This is local testing only; closing the Mac stops the local containers. Local Compose uses its own PostgreSQL container unless you change `DATABASE_URL`.

## Mailbox behaviour

- iCloud uses IMAP and SMTP with an Apple app-specific password.
- Gmail uses Google OAuth and Gmail API; the app never asks for your Google password.
- Initial import covers the last 90 days of Inbox. Sync is resumable in batches of up to 500 messages per run.
- Read-state and Trash are only updated locally after provider confirmation.
- Replies default to Reply All recipient handling where headers permit, allow edits to To/CC/BCC, lock From to the original account, and require a separate send approval.
- New outbound messages require explicit sender-account selection; their drafts are stored in the app and require a separate final send approval.
- Uncertain send outcomes are locked against blind retries; check the source account's Sent folder.
- Forwarding uses a separate internal forward draft and explicit approval. It defaults to the original source account, sends outside the source thread, includes the original message text and optionally forwards original attachments within the 25 MB combined in-app limit. Provider acceptance is reported separately from final delivery.
- Manual Sync Now commits a durable job to Neon and requests an immediate Cloud Run worker execution using the dashboard runtime service identity. The 15-minute Cloud Scheduler run remains a fallback for queued or interrupted work.
- Full provider-thread retrieval is available on demand for iCloud and Gmail, including available original Sent messages; results are chronological and disclose provider-scan limitations.
- Follow-ups can be created manually from the Follow-ups workspace or from a selected email, linked to the source message, assigned an owner and due/expected time, then edited, snoozed or completed.
- The raw message is hidden until you choose **Show original email**.
- An email thread can be linked to an app-managed Email Assistant conversation. Existing imported messages are backfilled once; new synced messages are appended once through a per-message deduplication ledger. Unlinking stops future appends but retains conversation history.
- Gmail threads use the provider's native thread ID. iCloud threads use the root Message-ID from References/In-Reply-To where available; ambiguous older messages may need a manual source-thread check.
- Linked email content is stored as untrusted source material and displayed as escaped text. Attachments are not included in conversation context.
- Background job failures are retried with bounded backoff and interrupted work is recovered.

## AI and other unfinished features

AI summaries, AI-generated replies, automatic follow-up extraction, delegated AI task execution and attachment-content analysis are not active.

The following non-AI features are implemented in the current source:
- Original attachment listing, secure viewing and download from the source mailbox.
- Separate forward drafts with optional original attachments and explicit send approval.
- App-managed email-thread linking, one-time history backfill and append-on-sync deduplication.
- Secure Apple Notes/Reminders command queue, one-time device enrolment, device polling and command-result receipts. A real Apple Shortcut still needs to be installed/enrolled and acceptance-tested on a device before native Notes or Reminders creation can be considered live.
- Each inbox email card has its own actions for View Original, Prepare Reply, Mark as Read/Unread, Delete, Block Sender, Summarise Entire Thread and Ask a Question. The two AI actions explicitly report that commercial ChatGPT integration approval is pending; they do not produce canned or fabricated output.

App-managed conversations and tasks are persisted, but they do not generate AI answers or execute delegated AI work yet.

The user's ChatGPT Go plan is not categorically excluded: OpenAI's current Help Center says Go, Plus, Pro and Business plans may use included plan usage in participating commercial apps that support the feature, subject to the app's own participation/eligibility and the user's separate consent. This Email Assistant is not currently an approved participating app. OpenAI's Sign in with ChatGPT Terms (effective 4 November 2026) add a material architecture restriction: persistent SIWC authentication tokens must be stored locally under the user's control, not in a remote or managed environment; plan usage requests must originate from the user's local runtime or a remote runtime that only that user controls, and background use requires express consent. This makes unattended Cloud Run AI processing unresolved: do not assume that SIWC tokens can be persisted in Neon or Google Secret Manager, and obtain written OpenAI clarification of the approved runtime/token-storage arrangement before implementing it. The official open-source Sign in with ChatGPT DevKit also carries a **Noncommercial License** that excludes development, testing, distribution or operation by/for a business in connection with its operations or commercial advantage. Because this Email Assistant is intended to process business correspondence, that DevKit is not used unless OpenAI grants the required commercial rights in writing. Until a compliant architecture and approval exist, AI work stays blocked/Waiting for User; do not use an unauthorised token-transfer workaround, and do not configure OpenAI API billing, ChatGPT credits or paid fallback.

References:
- [Using your ChatGPT plan in other apps and sites](https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites)
- [Sign in with ChatGPT commercial integration interest form](https://openai.com/form/sign-in-with-chatgpt/)
- [Official DevKit README and licence notice](https://github.com/openai/sign-in-with-chatgpt-devkit)
- [Official DevKit Noncommercial License](https://github.com/openai/sign-in-with-chatgpt-devkit/blob/main/LICENSE)

## Security and operating notes

- The repository is public source code, not a public mailbox. Email data and credentials belong in Neon/Google Secret Manager, never in Git.
- Keep Neon connection URIs, Apple app passwords, Google OAuth secrets, dashboard passwords, JWT secrets and the field key private.
- Cloud Run is protected by the app's single-user login; use a strong unique password. The application requires HTTPS in production.
- The app persists a failed-login lockout after five bad attempts for 15 minutes. Production state-changing browser requests must carry the exact configured Origin; Apple Shortcut device-token endpoints use separate device authentication.
- The scheduler uses a separate service account with permission only to execute the Cloud Run worker job; the worker runtime identity can read the required Secret Manager secrets.
- Do not expose the Neon database to unrestricted public access; use the pooled URL, require TLS and rotate credentials if exposed.
- Monitor Neon compute/storage/network quotas and Google Cloud billing. Free limits can suspend or charge depending on the plan/service; they are not a universal zero-cost promise.
- GitHub Actions scheduled workflow is not required for production background processing. CI runs on pushes; the optional manual sync diagnostic is a fallback only.

## Automated checks

Backend: `cd backend && pytest -q`

Frontend: `cd frontend && npm install && npm run build`

CI checks backend tests, frontend production build, deployment script syntax and the combined Cloud Run Docker image. Automated checks do not replace live iCloud/Gmail mailbox and delivery tests.
