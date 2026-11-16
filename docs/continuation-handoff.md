# Email Assistant — Continuation Handoff

**Last reviewed:** 16 November 2026 (Asia/Kolkata)  
**Repository:** https://github.com/mehulmanu98-png/email-assistant  
**Default branch:** `main`

This file is the durable handoff for continuing development when a ChatGPT conversation reaches its length limit. The repository specifications remain the source of approved product requirements: `docs/functional-spec.md`, `docs/architecture.md`, and `docs/ui-spec.md`.

## Product decisions to preserve

- Private, single-user Email Assistant. Public source code does not mean public mailbox data or a public service.
- React + TypeScript frontend; FastAPI backend; Neon PostgreSQL for persistent application data.
- iCloud Mail via IMAP/SMTP and Gmail via Google OAuth/Gmail API.
- Background mailbox sync is independent of the browser/Mac, with default review times 08:00, 11:00, 14:00 and 17:00 Asia/Kolkata.
- Reply All is the default. From remains the source account. Every send requires approval of the final saved draft. Uncertain sends must never be blindly retried.
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
- Neon-backed sync jobs, retry/backoff, stale-job recovery and singleton worker lease.
- Cloud Run deployment script, one-shot Cloud Run Job and Cloud Scheduler setup.
- Follow-ups API plus the dashboard filters and controls: All, Action Required, Awaiting Response, overdue state, open linked source email, edit, snooze, mark complete and remove tracking item without changing the email.

### Intentionally not active yet

- AI summaries/reply generation, automatic follow-up extraction, task execution, attachment download/preview, Forward, automatic project-conversation linking, and Apple Notes/Reminders device bridge.
- These are not to be represented as working features until the relevant backend, user consent, provider integration and tests are complete.

## Important AI integration and licensing blocker

OpenAI's current Help Center says ChatGPT Go, Plus and Pro users may use included plan usage in participating apps that support the feature; availability also depends on the app's own eligibility and approval.

However, the official open-source Sign in with ChatGPT DevKit is under a **Noncommercial License v1.0**. Its definition of Noncommercial Purpose excludes development, testing, distribution or operation by or for a business, employer or client in connection with their operations or commercial advantage, even where no fee is charged. This Email Assistant is intended to process business correspondence. Therefore:

- Do not embed or deploy the official open-source DevKit for this business-use purpose.
- Do not claim that the user's Go plan is categorically ineligible; that statement was corrected in the app.
- The supported next path is to request OpenAI's commercial-integration approval and clarify whether this private, single-user app qualifies, what runtime/token-storage architecture is approved, and which plan-usage permissions are available.
- Until approval is obtained, AI tasks must remain Waiting for User / blocked with a clear reason.
- Do not store SIWC access or refresh credentials in Neon, Google Secret Manager, browser storage, source control, URLs or logs.
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

1. Keep backend/frontend messages truthful about blocked AI capability and commercial approval.
2. Add tests for the Follow-ups edit/snooze/complete/remove routes and UI/API contract.
3. Complete the source-thread view, Forward and safe attachment viewing/download with explicit approval and safe rendering.
4. Design automatic follow-up extraction and app-conversation linking only after the commercial AI route is approved.
5. Design the Apple Notes/Reminders bridge using a user-enrolled Mac/iPhone Shortcut and signed/idempotent command receipts.
6. Finish deployment, provider acceptance, backup/restore checks, rate limiting, audit review and public-source security/licence audit before relying on critical business email.

## CI and release discipline

- GitHub Actions CI runs on pushes and checks backend tests, frontend production build, deployment-script syntax and the combined Cloud Run Docker image.
- A passing CI run proves the tested code builds; it does not prove deployment, Neon connectivity, mailbox credentials, OAuth approval or actual email delivery.
- After each code change, inspect the newest CI run and only describe it as passing when GitHub reports success.
- Keep secrets, personal email content, attachments, database dumps, logs and provider credentials out of Git.
