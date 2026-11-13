# Delivery checklist — Email Assistant

Status is deliberately conservative. "Built" means code exists in this repository; it does not mean a live provider, deployment or full production test has passed.

## Backend

| Requirement | Status | Notes |
|---|---|---|
| FastAPI API and health endpoint | Built | Containerised. |
| PostgreSQL persistence | Built | SQLAlchemy models and Docker volume. |
| First-run single-user bootstrap | Built | Environment variables. |
| Password hashing and HTTP-only session cookie | Built | PBKDF2-HMAC-SHA256 and signed cookie. |
| Encrypted iCloud app-specific password field | Built | Fernet-derived key; dedicated stable seed required. |
| Multiple email account records | Partial | iCloud starter; Gmail OAuth not built. |
| iCloud 90-day initial IMAP import | Partial | Inbox only, capped at 500 messages/run. |
| Gmail OAuth and incremental history sync | Not built | Google OAuth client and adapter required. |
| Scheduled 08:00, 12:00, 17:00 cloud review | Not built | Worker currently processes queued manual iCloud syncs. |
| Inbox/message records and search | Built | Database search. |
| Provider-confirmed read/unread write-back | Not built | Current read state is local only. |
| Provider-side move to Trash | Not built | Safely returns 501. |
| Attachment extraction and original viewer/download | Not built | Not wired. |
| Internal reply draft create/edit | Partial | Basic database storage. |
| Reply All, source From lock, approval snapshot and idempotent send | Not built | Sending is disabled. |
| Forward composer and sending | Not built | Not wired. |
| Provider/app-level sender blocking | Not built | Not wired. |
| Follow-up list/create/complete/remove | Partial | No AI extraction, edit or snooze. |
| Task record and four priority levels | Partial | Persistence and manual priority endpoint. |
| Hard/Target deadline escalation | Built | Policy function and unit tests. |
| Scheduled task start, dependency graph and three-slot worker queue | Not built | Schedule field exists; scheduler/executor absent. |
| Durable AI task executor/checkpoints/retries | Not built | Existing worker handles sync only. |
| Application-managed AI conversation storage | Built | Database history. |
| Official ChatGPT-plan/SIWC integration | Not built | Account/deployment eligibility must be checked; no API-billing fallback. |
| Apple Notes/Reminders Shortcut bridge | Not built | Requires device bridge and real-device tests. |
| Audit log, rate limits, migrations, backup/restore test | Not built | Required before production. |

## Frontend

| Requirement | Status | Notes |
|---|---|---|
| Responsive React dashboard | Built | Vite + React. |
| Four main navigation sections | Built | Inbox, Follow-ups, AI Assistant, Accounts & Settings. |
| Login screen | Built | API-backed session. |
| Inbox search/list/selected email detail | Built | Basic responsive layout. |
| Current-message and whole-thread summary display | Partial | Displays fields; no AI generation. |
| Original email view | Partial | Imported plain text only; not safe HTML rendering or complete source fidelity. |
| Sync Now | Built | Queues manual sync. |
| Original attachment viewer/download | Not built | Not available. |
| Internal reply draft editor and save | Partial | Basic draft; no version history or full recipient controls. |
| Send/forward/delete/block actions | Not built | Unsupported actions clearly report status. |
| Follow-up list/complete/remove | Partial | Edit, snooze and email trail navigation not built. |
| Persistent AI chat list and messages | Partial | Cannot produce model answers yet. |
| Task panel and priority colour labels | Partial | Shows saved tasks and changes manual priority. |
| Scheduled-start and complete deadline controls | Partial | Deadline entry exists; scheduled-start form and live status updates absent. |
| Accounts/settings | Partial | iCloud form; Gmail OAuth, AI consent and schedule controls pending. |
| Mobile layout | Built | Requires device QA. |

## Required steps before production

1. Clone the repository and copy `.env.example` to `.env`.
2. Set a unique bootstrap email/password, random JWT secret, encryption seed and database password. Never commit `.env`.
3. Run locally with Docker Compose and complete the login/API smoke test.
4. Run `cd backend && pytest` and `cd frontend && npm install && npm run build`.
5. Use HTTPS before remote use. Keep PostgreSQL private; configure monitored backups and test restoration.
6. Connect a test iCloud account with an Apple app-specific password. Do not use the normal Apple ID password.
7. Implement Google OAuth before connecting Gmail.
8. Implement and validate the official ChatGPT-plan/SIWC integration for this exact deployment and account. Obtain explicit consent for each background processing category. No paid API fallback is allowed.
9. Finish provider state write-back, safe send/forward/delete/block, attachments, scheduled email review, durable AI task queue, dependency handling, Apple Shortcuts, audit logging, rate limiting and database migrations.
10. Run security, integration and real-device tests before production.

## Release note

This is a runnable foundation, not the full production application described in the agreed specifications. The system does not fake AI answers, provider delivery, email deletion or Apple actions. Do not use it for live business mail until the outstanding safety-critical items are complete.
