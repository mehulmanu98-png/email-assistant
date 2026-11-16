# Email Assistant

Private single-user dashboard for iCloud Mail and Gmail. It includes a React interface, FastAPI backend, Neon PostgreSQL storage, provider sync, reply drafts and a cloud-scheduled mailbox worker.

## Background architecture

- **Neon PostgreSQL** stores accounts, encrypted provider credentials, messages, drafts, settings and sync jobs.
- **Google Cloud Run** hosts the dashboard and API from one container. The dashboard can cold-start after idle time; scheduled mailbox jobs are independent of the dashboard.
- **Google Cloud Run Jobs + Cloud Scheduler** execute the one-shot worker every 15 minutes. Cloud Scheduler uses the `Asia/Kolkata` timezone and calls the Cloud Run Jobs API using a dedicated service account. It does not require the MacBook or a GitHub scheduled workflow to be active.
- The worker reads the saved mailbox schedule and queues any due slots not yet processed that day; it also handles manually queued Sync Now jobs. A Neon-backed 20-minute singleton lease prevents overlapping Cloud Run Job executions. Interrupted jobs are requeued after the 25-minute stale-job threshold; both the lease and recovery are persisted in Neon.
- Default mailbox sync times are **08:00, 11:00, 14:00 and 17:00 Asia/Kolkata**. The in-app settings can change these times.
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
5. The script deploys the dashboard/API to Cloud Run, deploys a one-shot Cloud Run worker job, tests its Neon connection, grants the scheduler identity permission to invoke that job, and creates one Cloud Scheduler job that triggers every 15 minutes.
6. The script prints the Cloud Run dashboard URL and Gmail OAuth callback URI. Add that exact callback URI to your Google OAuth Web application client. Gmail OAuth cannot connect until the matching Google OAuth client credentials are configured.
7. If you left the Google OAuth fields blank on the first deployment, create the Web OAuth client after you have the callback URI, then run `bash scripts/deploy-cloud-run.sh` again and enter the new client ID/secret when prompted. The script preserves the existing Neon URL, dashboard login, JWT key and mailbox-encryption key on redeployment.
8. Open the dashboard URL and sign in with the dashboard credentials. Connect a test iCloud mailbox using an Apple app-specific password, and/or approve Gmail through Google's OAuth screen.
8. Check Cloud Scheduler job **email-assistant-mail-sync** and Cloud Run job **email-assistant-mail-worker** in the Google Cloud console. Confirm successful executions and that messages appear in the dashboard.

The GitHub `NEON_DATABASE_URL` secret you saved earlier is not used by the primary Cloud Scheduler route; you may leave it there. The app's database URL is stored in Google Secret Manager for Cloud Run and the scheduled worker.

## Local development

Requires Docker Desktop with Docker Compose v2. Run `bash scripts/setup-local.sh` from the repository root and open http://localhost:8080. This is local testing only; closing the Mac stops the local containers. Local Compose uses its own PostgreSQL container unless you change `DATABASE_URL`.

## Mailbox behaviour

- iCloud uses IMAP and SMTP with an Apple app-specific password.
- Gmail uses Google OAuth and Gmail API; the app never asks for your Google password.
- Initial import covers the last 90 days of Inbox. Sync is resumable in batches of up to 500 messages per run.
- Read-state and Trash are only updated locally after provider confirmation.
- Replies default to Reply All recipient handling where headers permit, allow edits to To/CC/BCC, lock From to the original account, and require a separate send approval.
- Uncertain send outcomes are locked against blind retries; check the source account's Sent folder.
- Manual Sync Now queues work in Neon; the cloud worker checks for queued work every 15 minutes, so a manual sync may not begin immediately.
- The raw message is hidden until you choose **Show original email**.
- Background job failures are retried with bounded backoff and interrupted work is recovered.

## AI and other unfinished features

AI summaries, AI-generated replies, automatic follow-up extraction, delegated AI task execution, attachment downloading/previewing and the Apple Notes/Reminders bridge are not active. App-managed conversations and tasks are stored, but they do not produce AI answers or execute delegated work yet.

The user's ChatGPT Go plan is not categorically excluded: OpenAI's current Help Center says Go, Plus and Pro users can use included plan usage in participating apps that support the feature, subject to the app's own eligibility and approval. This Email Assistant has **not** received approval for a commercial Sign in with ChatGPT integration. The official open-source Sign in with ChatGPT DevKit carries a **Noncommercial License** that excludes development, testing, distribution or operation by/for a business in connection with its operations or commercial advantage. Because this Email Assistant is intended to process business correspondence, that DevKit is not used in this project unless OpenAI grants the required commercial rights in writing. The next AI step is to seek OpenAI's commercial-integration approval. Until then, AI work stays blocked/Waiting for User; do not store SIWC credentials in Neon or Google Secret Manager, do not use an unauthorised token-transfer workaround, and do not configure OpenAI API billing, ChatGPT credits or paid fallback.

References:
- [Using your ChatGPT plan in other apps and sites](https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites)
- [Sign in with ChatGPT commercial integration interest form](https://openai.com/form/sign-in-with-chatgpt/)
- [Official DevKit README and licence notice](https://github.com/openai/sign-in-with-chatgpt-devkit)
- [Official DevKit Noncommercial License](https://github.com/openai/sign-in-with-chatgpt-devkit/blob/main/LICENSE)

## Security and operating notes

- The repository is public source code, not a public mailbox. Email data and credentials belong in Neon/Google Secret Manager, never in Git.
- Keep Neon connection URIs, Apple app passwords, Google OAuth secrets, dashboard passwords, JWT secrets and the field key private.
- Cloud Run is protected by the app's single-user login; use a strong unique password. The application requires HTTPS in production.
- The scheduler uses a separate service account with permission only to execute the Cloud Run worker job; the worker runtime identity can read the required Secret Manager secrets.
- Do not expose the Neon database to unrestricted public access; use the pooled URL, require TLS and rotate credentials if exposed.
- Monitor Neon compute/storage/network quotas and Google Cloud billing. Free limits can suspend or charge depending on the plan/service; they are not a universal zero-cost promise.
- GitHub Actions scheduled workflow is not required for production background processing. CI runs on pushes; the optional manual sync diagnostic is a fallback only.

## Automated checks

Backend: `cd backend && pytest -q`

Frontend: `cd frontend && npm install && npm run build`

CI checks backend tests, frontend production build, deployment script syntax and the combined Cloud Run Docker image. Automated checks do not replace live iCloud/Gmail mailbox and delivery tests.
