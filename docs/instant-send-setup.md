# Immediate email delivery setup

The Email Assistant keeps outgoing email in Neon until a background worker sends it. The API now supports triggering a dedicated send-only GitHub Actions run immediately after the user presses Send.

## Required Render environment variable

Add this variable to the Email Assistant backend service in Render:

- `GITHUB_WORKER_TOKEN`: a GitHub fine-grained personal access token.

The repository is already configured in the application as `mehulmanu98-png/email-assistant`, with the worker ref set to `main`. These defaults do not need to be changed unless the repository or branch changes.

## Create a least-privilege token

1. Open GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens.
2. Generate a token with access limited to the single repository `email-assistant`.
3. Under Repository permissions, grant **Actions: Read and write**. No other repository permissions are required for workflow dispatch.
4. Set an expiry and store the token in a password manager.
5. Add it to Render as `GITHUB_WORKER_TOKEN`. Do not paste the token into ChatGPT, source code, GitHub commits, or application logs.
6. Redeploy/restart the Render backend so the new environment variable is loaded.

## How delivery works

1. The API validates the saved draft, recipient list, source account and explicit Send action.
2. It commits the immutable draft as `queued` in Neon.
3. If `GITHUB_WORKER_TOKEN` is configured, the API dispatches the `mail-sync.yml` workflow with `send_only=true`.
4. The send-only worker processes approved outgoing drafts without waiting for the five-minute mailbox polling schedule.
5. The worker marks the draft `sent` only after the provider accepts the SMTP/API submission. Uncertain outcomes are not automatically retried, to avoid duplicate emails.

The GitHub Actions dispatch is asynchronous. Actual delivery time depends on GitHub runner availability and the mail provider's response. If the token is not configured or dispatch fails, the durable queue remains available to the existing scheduled worker.

## Manual verification

- Send a test email to an address you control.
- Confirm the UI initially shows `QUEUED`.
- Open the GitHub Actions run named **Scheduled mailbox sync** and confirm the **Process approved outgoing emails immediately** step ran.
- Confirm the draft changes to `SENT` after provider acceptance.
- Check the receiving mailbox, including Spam, and the sending account's Sent folder.
