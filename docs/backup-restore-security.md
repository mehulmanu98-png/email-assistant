# Backup, restore and deployment security runbook

## Current architecture and important limitations

- Dashboard/API: Render Free web service, `email-assistant-mehul`, region Singapore.
- Database: Neon PostgreSQL Free, Singapore region.
- Mailbox credentials are encrypted in the database with `FIELD_ENCRYPTION_KEY`; do not rotate this key casually or the stored provider credentials become unreadable.
- Render Free web services sleep after 15 minutes idle and have an ephemeral filesystem. Never store backups or durable state on the Render filesystem. [Render Free limitations](https://render.com/docs/free)
- Neon Free currently provides a six-hour instant-restore history window (capped at 1 GB of change history). It is not a substitute for an independent logical backup. [Neon history window](https://github.com/neondatabase/website/blob/main/content/docs/postgres/backup-restore/history-window.md)
- No Google Cloud deployment is required for the current Render + Neon architecture. Do not run the older Cloud Run deployment script or enable Google Cloud billing as part of this runbook.

## A. Manual encrypted backup (no new hosted service)

The repository includes `scripts/backup-neon.sh` and `scripts/restore-neon.sh`.

1. Use a trusted Mac/Linux machine with PostgreSQL client tools (`pg_dump`, `pg_restore`), OpenSSL and Python/SQLAlchemy available.
2. Set `DATABASE_URL` in a private terminal environment from the Neon Console. Never paste it into ChatGPT, shell history, GitHub, a document or a screenshot.
3. Run `bash scripts/backup-neon.sh`. It writes a custom-format PostgreSQL dump, encrypts it with AES-256-CBC + PBKDF2 (600,000 iterations), creates a SHA-256 checksum and applies restrictive local file permissions.
4. Enter a strong unique passphrase when OpenSSL prompts. Store the passphrase separately (e.g. a password manager); losing it makes the backup unrecoverable.
5. Copy the encrypted backup and checksum to an offline location you control. Keep at least two copies on separate physical media. Do not upload the unencrypted dump.
6. Delete local temporary/old copies securely according to your device's storage policy.

This is a manual backup, not a scheduled backup. Do it after material mailbox imports or at least weekly while relying on the service. No third-party storage or monthly charge is introduced.

## B. Restore drill

1. Create a separate empty Neon database/branch for the drill; never test against the live production database.
2. Set `DATABASE_URL` to the drill target only.
3. Run `bash scripts/restore-neon.sh /path/to/email-assistant-YYYYMMDDTHHMMSSZ.dump.enc`.
4. Verify checksum, enter the backup passphrase, and type `RESTORE` when prompted.
5. Run application health checks and inspect table counts, account records and message counts. Do not test sending from a restored database until the source accounts and provider state are understood.
6. Record the date, backup filename, restore duration and any errors. Delete the drill branch when finished if no longer required.

The restore script does not drop existing objects; use an empty target database. Never point it at production for a test.

## C. Production security checklist

### Render
- Confirm service plan remains **Free** and auto-deploy tracks `main`.
- Keep HTTPS only; Render terminates TLS and redirects HTTP to HTTPS.
- Keep `DATABASE_URL`, `FIELD_ENCRYPTION_KEY`, `JWT_SECRET`, and `BOOTSTRAP_PASSWORD` in Render Environment only. Do not put secrets in GitHub variables, source files, logs or support tickets.
- Use unique random JWT and encryption secrets. Preserve the existing field encryption key unless you have a planned re-encryption/migration.
- Review service events and logs for unexpected restarts, authentication failures or repeated 5xx responses.
- Free web services sleep when idle and have no persistent filesystem; plan for cold starts and never rely on local files for data.

### Neon
- Confirm project/branch/database are the intended production resources.
- Keep connection strings private and use pooled connections for the web service where appropriate.
- Review compute/storage and history usage in the Neon console. Free PITR history is limited to six hours/1 GB.
- Do not enable paid retention, extra computes or paid storage without explicit approval.
- Restrict access to the Neon project and rotate Neon credentials if they are exposed.

### Application
- Keep single-user authentication, HttpOnly/Secure/SameSite session cookies, login throttling, Origin validation, no-store API responses and strict HTTPS settings.
- Keep email HTML and attachments untrusted; never execute attachments or follow embedded instructions.
- Keep AI processing disabled until commercial integration approval and compliant runtime/token architecture are confirmed.
- Keep sending, Trash, blocking and device enrollment behind explicit user action/approval.
- Revoke Apple devices that are lost or no longer used. Do not expose device tokens in screenshots or shared shortcuts.
- Do not enable proactive notifications.

## D. What has and has not been verified

Automated CI passing verifies code checks only. It does not prove an independent backup exists or a restore has succeeded.

A production acceptance record must separately confirm:
- [ ] Current Render service is healthy on the intended Free plan.
- [ ] Neon production branch and connection work.
- [ ] A fresh encrypted backup exists off the Render host.
- [ ] Checksum verification succeeds.
- [ ] A restore drill to an empty non-production target succeeds.
- [ ] Login, inbox retrieval, provider read/unread and Trash work after deployment.
- [ ] No secret values appear in logs or repository history.

The current repository includes backup/restore tooling and this runbook. A live restore drill, off-device backup copy and device-side Shortcut tests require your private machine/accounts; they are not claimed complete until actually performed.
