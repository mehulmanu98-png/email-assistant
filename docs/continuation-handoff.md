# Email Assistant — Continuation Handoff

**Last reviewed:** 16 November 2026 (Asia/Kolkata)  
**Repository:** https://github.com/mehulmanu98-png/email-assistant  
**Default branch:** `main`

This file is the durable handoff for continuing development when a ChatGPT conversation reaches its length limit. The repository specifications remain the source of approved product requirements: `docs/functional-spec.md`, `docs/architecture.md`, and `docs/ui-spec.md`.

## Transcript coverage note

The PDF uploaded on 16 November 2026 is only a partial export: it contains 26 PDF pages, while the original ChatGPT transcript's printed page numbering reaches 130. The available extract reaches the beginning of the architecture discussion, so decisions made in the remaining pages have not yet been reviewed. Do not describe this as a complete transcript review.

The uploaded extract specifies 08:00, 12:00 and 17:00 IST. The functional specification also records these as the initial review times. The current code has been aligned to those project-specific defaults. The final product specification explicitly disables proactive notifications, so follow-up and task status is displayed inside the dashboard only.

## Product decisions to preserve

- Private, single-user Email Assistant. Public source code does not mean public mailbox data or a public service.
- React + TypeScript frontend; FastAPI backend; Neon PostgreSQL for persistent application data.
- iCloud Mail via IMAP/SMTP and Gmail via Google OAuth/Gmail API.
- Background mailbox sync is independent of the browser/Mac, with default review times 08:00, 12:00 and 17:00 Asia/Kolkata.
- Reply All is the default. From remains the source account. Every send requires approval of the final saved draft. Uncertain sends must never be blindly retried.
- Forward is a separate saved draft and send flow. It defaults to the source account, includes the original message text, optionally includes original attachments (25 MB aggregate limit), sends outside the source thread and requires explicit approval. Provider acceptance does not prove final delivery.
- Opening an email detail may mark that exact provider copy read only after provider confirmation. Background sync and hidden-original viewing must not silently change read state.
- No proactive notifications.
- App-managed AI conversations are separate from normal ChatGPT conversations and memories.
- No additional AI/API spend: do not configure API billing, paid model fallbacks, ChatGPT credits or automatic credit purchases.
- Delegated task concurrency limit is three; dependencies, priority, deadlines and checkpoints are governed by the functional specification.
- User actions that require account access or device interaction remain visibly pending; independent implementation work continues.

## Current implementation

### Built in the repository

- Responsive four-section dashboard: Inbox, Follow-ups, AI Assistant, Accounts & Settings.
- Single-user login and encrypted provider credentials.
- iCloud mailbox connection, initial 90-day import and resumable sync.
- Gmail OAuth/API integration code; OAuth Web client credentials and callback configuration still need real-account setup.
- Incremental sync and provider message identity/deduplication.
- Provider-confirmed read and Trash operations.
- Reply All draft creation/editing and explicit send approval; uncertain send protection.
- Separate forward draft persistence, editing, optional source-attachment inclusion, source-account locking, explicit approval and uncertain-send protection; Gmail forward MIME has a regression test to ensure it does not reuse the original thread ID.
- Neon-backed sync jobs, retry/backoff, stale-job recovery and singleton worker lease.
- Cloud Run deployment script, one-shot Cloud Run Job and Cloud Scheduler setup.
- Manual Sync Now and first account import commit durable sync jobs and request immediate Cloud Run worker execution using the dashboard runtime service identity; the 15-minute Scheduler trigger remains the fallback.
- Follow-ups API plus the dashboard filters and controls: All, Action Required, Awaiting Response, overdue state, open linked source email, edit, snooze, mark complete and remove tracking item without changing the email.
- Original attachment listing, source-provider view/download and safe MIME handling, with an integration test confirming attachment viewing does not mark the email read.
- Separate Forward drafts, optional source attachments up to the configured limit, source-account locking, explicit approval and uncertain-send protection.
- App-managed email-thread linking with one-time history backfill, per-message deduplication, automatic append on subsequent mailbox syncs, and unlink/relink history retention.
- Apple Notes/Reminders device enrolment and command queue, including idempotency, device polling/leases and completion receipts.
- Each inbox email card has individual action buttons. Provider-confirmed Mark as Read/Unread, Trash after confirmation, Prepare Reply, and app-only sender blocking are wired. The AI-only card actions show the pending commercial approval status without fabricating an answer.

### Intentionally not active yet

- AI current-message and entire-thread summaries, AI-generated reply drafting, Ask a Question responses, automatic priority assessment, automatic follow-up extraction/updates, attachment-content analysis, and delegated AI task execution.
- The Apple Shortcut itself has not been installed/enrolled and tested against a live Mac/iPhone; the server-side command queue alone does not create native Apple Notes or Reminders.
- Live production deployment and real-provider acceptance testing remain pending.
- Do not describe any of these pending capabilities as working features until the relevant approval, device/account setup, implementation and tests are complete.

## Important AI integration and licensing blocker

OpenAI's current Help Center says ChatGPT Go, Plus, Pro and Business users may use included plan usage in participating commercial apps that support it, subject to app eligibility and the user's separate authorization. This Email Assistant is not currently an approved participating app.

The Sign in with ChatGPT Terms effective 4 November 2026 state that persistent Authentication Tokens must be stored locally and under the user's control, not in a remote or managed environment (section 1). ChatGPT plan requests must come from the user's local runtime or a remote runtime that only the user controls, and background use requires express consent (section 3.1). The planned Cloud Run worker therefore cannot assume it may persist SIWC credentials in Neon or Google Secret Manager. Obtain written OpenAI clarification of the specific remote runtime and token-storage model before designing unattended AI processing.

The official open-source Sign in with ChatGPT DevKit is also under a **Noncommercial License v1.0**. Its definition of Noncommercial Purpose excludes development, testing, distribution or operation by or for a business, employer or client in connection with their operations or commercial advantage, even where no fee is charged. This Email Assistant is intended to process business correspondence. Therefore:

- Do not embed or deploy the official open-source DevKit for this business-use purpose.
- Do not claim that the user's Go plan is categorically ineligible; that statement was corrected in the app.
- The supported next path is to request OpenAI's commercial-integration approval and obtain written confirmation that this single-user business-email app qualifies, which runtime model is approved, and how user-controlled token persistence can work with the laptop-off requirement.
- Until approval and an architecture permitted by the current Terms are confirmed, AI tasks must remain Waiting for User / blocked with a clear reason.
- Do not persist SIWC access or refresh credentials in Neon, Google Secret Manager, source control, URLs or logs. Do not assume a remote managed Cloud Run service may persist them; the Terms require persistent token storage to be local and user-controlled.
- Do not work around the licence or hosted-app approval requirements by copying SDK code or moving protected credentials through an undocumented method.
- No OpenAI API billing, credit usage or paid fallback may be enabled.

References:
- https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites
- https://openai.com/form/sign-in-with-chatgpt/
- https://github.com/openai/sign-in-with-chatgpt-devkit
- https://github.com/openai/sign-in-with-chatgpt-devkit/blob/main/LICENSE
- https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms

## Infrastructure state checked on 16 November 2026

### Neon

- Project: `Email Assistant`
- Project ID: `summer-bar-64757607`
- Region: `aws-ap-southeast-1`
- Default branch: `production` (`br-noisy-lake-b3u4an4z`)
- Database: `neondb`
- The branch was ready and the project was on the free-tier organisation when checked.
- A direct table inspection returned no application tables. The FastAPI startup function calls SQLAlchemy `create_all` and adds existing compatibility columns; this should happen when the app first starts successfully against the Neon URL.
- Never paste the Neon connection URI, password or app secrets into this document, chat, source code or issue tracker.

### Google Cloud

- The repository contains `scripts/deploy-cloud-run.sh` and describes the deployment path, but this session did not have access to inspect the Google Cloud project or verify a live deployment.
- The script expects a Google Cloud project with an active billing account and enables Cloud Run, Cloud Build, Artifact Registry, Secret Manager and Cloud Scheduler. It creates runtime and scheduler service accounts, deploys the dashboard/API and one-shot worker, tests worker-to-Neon connectivity, then configures a 15-minute scheduler trigger in Asia/Kolkata.
- Do not claim the application is deployed until the Cloud Run service, worker job, scheduler job and live mailbox tests are verified in the user's Google Cloud console.
- Review the current Google Cloud and Neon usage and set a billing budget alert. Free-tier allowances are conditional limits, not a guarantee of zero cost.

## Owner actions — leave pending until completed

1. **Google Cloud deployment:** confirm/create the Google Cloud project, attach billing, review the costs and budget alert, then run `bash scripts/deploy-cloud-run.sh` from the repository root in Google Cloud Shell or a machine with `gcloud`. Enter the Neon URL and dashboard login only in the private terminal prompts. The script preserves existing persistent secrets on redeployment.
2. **Gmail (only if required):** create a Google OAuth Web client, add the exact callback URI printed by the deployment script, then redeploy with the client ID and secret. Do not put OAuth secrets in Git.
3. **Live acceptance:** sign into the deployed dashboard, connect a non-critical test iCloud mailbox and/or Gmail account, run Sync Now, verify messages, read-state, Trash and a test reply to an address you control. The app has not passed live provider acceptance until this is done.
4. **Commercial AI access:** submit the OpenAI commercial-integration interest form and obtain written approval/architecture requirements before resuming AI integration. No ChatGPT password, browser cookie, session cookie or token file should be shared in chat.

The assistant should continue code, tests and documentation that do not require these actions. Do not stop independent work while any owner action is pending.

## Next engineering priorities

1. Obtain written OpenAI commercial-integration approval and its supported remote-hosted token/usage architecture; until then, keep all AI actions blocked and do not add a paid API fallback.
2. Complete live acceptance of full source-provider thread retrieval (including original Sent messages) against a non-critical iCloud/Gmail account.
3. Create/install the private Apple Shortcut, enrol the Mac/iPhone, and verify native Note/Reminder creation and receipts end to end.
4. After AI approval, implement current-message and whole-thread summaries, contextual reply drafts, Ask a Question, priority assessment, automatic follow-up extraction/update, attachment-content analysis and delegated task execution.
5. Complete deployment, live iCloud/Gmail provider acceptance, backup/restore checks, rate limits, audit review and public-source security/licence review before relying on critical business email.

## CI and release discipline

- GitHub Actions CI runs on pushes and checks backend tests, frontend production build, deployment-script syntax and the combined Cloud Run Docker image.
- A passing CI run proves the tested code builds; it does not prove deployment, Neon connectivity, mailbox credentials, OAuth approval or actual email delivery.
- After each code change, inspect the newest CI run and only describe it as passing when GitHub reports success.
- Keep secrets, personal email content, attachments, database dumps, logs and provider credentials out of Git.
