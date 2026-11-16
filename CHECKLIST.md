# Delivery checklist — Email Assistant

Status as of the latest code commit. CI passing does not prove live provider or cloud deployment.

| Area | Status | Notes |
|---|---|---|
| React dashboard and FastAPI API | Built | Cloud Run image serves both on one origin. |
| PostgreSQL-compatible database layer | Built | Accepts Neon pooled PostgreSQL URL and adds TLS when absent. |
| User login and encrypted mailbox credentials | Built | Production secrets required; single-user bootstrap. |
| iCloud IMAP inbox import | Built | Initial 90 days; resumable 500-message batches. |
| Gmail OAuth + Gmail API | Built | Google OAuth Web client and redirect URI still need setup. |
| Incremental sync and deduplication | Built | Persisted provider cursors/page tokens. |
| iCloud UID handling for no-Message-ID mail | Built | Uses stored IMAP UID for supported actions. |
| Provider-confirmed read and Trash | Built | Real-account validation pending. |
| Reply All drafts and send approval | Built | To/CC/BCC; From locked; check Sent after uncertain response. |
| User-editable sync times | Built | Timezone-aware due scheduling and grace window. |
| One-shot worker for ephemeral runner | Built | Reclaims stale jobs after interrupted runs. |
| Scheduled worker workflow | Built | GitHub Actions every 15 minutes; requires Neon URL and field key secrets. |
| Neon deployment | Ready for setup | No Neon project/credentials provisioned yet. |
| Cloud Run single-container deploy | Prepared | No Google Cloud account/project/deployment yet; billing account required. |
| GitHub scheduled-run secrets | Scripted | Automatically set by deploy script if GitHub CLI is authenticated; otherwise add manually. |
| No notifications | Built | No proactive notification delivery. |
| AI summaries/replies/task execution | Disabled | Current ChatGPT Go setup not enabled for official plan-usage integration; no API billing. |
| Attachments and Apple Notes/Reminders | Not built | |
| Live provider acceptance test | Pending | Must test with non-critical mailbox. |
| Production audit, backups/restore, rate limits and independent security review | Pending | Complete before relying on critical business email. |

## Deployment acceptance

1. Create Neon project and obtain pooled TLS connection URI.
2. Create Google Cloud project and enable billing; review cost/budget controls before running the deployment script.
3. Run `bash scripts/deploy-cloud-run.sh` from a clone with `gcloud auth login`. The script prompts for secrets without echoing them and stores application secrets in Google Secret Manager.
4. Add the printed Google OAuth callback URI to the Google OAuth Web client.
5. Sign into Cloud Run dashboard; connect test iCloud and Gmail accounts.
6. Confirm GitHub Actions secrets `NEON_DATABASE_URL` and `EMAIL_ASSISTANT_FIELD_KEY` exist. Manually run **Email mailbox background sync** once and verify a successful job against Neon.
7. Check that scheduled runs complete, email records appear in the dashboard, and a test reply works for each provider.
8. Review Google Cloud billing and Neon usage after initial operation. Free allowances are limits, not an assurance of zero cost.

No live deployment or mailbox access is claimed until the user completes the account/credential setup and a real provider test succeeds.
