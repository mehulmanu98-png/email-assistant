# Google Drive independent backup setup

## What the scheduled workflow does

- Runs every Sunday at 08:00 India Standard Time (02:30 UTC), and can also be started manually from GitHub Actions.
- Dumps the Neon PostgreSQL database in custom format.
- Encrypts the dump with AES-256-CBC and PBKDF2 (600,000 iterations) before it leaves the runner.
- Uploads the encrypted dump and SHA-256 sidecar to the dedicated Google Drive folder.
- Keeps the newest 16 encrypted backup files in that folder. This is a rolling retention policy; it does not yet implement a separate monthly archive tier.
- Uses GitHub-hosted ephemeral runner storage; no backup is stored on Render.

The Google Drive API scope should be `drive.file`, and the OAuth refresh token should be issued only for the Google account/folder intended for this application. The Drive folder must be created by the same authorised account and its folder ID stored in GitHub.

## Required GitHub Actions secrets

Configure these under repository Settings -> Secrets and variables -> Actions -> New repository secret:

- `NEON_DATABASE_URL` (already configured for the existing worker; do not replace it)
- `BACKUP_PASSPHRASE` (new, strong unique passphrase; store it separately in a password manager)
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `GOOGLE_DRIVE_FOLDER_ID`

Never commit these values, put them in workflow YAML, or paste them into chat or logs.

## Google authorisation stage

1. In Google Cloud Console, create/select a project owned by the user and enable Google Drive API.
2. Configure the OAuth consent screen for the user's account. If the app remains in Testing, refresh tokens can expire after seven days for non-basic scopes; move to an appropriate production/publishing state if needed and complete any verification Google requires. Do not assume a testing token will support unattended long-term backups.
3. In Google Auth Platform -> Clients, create a **Web application** OAuth client. Add this exact authorised redirect URI: `https://developers.google.com/oauthplayground`. Do not create a service account and do not share a Drive folder publicly.
4. Create a dedicated folder in your own Google Drive, e.g. `Email Assistant Backups`. Open the folder and copy only the folder ID from its URL (the long value after `/folders/`).
5. Open [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground). Open its settings gear, enable **Use your own OAuth credentials**, and enter the OAuth client ID and client secret from the Cloud Console. In Step 1, enter only this scope: `https://www.googleapis.com/auth/drive.file`. Ensure offline access is requested; if the settings expose access type and consent prompt, use `offline` and `consent`. Authorise with the Google account that owns the backup folder. In Step 2, exchange the authorisation code for tokens. The refresh token is a secret: do not paste it into ChatGPT, a message, or a source file.
6. In GitHub repository Settings -> Secrets and variables -> Actions, add the five new secrets listed above. Keep the existing `NEON_DATABASE_URL` unchanged. Add the client ID, client secret, refresh token and folder ID, plus a long unique `BACKUP_PASSPHRASE`. Save the passphrase separately in your password manager; losing it makes backups unrecoverable.
7. Check the OAuth consent app's publishing status. Google documents that offline access is required for unattended backup and that a refresh token is returned during the offline authorisation flow. An app left in Testing can have refresh tokens expire after seven days for non-basic scopes, so do not treat a Testing-mode token as a permanent unattended setup. Follow Google's current verification/publishing requirements before relying on long-term scheduling.

Google OAuth client creation, consent and token issuance require the user's own Google account interaction. Do not ask the user to disclose a password or OAuth token in ChatGPT.

## First-run acceptance test

1. Confirm all six repository secrets exist (the existing Neon secret plus the five new secrets).
2. Run Actions -> Encrypted Neon backup to Google Drive -> Run workflow.
3. Confirm the run succeeds and both encrypted dump and checksum appear in the dedicated Drive folder.
4. Download the encrypted dump and checksum, verify the SHA-256 checksum, and perform a restore drill only into a separate empty PostgreSQL database. Never test against production.
5. Confirm table counts and app health on the restore target before marking the backup process accepted.

## Important limits

- GitHub Actions scheduled jobs are best-effort and may start later than the cron minute.
- Google Drive storage usage counts against the user's existing Drive quota. This workflow does not purchase storage.
- The workflow currently retains 16 newest backups (roughly four months at weekly cadence); adjust retention only after reviewing actual size and quota.
- A successful upload is not proof of recoverability. The restore drill is a separate required acceptance test.
- The existing manual restore script remains the recovery tool. Supply the target database URL privately and decrypt with the separately stored passphrase.
