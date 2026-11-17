# Email Assistant

Private single-user dashboard for iCloud Mail and Gmail. It includes a React interface, FastAPI backend, Neon PostgreSQL storage, provider sync, reply drafts and a scheduled mailbox worker. The strict-zero-cost deployment mode uses a local Mac dashboard/API plus GitHub Actions for scheduled mailbox sync.

## Free cloud deployment (target: ₹0/month)

The selected deployment target is a **Render Free Web Service** running the existing Docker image, with the existing Neon Free PostgreSQL database and GitHub Actions as the mailbox worker. This makes the dashboard available through a public HTTPS address from phones, tablets and computers without depending on the user's Mac being on.

- **Dashboard/API:** Render Web Service on the Free plan, deployed from this repository using `render.yaml`. The frontend is served by FastAPI from the same origin. The free service may spin down after inactivity; the first visit/request can take time to wake it. It is not an always-on SLA.
- **Database:** keep the existing Neon Free PostgreSQL project. Use its pooled connection URL. Do not create a new database or replace the existing encryption key.
- **Mailbox worker:** GitHub Actions runs the one-shot worker every five minutes and can also be started manually. It checks the configured 08:00, 12:00 and 17:00 Asia/Kolkata sync slots, and drains queued manual sync jobs. GitHub scheduled runs can be delayed; five minutes is a target cadence, not a guarantee.
- **AI:** disabled. No AI API key, paid fallback or automatic credit purchase.
- **Email safety:** outgoing email continues to require explicit user confirmation; Reply All remains the default for replies.
- **Mac requirement:** the Mac is needed only for optional local administration, not for the hosted dashboard or scheduled worker.

### Deployment setup

1. In Render, create a Blueprint from this repository and select the **Free** plan defined in `render.yaml`. Do not upgrade the service or attach a paid instance.
2. Enter the required environment values in Render privately: `DATABASE_URL` (the existing Neon pooled URL), `BOOTSTRAP_EMAIL`, and a strong unique `BOOTSTRAP_PASSWORD`. Render generates `JWT_SECRET` and `FIELD_ENCRYPTION_KEY` for the first deployment. If the app has already stored encrypted mailbox credentials in Neon, the field key must be the exact existing key; never replace it.
3. In GitHub repository **Settings → Secrets and variables → Actions**, add `NEON_DATABASE_URL` with the same pooled Neon URL and `EMAIL_ASSISTANT_FIELD_KEY` with the exact same field key used by Render. Optionally add both `EMAIL_ASSISTANT_GOOGLE_CLIENT_ID` and `EMAIL_ASSISTANT_GOOGLE_CLIENT_SECRET` for Gmail OAuth.
4. Set the GitHub Actions workflow secrets before relying on scheduled sync. Use **Actions → Scheduled mailbox sync → Run workflow** for a manual worker run.
5. Test with a non-critical mailbox: login, initial 90-day import, read/unread, trash, draft, and explicit send approval.

**Important encryption rule:** the database URL and field-encryption key must match between Render and GitHub Actions. If an existing Neon database contains encrypted mailbox credentials, recover and reuse its original field key before deployment. Do not generate a replacement key for existing encrypted data.

**Free-tier limitations:** Render Free services can sleep and have resource/usage limits; Neon Free and GitHub Actions also have limits and terms that may change. This is a best-effort ₹0 configuration, not a promise of uninterrupted uptime. Do not add a payment method or upgrade a service unless the user explicitly approves. Do not deploy to Google Cloud Run under the current zero-spend decision; its deployment script remains for a future separately approved paid/billing-enabled setup.

## Mailbox behaviour

- iCloud uses IMAP and SMTP with an Apple app-specific password.
- Gmail uses Google OAuth and Gmail API; the app never asks for your Google password.
- Initial import covers the last 90 days of Inbox. Sync is resumable in batches of up to 500 messages per run.
- Read-state and Trash are only updated locally after provider confirmation.
- Replies default to Reply All recipient handling where headers permit, allow edits to To/CC/BCC, lock From to the original account, and require a separate send approval.
- New outbound messages require explicit sender-account selection; their drafts are stored in the app and require a separate final send approval.
- Uncertain send outcomes are locked against blind retries; check the source account's Sent folder.
- Forwarding uses a separate internal forward draft and explicit approval. It defaults to the original source account, sends outside the source thread, includes the original message text and optionally forwards original attachments within the 25 MB combined in-app limit. Provider acceptance is reported separately from final delivery.
- Manual Sync Now commits a durable job to Neon. GitHub Actions polls the durable queue on its five-minute worker cadence; a manual workflow run can also process queued work.
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
- The GitHub Actions worker reads only the repository secrets required to connect to Neon and decrypt provider credentials. Keep repository access restricted to trusted collaborators.
- Do not expose the Neon database to unrestricted public access; use the pooled URL, require TLS and rotate credentials if exposed.
- Monitor Neon compute/storage/network quotas and Google Cloud billing. Free limits can suspend or charge depending on the plan/service; they are not a universal zero-cost promise.
- GitHub Actions scheduled workflow is not required for production background processing. CI runs on pushes; the optional manual sync diagnostic is a fallback only.

## Automated checks

Backend: `cd backend && pytest -q`

Frontend: `cd frontend && npm install && npm run build`

CI checks backend tests, frontend production build, deployment script syntax and the combined Cloud Run Docker image. Automated checks do not replace live iCloud/Gmail mailbox and delivery tests.
