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
- Follow-ups API plus the dashboard filters and controls: All, Action Required, Awaiting Response, overdue state, open linked source email, edit, snooze, mark complete and remove tracking item without changing the email.
- Original attachment listing, source-provider view/download and safe MIME handling, with an integration test confirming attachment viewing does not mark the email read.
- Separate Forward drafts, optional source attachments up to the configured limit, source-account locking, explicit approval and uncertain-send protection.
- App-managed email-thread linking with one-time history backfill, per-message deduplication, automatic append on subsequent mailbox syncs, and unlink/relink history retention.
- Apple Notes/Reminders device enrolment and command queue, including idempotency, device polling/leases and completion receipts.
- Each inbox email card has individual action buttons. Provider-confirmed Mark as Read/Unread, Trash after confirmation, Prepare Reply, and app-only sender blocking are wired. The AI-only card actions show that AI is not connected yet; no canned answer is fabricated.
- On-demand full-thread retrieval from source providers, chronological rendering and explicit partial-history warnings; tests assert thread loading does not change read flags.
- New outbound email composer with explicit From selection, internal draft, approval before sending and uncertainty protection.

### Intentionally not active yet

- AI current-message and entire-thread summaries, AI-generated reply drafting, Ask a Question responses, automatic priority assessment, automatic follow-up extraction/updates, attachment-content analysis, and delegated AI task execution.
- SIWC open-source OAuth/PKCE client, VM credential import/refresh manager, Responses API wrapper, background AI consent UI/record, AI worker and AI workflow implementation are not built yet.
- The Apple Shortcut itself has not been installed/enrolled and tested against a live Mac/iPhone; the server-side command queue alone does not create native Apple Notes or Reminders.
- Live production deployment and real-provider acceptance testing remain pending.
- Do not describe any of these pending capabilities as working features until the relevant approval, device/account setup, implementation and tests are complete.

## AI integration path and safeguards

The earlier handoff incorrectly treated commercial SIWC partner approval as the only way to use ChatGPT plan usage. OpenAI's current developer documentation separately describes an open-source client flow and a self-hosted-VM transfer procedure. This project is MIT-licensed and is a private, single-user open-source application; it will implement the published protocol independently and will not copy or bundle the official DevKit, which is under a Noncommercial License.

### Documented integration shape

1. Prepare a single stable opaque ext_agent_host_id on the AI VM and persist it there before sign-in. Copy the non-secret VM ID to the Mac.
2. On the Mac, run an app-owned loopback callback and OAuth authorization-code flow using the VM's host ID, state, OIDC nonce, PKCE S256, and the documented dynamic client registration (dynamic_agent_client) for first sign-in. Use the issued client ID on subsequent sign-ins; no partner API key or client secret is part of this open-source flow.
3. Request identity scopes and the plan-use permission: openid profile email offline_access resource.invoke chatgpt.tokens.use.direct, with resource=https://api.openai.com/v1.
4. Exchange the authorization code, validate the ID token signature and claims against OpenAI's published JWKS, validate the callback state/nonce and issued client ID, and confirm the token response actually grants chatgpt.tokens.use.direct. A valid identity token alone is not enough to allow inference.
5. Transfer the protected credential file to the user's dedicated self-hosted VM over a secure channel such as SSH/IAP. The importer must verify that ext_agent_host_id matches the VM's already-persisted host ID. The VM stores the credential file on its own local filesystem with owner-only permissions and owns subsequent token refreshes. A rotated refresh token and access-token expiry must be updated atomically.
6. The VM requests only models returned for the user's signed-in account. Inference uses POST https://api.openai.com/v1/responses with store:false, stream:true, and completes only on response.completed.

### Security, consent and limits

- Persistent SIWC tokens never go in Neon/Postgres, Google Secret Manager, Cloud Run environment variables, source control, browser storage, URLs, logs or chat messages.
- The VM must be a dedicated remote runtime the user controls. The credential file must remain local to that VM's filesystem, not a managed secret store. If this condition or current OpenAI terms cannot be satisfied, do not enable plan usage.
- OpenAI explicitly documents the self-hosted VM transfer flow. Its current documentation warns that host-specific usage attribution and revocation for transferred sessions are not yet available.
- The user must expressly authorise background AI work in the OAuth plan-use consent and in the application's own revocable background-processing controls. Each processing category must be disclosed.
- If the required plan-use scope is missing, do not issue inference. If plan usage is ineligible or exhausted, pause AI work and show the actual blocker; do not switch to API billing, credits, another account, another provider or a paid fallback.
- The official open-source Sign in with ChatGPT DevKit is not used or copied because its Noncommercial License excludes business use. The project will implement the documented public OAuth/Responses protocol independently.
- SIWC does not grant access to native ChatGPT chats or memories. Email Assistant conversation history stays in this app's own database.

### Infrastructure and costs

The planned AI worker is a self-hosted VM in the user's own Google Cloud project, separate from Cloud Run and Neon. The Cloud Run service continues to host the dashboard/API and mailbox sync. The VM polls durable AI task records from Neon but keeps SIWC credentials only on its own local disk.

Google's Always Free Compute Engine e2-micro is available only in us-west1, us-central1 or us-east1, includes up to 30 GB-months standard persistent disk and 1 GB/month of outbound transfer from North America. This is not proof that the full VM network path is free. IAP can administer a VM without a public IP, but a separate outbound route is still required. Confirm the billing account, region, egress, IP/NAT and storage costs before provisioning any resource; obtain explicit user approval for any potential charge.

References:
- https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery
- https://developers.openai.com/siwc/token-sharing-open-source/token-reference
- https://openai.com/policies/sign-in-with-chatgpt-terms/
- https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites
- https://github.com/openai/sign-in-with-chatgpt-devkit/blob/main/LICENSE
- https://docs.cloud.google.com/free/docs/free-cloud-features
- https://docs.cloud.google.com/iap/docs/using-tcp-forwarding

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
4. **ChatGPT plan authorisation and VM transfer:** after the independent SIWC client and VM are built, complete sign-in on the Mac, review and explicitly grant plan-use/background permissions, and transfer the protected credentials to the user's VM using the documented secure method. Never share the credential file in chat. This action remains pending; do not enable AI inference before the VM verifies the issued client ID, identity and required scope.

The assistant should continue code, tests and documentation that do not require these actions. Do not stop independent work while any owner action is pending.

## Next engineering priorities

1. Independently implement and test the documented SIWC open-source OAuth/PKCE client, strict ID-token/scope validation, secure local credential-file format and VM import/rotating-refresh path. Do not copy the DevKit.
2. Build the dedicated user-controlled AI VM worker and durable Neon-backed AI job execution; implement the explicit, revocable background AI consent controls. Keep AI inference disabled pending the user's live OAuth consent and VM verification.
3. Implement current-message and whole-thread summaries, contextual reply drafting, Ask a Question, priority assessment, automatic follow-up extraction/update, attachment-content analysis and delegated task execution with source-grounding and usage-limit pause behaviour.
4. Create/install the private Apple Shortcut, enrol the Mac/iPhone, and verify native Note/Reminder creation and receipts end to end.
5. Complete cloud deployment, live iCloud/Gmail provider acceptance, VM cost review, backup/restore checks, rate limits, audit review and public-source security/licence review before relying on critical business email.

## CI and release discipline

- GitHub Actions CI runs on pushes and checks backend tests, frontend production build, deployment-script syntax and the combined Cloud Run Docker image.
- A passing CI run proves the tested code builds; it does not prove deployment, Neon connectivity, mailbox credentials, OAuth approval or actual email delivery.
- After each code change, inspect the newest CI run and only describe it as passing when GitHub reports success.
- Keep secrets, personal email content, attachments, database dumps, logs and provider credentials out of Git.
