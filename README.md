# Email Assistant

A private, single-user mail workspace for iCloud Mail and Gmail. It provides a responsive inbox, provider-backed read/Trash actions, saved Reply All drafts, explicit sending approval, follow-ups and task/conversation records.

**Release status:** usable mail-workspace release candidate, subject to one-time provider setup and real-mailbox testing. It is not yet the fully automated AI assistant in the agreed specification. AI summaries, AI-generated replies, automatic follow-up extraction and AI task execution are intentionally disabled.

## Start the app

Requires Docker Desktop with Docker Compose v2.

1. Clone this repository.
2. Configure Google OAuth first if you plan to connect Gmail. See below.
3. From the repository root run `bash scripts/setup-local.sh`.
4. Enter your dashboard email and a unique password. The script generates private secrets and starts the containers.
5. Open http://localhost:8080 and sign in.

The script creates a private `.env` file and refuses to overwrite an existing one. Never commit or share `.env`. API health is at http://localhost:8080/api/health. Stop with `docker compose down`; `docker compose down -v` deletes the database volume.

## Mailbox connections

### iCloud Mail
Use an Apple app-specific password, not your normal Apple Account password. The app imports up to 500 messages from the last 90 days of Inbox per sync. It uses IMAP to import and mark messages read, moves supported messages to the provider's Trash, and sends replies through iCloud SMTP from the original source account.

### Gmail
Create a Google Cloud project, enable the Gmail API, configure the OAuth consent screen, and create an OAuth client ID of type **Web application**. Add this exact authorised redirect URI:

`http://localhost:8080/api/oauth/gmail/callback`

When you run the setup script, enter the client ID and client secret. The app redirects to Google for consent and never asks you to type your Google password into this app. The OAuth flow requests Gmail modify and send permissions, stores refresh credentials encrypted in the private database, and refreshes access tokens server-side.

For a consent screen in **Testing** mode, add your Google account as a test user. Google may limit refresh-token lifetime for external apps in testing; complete the appropriate publishing/verification steps before relying on it long-term.

## Mail synchronisation

The worker syncs mail at 08:00, 12:00 and 17:00 Asia/Kolkata while the worker is running. These are mailbox synchronisation times only. They do not run AI review and do not send notifications. Sync Now queues a manual sync for all connected mailboxes; each account also has an individual sync action. Initial sync imports up to 90 days and 500 messages per account per run.

## Actions and safeguards

- Opening an email changes its read state only after the provider confirms the operation.
- Move to Trash asks for confirmation and updates local state only after provider confirmation. Permanent deletion is not exposed.
- Reply drafts default to Reply All recipients where provider headers expose them. The source From address is locked.
- Sending requires a second confirmation and a check that the saved draft has not changed since it was displayed. A network failure can leave the outcome uncertain; the draft is locked against blind retries. Check the provider's Sent folder before taking further action.
- Block in app hides future messages from a sender in this workspace only; it does not create a provider-level block.
- Message HTML is not executed. Attachments are detected but are not downloaded, previewed or extracted in this release.
- No proactive notifications are configured.

## AI and cost policy

The AI Assistant section stores app-managed conversations and tasks, but does not produce model answers. The current ChatGPT Go plan is not eligible for the official open-source ChatGPT plan-usage integration. The app does not attempt to reuse ChatGPT browser cookies, account sessions or private history, and does not enable OpenAI API billing or a paid fallback. AI review, summaries, reply generation, follow-up extraction and task execution therefore remain disabled.

## Security and deployment

This release is intended for local testing. The repository contains source code only; mailbox credentials, messages and the PostgreSQL database stay in your private local runtime. The generated `.env` has restrictive file permissions. Do not expose the database port publicly. Remote use requires HTTPS, private networking, managed secrets, backups, restore testing, rate limits and a fuller security review. Docker Compose is not a zero-cost 24/7 cloud-hosting guarantee.

## Tests

Backend: `cd backend && pytest -q`

Frontend: `cd frontend && npm install && npm run build`

Specifications: [functional](docs/functional-spec.md), [architecture](docs/architecture.md), [UI](docs/ui-spec.md), [delivery checklist](CHECKLIST.md).
