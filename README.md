# Email Assistant

A private, single-user email workspace for iCloud Mail and Gmail. The application includes a React dashboard, FastAPI backend, PostgreSQL database and a separate durable mailbox-sync worker.

## Important: local run vs background run

The code in this repository is **not yet deployed to cloud hosting**. Running Docker Compose on your Mac is useful for testing, but closing or sleeping the Mac stops the local containers and scheduled worker.

To run while your Mac is off, deploy the whole Docker Compose stack to an always-on cloud VM or equivalent container host: web frontend, API, PostgreSQL with persistent storage, and the worker. Put HTTPS in front of the web service (the Compose file binds it to localhost by default for a same-host TLS reverse proxy). The cloud host must keep the worker running and retain the database volume. A free plan that sleeps or pauses cannot guarantee scheduled sync. No hosting provider has been selected, no cloud deployment has been performed, and no mailbox credentials are stored in this public repository.

## Current capabilities

- Unified inbox storage for iCloud Mail and Gmail.
- iCloud Mail via Apple app-specific password; Gmail via Google OAuth with PKCE and offline refresh credentials.
- Initial 90-day Inbox import, incremental mailbox sync, and resumable 500-message batches.
- Scheduled mailbox sync at **08:00, 11:00, 14:00 and 17:00 Asia/Kolkata** by default. These settings can be edited in the dashboard.
- Manual Sync Now and per-account sync.
- Provider-confirmed read-state changes and provider Trash operations.
- Internal Reply All drafts with editable To/CC/BCC, locked From account, and explicit send confirmation.
- App-only sender blocking, follow-ups and task/conversation records.
- Raw email body hidden until the user chooses **Show original email**.
- No proactive notifications.

## What is not active

AI email summaries, AI-generated replies, automatic follow-up extraction, AI task execution, attachment downloading/previewing and the Apple Notes/Reminders bridge are not active in this release. The AI features are deliberately disabled rather than returning invented content. There is no OpenAI API billing or paid fallback configured.

## Local testing

Requires Docker Desktop with Docker Compose v2.

1. Clone this repository.
2. Run `bash scripts/setup-local.sh` from the repository root.
3. Enter your dashboard email and a unique password. The script generates local secrets and starts the services.
4. Open http://localhost:8080 and sign in.
5. Add an iCloud account with an Apple app-specific password and/or connect Gmail through Google's consent screen.

The setup script creates a private `.env` file with restrictive permissions and refuses to overwrite an existing one. Never commit or share `.env`. The database is private and is not exposed as a host port. `docker compose down` stops the services; `docker compose down -v` deletes the local database volume.

## Gmail OAuth setup

Create a Google Cloud project, enable the Gmail API, configure the OAuth consent screen and create an OAuth client of type **Web application**. Register the exact redirect URI:

`http://localhost:8080/api/oauth/gmail/callback`

Enter the client ID and secret in the local setup prompt. Google handles account selection and consent; never enter your Google password into this app. For a cloud deployment, change the redirect URI and `GOOGLE_REDIRECT_URI` to the HTTPS hostname and update `FRONTEND_ORIGIN` to the same origin.

## Cloud deployment requirements

For production, set `APP_ENV=production`, a long random `JWT_SECRET`, a stable private `FIELD_ENCRYPTION_KEY`, a strong database password and the correct HTTPS `FRONTEND_ORIGIN` and `GOOGLE_REDIRECT_URI`. Use a durable PostgreSQL volume, HTTPS reverse proxy, firewall, backups and restore testing. Do not expose PostgreSQL or the API directly to the public internet. The same encrypted credentials and database volume must persist across restarts. Never publish the `.env` file or database backups.

Cloud deployment still requires an account/host, domain or supported HTTPS URL, secure environment-variable entry and live iCloud/Gmail OAuth testing. These credentials and provider approvals cannot be safely guessed or fabricated.

## Safeguards and limitations

- Opening a message marks it read only after provider confirmation.
- Trash is provider-side; permanent deletion is not exposed.
- Reply From is fixed to the original receiving account.
- Sending requires explicit approval and a draft-version check. If the provider's response is uncertain, the draft is locked against blind retry; check Sent first.
- Blocking is app-only, not a provider-level block.
- HTML is not executed. Attachments are detected but not downloaded or extracted.
- Conversations and tasks are stored in this app and are separate from ChatGPT history.
- The current ChatGPT Go plan is not eligible for the official open-source ChatGPT plan-usage route; no API key or paid fallback has been added.

## Checks

Backend: `cd backend && pytest -q`

Frontend: `cd frontend && npm install && npm run build`

The GitHub Actions workflow runs both checks on every push to `main`. Automated checks do not replace real mailbox, OAuth, delivery, backup or device testing.
