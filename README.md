# Email Assistant

Private single-user dashboard for iCloud Mail and Gmail. It includes a React interface, FastAPI backend, Neon PostgreSQL storage, provider sync, reply drafts and a scheduled mailbox worker. The strict-zero-cost deployment mode uses a local Mac dashboard/API plus GitHub Actions for scheduled mailbox sync.

## Strict zero-cost operating mode (selected project direction)

Do **not** use `scripts/deploy-cloud-run.sh` for this mode. Cloud Run requires a billing account and cannot guarantee a ₹0 bill.

- **Dashboard/API:** run locally on the Mac with Docker Compose using `bash scripts/setup-local.sh`. It is available at `http://localhost:8080` while the Mac and Docker Desktop are running.
- **Database:** use the existing Neon Free project as the shared PostgreSQL database. The local dashboard and GitHub Actions worker must use the same pooled Neon URL and the same `FIELD_ENCRYPTION_KEY`.
- **Scheduled mailbox sync:** the public GitHub repository's Actions workflow runs at 08:00, 12:00 and 17:00 Asia/Kolkata (02:30, 06:30 and 11:30 UTC). GitHub may delay scheduled workflows during busy periods, so these are target times, not exact-time guarantees. The workflow can also be started manually.
- **Required GitHub Actions secrets:** `NEON_DATABASE_URL` (same pooled Neon URL used by the local app), `EMAIL_ASSISTANT_FIELD_KEY` (exact same value as local `FIELD_ENCRYPTION_KEY`), and optionally both `EMAIL_ASSISTANT_GOOGLE_CLIENT_ID` and `EMAIL_ASSISTANT_GOOGLE_CLIENT_SECRET` for Gmail.
- **AI:** disabled. No OpenAI API key, API billing, paid fallback or automatic credit purchase.
- **Important limitation:** scheduled mailbox sync can run while the Mac is off, but the dashboard, manual actions and local API are unavailable until the Mac is awake and Docker is running. Remote iPhone access is not included in this zero-cost local setup.

GitHub Actions scheduled runs on this repository's public standard runners; Neon Free has usage limits. Stay within the free allowances and check Neon usage. This setup avoids Cloud Run and other paid hosting, but no third-party free tier can promise permanent availability or unchanged terms.

### Zero-cost setup steps

1. Confirm the Neon project is on the Free plan and copy its **pooled** PostgreSQL connection URL privately.
2. Clone the repository and run `bash scripts/setup-local.sh` from its root. Enter the Neon URL and choose the dashboard login. The script generates a local encryption key.
3. In GitHub repository **Settings → Secrets and variables → Actions**, add `NEON_DATABASE_URL` with the same pooled URL and `EMAIL_ASSISTANT_FIELD_KEY` with the exact value of `FIELD_ENCRYPTION_KEY` from the local `.env` file. Do not paste either value into chat or commit them.
4. If using Gmail, also add both Google OAuth secrets. iCloud-only use does not require them.
5. Open **Actions → Scheduled mailbox sync → Run workflow** once to test the worker. Confirm a successful run and then check the dashboard at `http://localhost:8080`.
6. Connect a non-critical iCloud mailbox and test import, read/unread, Trash, reply draft and explicit send approval.

The scheduled worker and local dashboard share Neon, so emails synced by GitHub Actions appear in the dashboard when the Mac is running. The local app also has a worker container for manual and catch-up processing while the Mac is awake.

## Optional paid-cloud deployment (not selected)

The Cloud Run deployment script remains in the repository for a future change of direction. It requires a Google Cloud billing account and can incur charges beyond free allowances. Do not run it under the current strict ₹0 decision.

## Local development

Requires Docker Desktop with Docker Compose v2. Run `bash scripts/setup-local.sh` from the repository root and open http://localhost:8080. This setup uses the shared Neon database so scheduled GitHub Actions syncs and the local dashboard see the same messages. The local dashboard/API stop when the Mac is off; the GitHub scheduled worker can continue syncing.

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
