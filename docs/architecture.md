# Email Assistant — System Architecture

**Architecture version:** 1.1  
**Status:** Approved direction for implementation  
**Product:** Private, cloud-hosted email workspace and AI task assistant

## 1. Product boundaries

- One cloud backend runs email synchronisation and delegated AI task execution.
- One responsive dashboard is accessible from Mac and iPhone.
- The user's browser, Mac, and open ChatGPT conversation are not required for cloud email processing or ordinary delegated tasks to continue.
- Native Apple Notes and Reminders creation is a device-side exception: the cloud queues an authenticated command, and an enrolled Apple Shortcut on an available Mac/iPhone executes it.
- No push, email, WhatsApp, SMS, desktop, or other proactive notification delivery.
- Initial mailbox import is the most recent 90 days per account; older mail is retrieved on demand where provider APIs permit.
- Supported mail providers: multiple iCloud Mail accounts and multiple Gmail accounts.
- AI preference: ChatGPT/OpenAI models, using supported OpenAI API or eligible ChatGPT Apps integration. The application must disclose API billing separately if API use is selected.

## 2. High-level architecture

```mermaid
flowchart TB
  subgraph CLIENTS["User interfaces"]
    WEB["Responsive React dashboard"]
    MAC["Mac browser"]
    PHONE["iPhone browser"]
    MAC --> WEB
    PHONE --> WEB
  end

  subgraph CLOUD["Always-on cloud application"]
    API["FastAPI application/API"]
    AUTH["Authentication and authorisation"]
    DB[("PostgreSQL")]
    QUEUE["Durable job queue"]
    SCHED["Cloud scheduler"]
    WORKER["Background worker pool"]
    AI["OpenAI / ChatGPT models"]
    AUDIT["Audit and task event records"]
  end

  subgraph PROVIDERS["External providers"]
    ICLOUD["iCloud Mail via IMAP/SMTP"]
    GMAIL["Gmail API + Google OAuth"]
    APPLE["Enrolled Apple Shortcut"]
    NOTES["Apple Notes"]
    REMINDERS["Apple Reminders"]
  end

  WEB <--> API
  API <--> AUTH
  API <--> DB
  API --> QUEUE
  SCHED --> QUEUE
  QUEUE --> WORKER
  WORKER <--> DB
  WORKER <--> ICLOUD
  WORKER <--> GMAIL
  WORKER <--> AI
  WORKER --> AUDIT
  API --> AUDIT
  API <--> APPLE
  APPLE --> NOTES
  APPLE --> REMINDERS
```

## 3. Application components

### Frontend
- React + TypeScript responsive web interface.
- Four main areas: Inbox, Follow-ups, AI Assistant, Accounts & Settings.
- Three-column desktop Inbox; responsive email list/detail flow on mobile.
- All sensitive actions call authenticated backend APIs. The frontend never receives provider passwords, refresh tokens, or OpenAI secrets.

### API/backend
- Python + FastAPI.
- Authenticates users and devices, validates requests, applies permission rules, and orchestrates application modules.
- Modules: account management, provider adapters, message sync, duplicate detection, thread resolver, summary/draft generation, priority, attachments, follow-ups, AI tasks, Apple command queue, audit and settings.

### Database
PostgreSQL is the durable source of truth for application state.

Core entities/tables:
- users, sessions, authorised_devices
- email_accounts, provider_tokens/secret references
- messages, provider_message_copies, attachments
- threads, cross_account_duplicate_groups
- ai_summaries, ai_drafts, draft_versions
- ai_conversations, email_thread_ai_links, ai_conversation_items
- follow_ups, follow_up_events
- delegated_tasks, delegated_task_steps, task_events, idempotency_records
- apple_commands, apple_command_attempts
- sync_cursors, sync_runs, audit_events
- account_review_schedules, user_preferences

Do not store raw provider credentials or OpenAI API keys in ordinary database rows. Use encrypted secret storage or a managed secret manager and store only secret references in the database.

### Durable job queue and background worker
- Use a durable queue backed by PostgreSQL or a managed queue service.
- A cloud scheduler enqueues account sync jobs at the configured times (default 08:00, 12:00, 17:00 Asia/Kolkata).
- Manual Sync Now enqueues the same idempotent sync pipeline.
- Gmail change notifications can enqueue incremental sync jobs; iCloud may use IMAP IDLE if supported by the chosen server/connection, with polling fallback.
- Worker processes jobs independently of browser/ChatGPT session state.
- Delegated AI tasks are persisted and scheduled as jobs, not held in an in-memory request or browser session.
- A worker orchestrates discrete steps and invokes the OpenAI model when needed. The OpenAI model itself is not assumed to be a continuously running worker.
- Jobs are checkpointed. They can safely resume after process restart or deployment.
- Use idempotency keys, deduplication, bounded retries, exponential backoff, and a dead-letter/failed state.
- Long jobs must have timeouts and step limits. Human approval or missing information moves a job to Waiting for User.

## 4. Email provider adapters

### iCloud Mail
- Connect using the supported IMAP/SMTP path and an Apple app-specific password.
- Store the app-specific password in deployment secret storage.
- Use IMAP UIDs and RFC Message-ID where available for identity/deduplication.
- Verify IMAP IDLE capability before relying on it; otherwise poll.
- Read/unread, move-to-trash, drafts and send operations must be checked against provider response.

### Gmail
- Use Gmail API and Google OAuth, not the user's Google password.
- Store OAuth refresh tokens securely server-side.
- Use Gmail thread IDs, message IDs and history IDs for incremental synchronisation.
- Google watch/Pub/Sub may be used for change detection, with scheduled renewal and polling/repair sync as a fallback.
- Request only required OAuth scopes and complete Google's OAuth verification/production process as applicable.

### Provider-neutral message model
- Each mailbox copy has its own provider/account identity and state.
- Same email copies can be visually grouped only when high-confidence duplicate identity is established.
- Grouping does not combine read state, deletion, flags or provider operations.
- Actions from a visually grouped card are scoped to the selected account copy unless the user explicitly requests a multi-account action.

## 5. Sync and AI processing pipeline

```mermaid
flowchart TD
  A["Scheduler / Sync Now / provider change event"] --> B["Enqueue account sync job"]
  B --> C["Fetch changed messages"]
  C --> D["Deduplicate by provider identity"]
  D --> E["Resolve thread identity"]
  E --> F["Persist provider copy and metadata"]
  F --> G["Analyse supported attachments"]
  G --> H["Generate current-message summary"]
  G --> I["Update whole-thread summary"]
  H --> J["Assess priority"]
  I --> J
  J --> K["Generate internal reply draft"]
  K --> L["Extract or update follow-ups"]
  L --> M["Append to linked AI conversation once"]
  M --> N["Update dashboard state"]
```

- First import covers the last 90 days per account and is resumable.
- Older mail can be fetched on demand.
- Incremental sync uses provider cursors/history after the initial import.
- Background summarisation, attachment analysis or draft generation does not mark an email read.
- Opening an email detail in the portal marks that exact source copy read in its provider; provider confirmation is required.
- Provider-side read changes are reflected at the next sync.
- Each incoming email gets a current-message summary, separate whole-thread summary, priority assessment and an internal draft record (or explicit "reply not recommended" state).
- AI must be grounded in retrieved content; missing/truncated data must be disclosed.

## 6. Persistent AI conversations and automatic email trail updates

- Application-managed AI conversations use supported OpenAI conversation-state APIs.
- Database maps provider + account + thread identity to the relevant OpenAI Conversation ID.
- On every new message in a linked thread, a worker verifies identity, prevents duplicates, appends the new email context once and triggers summary/task reassessment.
- AI conversations in this application are not represented as arbitrary native ChatGPT history conversations. Native ChatGPT history modification must not be claimed without a supported product integration.

## 7. Delegated AI task execution

### Durable task lifecycle
- User assigns a task in the AI Assistant.
- API validates the request and creates a durable task record with a unique ID, scope, linked email/thread references, status, and plan/steps.
- Task scheduler enqueues the task.
- Background worker claims the job, records a lease/heartbeat, and executes each approved step.
- After each step, the worker persists checkpoint, result reference, status and updated progress.
- User closing the dashboard, browser, or related ChatGPT conversation does not cancel or pause the task.
- Worker restart/deploy does not lose progress. Expired leases are safely reclaimed.
- User can return from another device and see saved status and task updates.

### Task states
- Queued
- In Progress
- Waiting for User
- Completed
- Failed
- Cancelled

### Execution safeguards
- Each step has idempotency key and retry policy.
- Use bounded retries with backoff; permanent errors move to Failed with actionable explanation.
- If user input, account reconnect or approval is needed, move to Waiting for User and save a resumable checkpoint.
- Sending email, permanent deletion, sender blocking changes and other consequential actions pause for required approval.
- User can pause/cancel eligible tasks.
- Never fabricate progress. Only report persisted worker status and completed steps.
- No proactive notifications. The dashboard displays task changes when opened/refreshed.

## 8. Apple Notes and Reminders bridge

- Cloud parses natural-language reminder/note instruction and stores an authenticated, device-targeted Apple command.
- If no authorised device is available, leave it Pending on Device.
- An enrolled Mac/iPhone Shortcut polls/receives eligible commands, validates one-time credentials, performs native Apple action and returns a signed/validated result.
- Mark Completed only after confirmed Shortcut result.
- Commands are idempotent to prevent duplicate notes/reminders.
- Cloud task execution can continue while device is offline, but native Apple action cannot complete until a compatible device runs the Shortcut.

## 9. Security boundaries

- HTTPS, authentication, secure sessions and least-privilege access.
- OAuth tokens and app-specific passwords stored in a managed secret manager.
- Encryption at rest and in transit; database access restricted to the application.
- Restrict CORS to production dashboard origin.
- CSRF protection for state-changing browser operations.
- Safe rendering of untrusted email HTML and attachments.
- AI instructions embedded in email content must never override app/system instructions.
- No secrets or message bodies in source control or routine logs.
- Require approval for consequential operations.
- Record action/task audit metadata without retaining unnecessary message contents.
- Private dashboard; no public registration in initial version.

## 10. Proposed implementation sequence

1. Consolidate requirements and API contracts.
2. Backend skeleton, database migrations, authentication and secrets.
3. Deploy private dashboard and API.
4. Implement iCloud and Gmail account connections.
5. Implement initial 90-day import and incremental sync.
6. Implement unified inbox, provider state reconciliation and attachments.
7. Implement OpenAI summaries, priority, internal drafts and persistent AI conversations.
8. Implement follow-ups and durable delegated task worker.
9. Implement email action endpoints and approval gates.
10. Implement Apple Shortcut bridge.
11. Add observability, recovery, rate limiting, security tests and end-to-end tests.


## 11. Task priority queue and bounded parallel execution — approved

- The task scheduler uses a priority-aware queue and a bounded worker pool.
- Run **up to three independent delegated AI tasks concurrently** for this user's workspace.
- This is a maximum concurrency limit, not a requirement to run three tasks at all times.
- Tasks with dependencies must execute in dependency order. A task step cannot start until its prerequisite steps are confirmed complete.
- Independent tasks may run in parallel, subject to the maximum of three active tasks.
- Tasks waiting for user input/approval, paused by the user, or waiting for an external Apple device do not occupy an active AI worker slot.
- The scheduler prioritises queued tasks by priority: Urgent, High, Normal, Low. Within the same priority, use FIFO ordering unless a valid due-time rule is explicitly configured.
- A higher-priority task may move ahead of queued lower-priority tasks, but must not abruptly interrupt a running step. Running tasks pause only at safe persisted checkpoints when necessary.
- Enforce per-user and provider/API rate limits, bounded retries, backpressure and fair scheduling. Do not exceed the concurrency cap to work around rate limits.
- The concurrency limit must be configurable by deployment operator for future capacity tuning, with **3** as this user's approved default.
- Surface queued position, task priority, active/queued state, dependencies, current step and persisted progress in the task UI.


## 11. AI task scheduling and worker concurrency — approved policy

### Approved concurrency
- Initial maximum: **three independent delegated AI tasks executing concurrently** across the user's workspace.
- Enforce the cap in the backend worker scheduler using a durable queue and database-backed task leases/semaphores. Never rely on frontend/browser state to enforce concurrency.
- Independent tasks may run at the same time while active slots are available.
- Tasks with dependencies are represented as a dependency graph or ordered steps and only become eligible after prerequisites succeed.
- Waiting-for-user tasks release their active worker slot; unrelated queued tasks may then proceed.
- Completed, cancelled and terminally failed tasks release their slots.
- Limit is operator-configurable for hosting/API cost management, with three as the approved initial setting.

### Priority-aware scheduling
- Persist a priority field on every task; default to Normal.
- Priority may be set by the user or by an explicit AI planning rule, and can be changed by the user.
- Select eligible queued work by priority first, then FIFO order within the same priority.
- Priority changes affect queued work only; do not pre-empt a running task in the initial implementation.
- Tasks at a higher priority still respect dependencies and the three-task concurrency cap.
- When all slots are occupied, additional tasks remain Queued with their priority and queue position visible.

### Reliability and visibility
- Persist queue state, lease/heartbeat, checkpoints, attempt count, last error and timestamps.
- Resume safely after worker restart or deployment.
- Use idempotency keys, bounded retries with backoff, and a clear terminal Failed state.
- Show active task slot usage and queued task count in the AI Assistant dashboard.
- No proactive notifications for task state changes.
