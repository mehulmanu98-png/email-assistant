# Email Assistant

Private single-user dashboard for iCloud Mail and Gmail. The current implementation includes a React interface, FastAPI backend, Neon-compatible PostgreSQL storage, provider sync, reply drafts and background mailbox jobs.

## Background architecture

- **Neon PostgreSQL** stores accounts, encrypted provider credentials, messages, drafts, settings and sync jobs.
- **Google Cloud Run** hosts the dashboard and API from one container. The dashboard can cold-start after idle time; this does not stop scheduled mailbox processing.
- **GitHub Actions** runs an ephemeral background worker every 15 minutes. It reads the user's configured schedule in Asia/Kolkata, queues due mailbox syncs and processes manual/queued sync jobs. It does not require the MacBook to be on.
- The default mailbox schedule is **08:00, 11:00, 14:00 and 17:00 Asia/Kolkata**. GitHub's scheduled runner is best-effort and can start late during platform load, so jobs are processed in a grace window rather than relying on exact-minute starts.
- The GitHub Actions background worker requires the repository secrets `NEON_DATABASE_URL` and `EMAIL_ASSISTANT_FIELD_KEY`. The field-encryption value must be the same as the one stored by Cloud Run.
- The app sends no proactive notifications.

## Deployment status

Repository source and CI are maintained here: https://github.com/mehulmanu98-png/email-assistant

The application is **not yet live**. No Neon database or Google Cloud project has been provisioned from this repository. Cloud Run needs a Google Cloud account with billing enabled; eligible free allowances and trial credits may offset usage, but they are not a guaranteed zero-cost hosting promise. Keep Cloud Billing budgets/alerts and review usage. See the Google Cloud pricing and free-tier pages before deploying.

## Deploy

Prerequisites: a Neon project, Google Cloud project with billing enabled, Google Cloud CLI, OpenSSL, and (recommended) GitHub CLI authenticated to the repository.

1. In Neon, create a Postgres project and copy the **pooled** connection string. Keep it private. Neon free quotas and compute auto-suspend are subject to the current plan; do not exceed the monthly allowance.
2. Clone this repository and open a terminal at its root.
3. Authenticate with Google Cloud using `gcloud auth login`, select/create a Google Cloud project, and make sure billing is enabled.
4. Run `bash scripts/deploy-cloud-run.sh`. It asks for the project ID, Neon connection URI, dashboard login email/password and optional Google OAuth credentials. It generates random application secrets and stores them in Google Secret Manager. It also adds the Neon URL and field key to GitHub Actions Secrets when GitHub CLI is installed and authenticated.
5. The script prints the Cloud Run dashboard URL and the Google OAuth callback URI. Add that exact callback URI to the Google OAuth Web application client. If Gmail OAuth was not configured during deployment, add the OAuth credentials as Google Secret Manager secrets and update the Cloud Run service environment before connecting Gmail.
6. Open the Cloud Run URL and sign in with the dashboard credentials. Connect a test iCloud mailbox using an Apple app-specific password, and/or approve Gmail through Google's OAuth screen.
7. In GitHub, open Actions and check **Email mailbox background sync**. You can manually run it with **Run workflow** to test the Neon connection. Confirm that the scheduled runs complete and messages appear in the dashboard.

## Local development

Requires Docker Desktop with Docker Compose v2. Run `bash scripts/setup-local.sh` from the repository root and open http://localhost:8080. This is local testing only; closing the Mac stops the local containers. Local Compose uses its own PostgreSQL container unless you change `DATABASE_URL`.

## Mailbox behaviour

- iCloud uses IMAP and SMTP with an Apple app-specific password.
- Gmail uses Google OAuth and Gmail API; the app never asks for the user's Google password.
- Initial import covers the last 90 days of Inbox. Sync is resumable in batches of up to 500 messages per run.
- Read-state and Trash are only updated locally after provider confirmation.
- Replies default to Reply All recipient handling where headers permit, allow edits to To/CC/BCC, lock From to the original account, and require a separate send approval.
- Uncertain send outcomes are locked against blind retries; check the source account's Sent folder.
- The raw message is hidden until the user chooses **Show original email**.

## AI and other unfinished features

AI summaries, AI-generated replies, automatic follow-up extraction, task execution, attachment downloading/previewing and the Apple Notes/Reminders bridge are not active. No OpenAI API billing, external AI API, paid model fallback or fabricated AI response is enabled. App-managed conversations/tasks are stored but do not produce AI answers under the current configuration.

## Security and operating notes

- The repository is public source code, not a public mailbox. Email data and credentials belong in Neon/Google Secret Manager, never in Git.
- Keep Neon connection URIs, Apple app passwords, Google OAuth secrets, dashboard passwords, JWT secrets and the field key private.
- Cloud Run is protected by the app's single-user login; use a strong unique password. The application requires HTTPS in production.
- Do not expose the Neon database to unrestricted public access; use the pooled URL, require TLS and rotate credentials if exposed.
- GitHub Actions runs code from the default branch with access to the two explicitly configured secrets. Keep repository write access restricted.
- Free tiers can sleep, auto-suspend, cap usage or change. Scheduled GitHub runs are best-effort, not a guaranteed SLA. Monitor Cloud Run billing and Neon usage.

## Automated checks

Backend: `cd backend && pytest -q`

Frontend: `cd frontend && npm install && npm run build`

The CI workflow also builds the root Cloud Run Docker image. Automated checks do not replace live iCloud/Gmail mailbox and delivery tests.
