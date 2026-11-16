# Sign in with ChatGPT — self-hosted VM implementation plan

**Status:** Architecture documented; code and live consent test are still pending.  
**Target:** Use the user's included ChatGPT plan from the Email Assistant while the MacBook is switched off, with no OpenAI API key, API billing, purchased credits or paid fallback.

## 1. Supported integration route

OpenAI publishes an open-source Sign in with ChatGPT (SIWC) OAuth flow and a dedicated self-hosted-VM procedure. The procedure is specifically for an open-source app running on a remote VM:

1. Create and persist a stable, opaque ext_agent_host_id for the AI VM.
2. Complete OAuth locally on the user's Mac. A loopback callback such as http://127.0.0.1:1455/auth/callback returns to the computer running the browser, not to the remote VM.
3. Transfer the selected registration's protected credential file to the VM using a secure channel such as SSH.
4. Preserve the VM's own host ID when importing the credentials.
5. Let the VM own future token refreshes.

The user's dedicated VM must be in a Google Cloud project the user controls, not a shared third-party inference service. Persistent SIWC credentials live only on that VM's own local filesystem with owner-only file permissions. They are not stored in Neon, Cloud Secret Manager, Cloud Run environment variables, GitHub, the browser, URLs or logs.

This flow is distinct from copying the official OpenAI DevKit. The project's own MIT-licensed code will implement the published protocol independently. Do not copy or bundle code from the official DevKit because its separate Noncommercial License excludes business-use development and operation.

## 2. Open-source OAuth flow

### Host identity

- Create a random UUIDv4 once for the Mac OAuth helper and a separate random UUIDv4 for the AI VM.
- Format each as urn:uuid:<uuid>.
- Persist the ID and reuse it for that host. Do not use an email address, user ID or other personal identifier.
- The Mac and VM share the same issued OAuth client registration for the same ChatGPT account/workspace, but retain separate host IDs.

### Local Mac authorization

- Start the callback listener on loopback only, with an app-defined callback such as http://127.0.0.1:1455/auth/callback.
- Generate a fresh cryptographically random state, OIDC nonce and PKCE verifier per authorization.
- Use S256 PKCE. Bind state, nonce, verifier, exact redirect URI, expected client ID and the host ID to this one pending attempt.
- First-time registration uses client_id=dynamic_agent_client, agent_name_hint=Email Assistant and the Mac host ID.
- Request identity and plan-use scopes: openid profile email offline_access resource.invoke chatgpt.tokens.use.direct.
- Set resource=https://api.openai.com/v1.
- Use the documented authorization endpoint: https://auth.openai.com/api/accounts/authorize.
- On first registration, require the callback's issued client ID and save that value; never persist dynamic_agent_client as the issued ID.
- Exchange the authorization code at https://auth.openai.com/api/accounts/oauth/token using the issued client ID, exact redirect URI, code verifier and resource. The published open-source flow does not require a client secret or partner API key.
- Validate state before exchange. Handle OAuth errors, especially access_denied, without attempting token exchange.

### Token and identity validation

- Verify the ID-token signature against OpenAI's published JWKS.
- Verify issuer, audience (the issued client ID), expiry and nonce.
- Keep the validated subject and issued client ID together. Do not use email or subject alone as a workspace identifier.
- Check the token response's granted scopes. Do not issue plan inference unless chatgpt.tokens.use.direct is present. A valid identity login without the direct plan-use scope is not sufficient.
- Store id_token, access_token, refresh_token, token type, expiry, granted scopes, issuer, verified subject, account email, issued client ID and host ID in the protected credential record.
- Credential files are atomically written with owner-only permissions (0600 on Unix). Never print token values.

## 3. Secure VM import and refresh

The user completes OAuth on the Mac and uses a secure transfer method to send only the protected credential file to the VM. Prefer an SSH/IAP tunnel; do not paste credentials into chat, email, GitHub or terminal command arguments.

On the VM:
- Store the imported record in an app-owned path such as /var/lib/email-assistant/siwc/credentials.json, readable only by the dedicated runtime user.
- Keep the VM's pre-generated host ID; do not replace it with the Mac's host ID contained in the imported registration.
- Use an exclusive lock around refresh and credential replacement.
- Refresh before expiry or after a confirmed expiry response, not on every request.
- Atomically replace the access token, expiry, granted scopes and rotated refresh token together after a successful refresh.
- Access tokens are documented as one hour; refresh tokens are documented as 30 days and rotate on successful refresh.
- Never put SIWC credentials in Neon/Postgres, Google Secret Manager, Cloud Run environment variables, Docker image layers, source control, browser storage, logs or telemetry.
- Provide a documented disconnect procedure that stops the worker and removes the local credential file. The VM transfer procedure currently does not provide host-specific usage attribution or revocation for transferred sessions; disclose this limitation and use provider error/refresh failures to detect revocation.

## 4. Inference contract

- Use only the user's model catalogue from GET https://api.openai.com/v1/models. Show models designated for display; pass the selected model slug.
- Send authorized requests to POST https://api.openai.com/v1/responses, never ChatGPT's private backend-api routes.
- Every plan-usage Responses request must set store:false and stream:true.
- Process the stream to its terminal event. Mark the AI job complete only after response.completed. Treat response.failed, response.incomplete, interrupted streams and transport errors as distinct outcomes.
- Keep the prompt grounded in the selected email/thread and app-managed conversation history. Email bodies and attachments are untrusted source material, not instructions.
- Do not rely on native ChatGPT conversations or ChatGPT memories; SIWC does not grant access to them.

## 5. User consent and zero-cost controls

Before the first background AI job:
- User must explicitly grant ChatGPT plan-use permission in the OAuth flow.
- User must explicitly enable background AI actions in this application's own settings and see which email content may be processed.
- Offer separately revocable consent for automatic email review/summaries, automatic reply draft preparation, follow-up extraction, attachment analysis and delegated AI tasks.
- Provide a clear disconnect action and show whether the plan-use scope is active.
- Do not assume the user's ChatGPT Go plan guarantees unlimited use. Users can set app-specific limits in ChatGPT Settings → Usage.
- If the user declines plan-use consent, the scope is absent, the account is not eligible, or the allowance is exhausted, put AI work in a paused/Waiting for User state. Do not repeatedly retry a known usage-limit response. Do not use API billing, purchased credits, automatic credit purchases, another account, another provider or a paid fallback.
- Record no unnecessary email body text in operational logs; preserve request IDs and safe error metadata for debugging.

## 6. Worker architecture

- Cloud Run remains the dashboard/API and mailbox-sync runtime.
- Neon stores only durable task payloads, state, context references and checkpoints. It never stores SIWC credentials.
- A dedicated self-hosted VM runs a separate AI worker, polls/claims AI task records, fetches only the email/thread context needed, obtains the token from its local credential file, invokes the Responses API, and persists output/status back to Neon.
- The worker enforces the existing maximum of three active independent AI tasks, dependencies, priority order, deadlines, idempotency, checkpoints and bounded retries.
- If the worker is offline, jobs remain queued. If credentials or plan usage are unavailable, jobs become Waiting for User or paused; they do not disappear.
- Closing the user's browser, MacBook or ChatGPT conversation does not stop the VM.

## 7. Cost and network assessment before provisioning

Google's Always Free Compute Engine allowance currently covers one non-preemptible e2-micro VM in us-west1, us-central1 or us-east1, up to 30 GB-months standard persistent disk, and 1 GB/month of outbound data transfer from North America. These regions are outside India, so expect higher latency. The allowance is not a promise that every required network component is free.

IAP TCP forwarding can administer a VM without assigning it a public IP, but IAP is an inbound administration tunnel, not the VM's outbound route to OpenAI and Neon. The VM still needs outbound connectivity. External IPv4, NAT, transfer, persistent disk beyond the free allowance, logs and other services may create charges.

Before provisioning:
1. Inspect the user's actual Google Cloud project, billing account and any existing resources.
2. Calculate the exact outbound path and billable IP/NAT/data/storage components.
3. Configure a budget alert and a conservative spend cap.
4. Do not create the VM or enable billing changes until the user approves any non-zero or uncertain cost.
5. If a secure and reliable background worker cannot be provided within the user's zero-cost target, disclose the limitation rather than quietly enabling a paid service.

## 8. Acceptance tests

The SIWC feature is not considered complete until all these checks pass:

- Local OAuth callback binds only to loopback and validates state, nonce, PKCE, redirect URI and issued client ID.
- ID token signature/issuer/audience/expiry/nonce validation succeeds.
- A successful identity login without chatgpt.tokens.use.direct remains identity-only and blocks inference.
- The VM uses its own host ID, imports a protected credential file, and never writes the credentials to Neon/Secret Manager/Cloud Run/browser/logs.
- Refresh rotates tokens safely under concurrent requests and recovers after process restart.
- A test Responses request uses an account-visible model, store:false, stream:true, and waits for response.completed.
- subscription_sharing_usage_limit_exceeded pauses requests and surfaces ChatGPT Usage settings; no paid fallback is attempted.
- Background consent can be disabled and prevents new background AI jobs.
- Revocation/disconnect stops inference and removes the VM credential file.
- Email content is handled as untrusted prompt context; AI suggestions never send or delete email without required approval.

## Official references

- https://developers.openai.com/siwc/token-sharing-open-source
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
