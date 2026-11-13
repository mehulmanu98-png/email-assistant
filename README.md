# Email Assistant

Private single-user email workspace for iCloud Mail and Gmail, with a responsive inbox, follow-ups and an AI task workspace.

**Current release: runnable foundation, not production complete.** It includes a FastAPI backend, PostgreSQL models, React dashboard, authenticated sessions, encrypted iCloud credential storage, a limited IMAP import path, follow-up/task records and deadline-priority policy. Important integrations remain incomplete; see [CHECKLIST.md](CHECKLIST.md).

## Run locally

Requires Docker Desktop.

1. Clone this public repository.
2. From the repository root, run `bash scripts/setup-local.sh`.
3. Enter your dashboard email and choose a password when prompted. The script generates the remaining secrets, creates a private `.env`, and runs Docker Compose.
4. Open http://localhost:8080 and sign in with the email/password entered in the script.
5. API health endpoint: http://localhost:8000/api/health

The script refuses to overwrite an existing `.env`. Keep `.env` private and never commit it.

Generate a Fernet key seed with:
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
The application derives its Fernet key from the configured seed; keep it stable or encrypted account credentials cannot be decrypted.

Stop with `docker compose down`. Data remains in the Docker volume. `docker compose down -v` deletes the database volume.

## Mail providers

- **iCloud:** Limited IMAP Inbox import using an Apple app-specific password. The worker attempts a 90-day window and imports up to 500 messages per run. Not full folder, thread or provider-state sync.
- **Gmail:** Not available; Google OAuth must be implemented. Never enter a Google password.
- Provider-confirmed read state, Trash, sending, forwarding, blocking and attachment processing are not implemented. Unsupported actions return a clear error rather than claiming success.

## AI and cost policy

No OpenAI API key, paid inference or paid fallback is configured. The chat stores messages but does not generate AI answers. The official Sign in with ChatGPT plan-usage path must be implemented and eligibility verified for the user's account and exact deployment before AI can run. No zero-cost continuous hosting guarantee is made.

## Security

- Single-user bootstrap, password hashing and HTTP-only signed session cookie.
- iCloud credential field encrypted at rest.
- Use HTTPS for remote access, keep PostgreSQL private, configure backups and restrict access.
- Public source code does not make runtime email, attachments, account credentials, database or deployment public.

## Specifications and status

- [Functional specification](docs/functional-spec.md)
- [System architecture](docs/architecture.md)
- [UI specification](docs/ui-spec.md)
- [Backend and frontend checklist](CHECKLIST.md)

See the checklist for the implemented foundation versus required production work.
