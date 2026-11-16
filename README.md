# Email Assistant

Private single-user dashboard for iCloud Mail and Gmail. It includes a React interface, FastAPI backend, Neon PostgreSQL storage, provider sync, reply drafts and a cloud-scheduled mailbox worker.

## Background architecture

- **Neon PostgreSQL** stores accounts, encrypted provider credentials, messages, drafts, settings and sync jobs.
- **Google Cloud Run** hosts the dashboard and API from one container. The dashboard can cold-start after idle time; scheduled mailbox jobs are independent of the dashboard.
- **Google Cloud Run Jobs + Cloud Scheduler** execute the one-shot worker every 15 minutes. Cloud Scheduler uses the `Asia/Kolkata` timezone and calls the Cloud Run Jobs API using a dedicated service account. It does not require the MacBook or a GitHub scheduled workflow to be active.
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
- Forwarding uses a separate internal forward draft and explicit approval. It defaults to the original source account, sends outside the source thread, includes the original message text and optionally forwards original attachments within the 25 MB combined in-app limit. Provider acceptance is reported separately from final delivery.
- Manual Sync Now queues work in Neon; the cloud worker checks for queued work every 15 minutes, so a manual sync may not begin immediately.
- The raw message is hidden until you choose **Show original email**.
- An email thread can be linked to an app-managed Email Assistant conversation. Existing imported messages are backfilled once; new synced messages are appended once through a per-message deduplication ledger. Unlinking stops future appends but retains conversation history.
- Gmail threads use the provider's native thread ID. iCloud threads use the root Message-ID from References/In-Reply-To where available; ambiguous older messages may need a manual source-thread check.
- Linked email content is stored as untrusted source material and displayed as escaped text. Attachments are not included in conversation context.
- Background job failures are retried with bounded backoff and interrupted work is recovered.

## AI and other unfinished features

AI summaries, AI-generated replies, automatic follow-up extraction, delegated AI task execution and attachment-content analysis are not active yet. The app currently persists conversations and tasks, but does not generate AI answers or execute delegated AI work.

The following non-AI features are implemented in the current source:
- Original attachment listing, secure viewing and download from the source mailbox.
- Separate forward and new outbound drafts with explicit sender selection, final send approval and uncertain-send safeguards.
- On-demand full-thread retrieval from Gmail/iCloud, shown chronologically with partial-history warnings and without changing mailbox read flags.
- App-managed email-thread linking, one-time history backfill and append-on-sync deduplication.
- Secure Apple Notes/Reminders command queue, one-time device enrolment, device polling and command-result receipts. A real Apple Shortcut still needs to be installed/enrolled and acceptance-tested on a device before native Notes or Reminders creation can be considered live.
- Each inbox email card has its own actions for View Original, Prepare Reply, Mark as Read/Unread, Delete, Block Sender, Summarise Entire Thread and Ask a Question. The two AI actions explicitly report that AI is not connected yet; they do not produce canned or fabricated output.

App-managed conversations and tasks are persisted, but they do not generate AI answers or execute delegated AI work yet.

### ChatGPT plan usage path (implementation pending)

OpenAI publishes an open-source Sign in with ChatGPT flow that lets an open-source app request the direct ChatGPT plan-use scope for eligible Responses API usage. Its self-hosted-VM procedure supports completing sign-in on the user's computer, securely transferring the protected credential file to a remote VM controlled by that same user, then allowing that VM to refresh tokens. This is the route being evaluated for AI work while the MacBook is closed. It is not implemented or connected yet.

The planned separation is:
- Cloud Run / Cloud Scheduler / Neon continue to run the dashboard, email synchronisation, and durable AI task records.
- A dedicated self-hosted VM under the user's own Google Cloud project runs the AI worker and stores its SIWC credential file on that VM's own local filesystem.
- OAuth is completed locally on the user's Mac using the documented loopback PKCE flow. Only the protected credential file is transferred to the VM over SSH/IAP; it is never sent to Neon, Cloud Secret Manager, Cloud Run environment variables, GitHub, the browser, URLs or logs.
- The VM uses the public Responses API with the account-authorised access token, store:false and stream:true; model choices are retrieved from the signed-in account's model catalogue. A response is successful only after response.completed.
- The app checks the granted scope for chatgpt.tokens.use.direct. A normal identity sign-in without that scope does not authorise inference.
- Background AI processing remains disabled until the user expressly authorises it in the app and in the ChatGPT sign-in consent flow. The user can revoke the app connection or disable background processing.
- If ChatGPT plan usage is unavailable or exhausted, AI work pauses. No API key, purchased credits, paid fallback or automatic credit purchase is configured.

The official OpenAI open-source DevKit is under a Noncommercial License and is not bundled or copied into this business-use application. The project will implement the documented public OAuth/Responses protocol independently. Do not assume that open-source availability guarantees plan eligibility: the actual ChatGPT account must grant the plan-use scope, and the exact user-controlled VM deployment must pass a live acceptance test.

Important limitation: OpenAI says transferred self-hosted-VM sessions do not yet have host-specific usage attribution or revocation. Token invalidation must therefore be detected from refresh/Responses failures. See the dedicated SIWC self-hosted VM design (docs/siwc-self-hosted-vm.md).

### Cost and deployment constraint

Google's Compute Engine always-free e2-micro allowance is restricted to specified US regions, with 30 GB-months of standard disk and 1 GB/month of outbound data transfer from North America. It does not establish that the complete VM networking, egress and support setup will cost ₹0. A VM without a public external IP can be administered using IAP, but outbound access still needs a supported network route. We will verify region, connectivity and all billable components before creating anything. No new paid resource will be provisioned without the user's explicit approval.

References:
- OpenAI: Sign in with ChatGPT — self-hosted VMs: https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms
- OpenAI: Sign in with ChatGPT — registration and sign-in: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- OpenAI: Sign in with ChatGPT — models and inference: https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- OpenAI: errors and recovery: https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery
- OpenAI: token reference: https://developers.openai.com/siwc/token-sharing-open-source/token-reference
- OpenAI: Sign in with ChatGPT Terms: https://openai.com/policies/sign-in-with-chatgpt-terms/
- OpenAI Help: using your ChatGPT plan in other apps and sites: https://help.openai.com/en/articles/20001542-using-your-chatgpt-plan-in-other-apps-and-sites
- Google Cloud Free Tier: https://docs.cloud.google.com/free/docs/free-cloud-features
- Google Cloud IAP TCP forwarding: https://docs.cloud.google.com/iap/docs/using-tcp-forwarding

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
