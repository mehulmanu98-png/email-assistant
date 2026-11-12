# Email Assistant — Functional Specification

**Status:** Agreed product requirements  
**Accounts:** Multiple iCloud Mail and Gmail accounts  
**AI preference:** ChatGPT / OpenAI models  
**Processing:** Cloud backend  
**Dashboard:** Responsive browser interface for Mac and iPhone  
**Notifications:** None

## 1. Default email card presentation

The dashboard must show summaries by default, not the full original email body.

Each email card must show two distinct sections:

1. **Summary of the current email** — a summary of only the selected/latest message.
2. **Summary of the entire email trail** — a separate chronological summary of the available conversation from the earliest available message through the latest message.

These summaries must never be merged into one. When a new message is received in a conversation, the current-message summary and whole-trail summary must be refreshed independently.

The card also shows sender, subject, account, date/time, read status, priority and attachment information.

## 2. Required per-email actions

### Delete Email
- Ask for confirmation.
- Move the selected message to the relevant provider's Trash.
- Do not permanently delete by default.

### Show Original Email
- The full original message is hidden by default.
- Selecting this control expands the original content inline in the selected-email panel.
- Display email HTML safely; treat message content as untrusted input.

### Create Reply
- Open an interactive ChatGPT-style reply workspace.
- ChatGPT prepares an initial draft, but the user can also write directly.
- The user can ask ChatGPT to rewrite, shorten, expand or change tone, and can manually edit the draft.
- Reply All is the default.
- The user can change recipients and switch to replying to one particular person.
- To, CC and BCC must be editable.
- A reply or Reply All must be sent from the exact email account/address that received the selected original message. Display this From value read-only/locked. Never silently use another account.
- If the original receiving account cannot send, ask the user to reconnect it.
- The final email must remain in the original conversation where the provider supports it.
- Sending an existing reply requires explicit final approval of the content and recipients.

### Block User
- Provide a sender-blocking action.
- Implement provider-level blocking/rules where supported and permitted.
- Where a provider does not expose a native blocking API, clearly label the operation as an application-level block/filter.
- Explain the effect and scope before enabling the rule.

### Add Reminder
- Accept natural-language instructions.
- Parse title, date, time and Asia/Kolkata timezone by default.
- Queue a secure command for an authorised Apple Shortcut on Mac or iPhone.
- The action is complete only after the Shortcut reports successful creation in Apple Reminders.
- Keep pending/completed/failed execution state and an email/thread reference when applicable.

### Add Note
- Accept natural-language note content.
- Queue a secure command for an authorised Apple Shortcut.
- The action is complete only after the Shortcut reports successful creation in Apple Notes.
- Keep execution state and a source email/thread reference where applicable.

### Update a particular ChatGPT chat
- Let the user select a destination application-managed AI conversation and send the email/thread context to it.
- Automatically append new messages to the linked application-managed AI conversation when they arrive.
- Do not claim that the ordinary ChatGPT history sidebar can be directly modified unless a supported ChatGPT Apps capability is verified.

### Forward
- Open a forward composer.
- Allow recipient, CC and BCC editing and an optional message.
- Default to the email account that received the selected source message.
- Preserve original message context and available attachments where supported.
- Require explicit approval before sending.

## 3. Email accounts

- Support multiple iCloud Mail accounts.
- Support multiple Gmail accounts.
- Use iCloud IMAP/SMTP where suitable and Gmail API with Google OAuth.
- Identify the source account on every message.
- New outbound email: show a From dropdown containing all connected accounts; do not preselect a default account. Ask the user to select one unless explicitly named in their command.
- Replies/Reply All: strictly use the exact account that received the selected source message. Show the From address read-only/locked.
- Forwards: use the source account by default; an explicit alternative can be selected in the forward composer.
- If a visually grouped duplicate exists across accounts, actions are scoped to the exact selected source copy.

## 4. Global product requirements

- All email synchronisation and AI processing run in the cloud.
- Responsive dashboard accessible from Mac and iPhone.
- Automatic inbox reviews initially at 08:00, 12:00 and 17:00 Asia/Kolkata; schedule is editable.
- Manual Sync Now for all accounts or an individual account.
- No push, email, WhatsApp, SMS, desktop or other proactive notifications.
- Opening an email detail in the portal marks that exact source message as read in the provider; provider confirmation is required before claiming success.
- Opening/listing, background AI analysis or attachment processing alone must not change read status.
- Read/unread state changes in Gmail/iCloud are reflected in the dashboard at the next synchronisation.
- Full conversation retrieval must disclose when source history is incomplete.
- Sync and task status are shown only inside the dashboard.

## 5. Synchronisation and duplicate handling

- First connection of each account imports the most recent 90 days of emails.
- Initial import is paginated, resumable and idempotent.
- Older messages are fetched on demand from the provider when searched/opened, subject to provider capabilities.
- After initial import, use incremental sync cursors/history rather than repeatedly importing 90 days.
- Manual Sync Now and scheduled sync use the same safe pipeline.
- Use exact provider message identities and RFC Message-ID where available.
- For cross-account duplicates, require high-confidence identity and corroborating evidence. Do not merge on subject/sender alone.
- High-confidence cross-account duplicates appear as one visual inbox entry with account labels, while retaining separate mailbox copies and independent read/delete/flag states.
- When uncertain, show entries separately.

## 6. AI summaries, priority and reply drafts

For each new incoming email:
- Generate a summary of the current email.
- Generate/update a separate summary of the entire thread.
- Extract purpose, key information, amounts, dates, deadlines, commitments, unanswered questions and required actions.
- Automatically assess priority based on urgency, time-sensitive deadlines, financial/legal/contractual exposure, operational disruption and significant commitments.
- Store a concise reason for AI-assigned priority.
- User priority overrides AI priority until reset.
- Prepare an internal AI reply draft for every incoming email in the synchronised review scope.
- For messages where replying is inappropriate (mailing list, automated sender, no-reply address or similar), create a clear "Reply not recommended" draft state with an explanation; do not invent an appropriate recipient or encourage sending.
- Drafts are stored in the Email Assistant database, not Gmail/iCloud Drafts by default.
- Drafts can be revised through chat and direct editing. Sending requires explicit approval.
- Draft creation must be idempotent and must not mark the source email read.
- Do not invent facts, commitments, prices or dates.

## 7. Attachments

- Automatically analyse relevant supported attachments when a new email is synchronised.
- Detect filename, MIME type and size.
- Use supported PDF, common image, DOCX and XLSX content as context for summaries, priority, reply drafts, follow-ups and questions.
- Keep original attachments retrievable from the provider; do not automatically download and permanently store every attachment.
- Provide **View Original Attachment** and Download actions separately from AI analysis.
- PDFs open in an in-app viewer with page navigation and zoom; images in an image viewer; supported Office formats in an original-file preview where available.
- Unsupported, encrypted, corrupted, truncated or oversized files must be identified clearly. Never claim to have analysed content that could not be read.
- Treat attachments as untrusted data. Never execute files, macros or embedded programs.
- Apply size/page/token limits and minimise temporary retention.
- Attachment preview alone must not silently change mailbox read state.

## 8. Follow-ups

- Identify commitments, deadlines, promised replies, payment dates, missing documents and actions from new email.
- Deduplicate follow-ups; update an existing task when the same commitment changes.
- Provide active views for All, Action Required and Awaiting Response; make overdue status visible.
- Each follow-up links to its source email/thread and shows task, responsible party, due/expected date and status.
- Actions: Open Email Trail, Mark Complete, Edit, Snooze, Remove from Follow-ups.
- **Remove from Follow-ups** removes only the tracking entry; never delete or alter the email, conversation or linked AI conversation.
- Mark Complete removes the item immediately from active views; do not show a Completed tab/section. Keep minimal completion history internally.
- AI can list, update, snooze, complete or remove follow-up tracking through clear commands.
- A new email must update/close related follow-ups only when the new content clearly changes or fulfils the commitment.

## 9. AI Assistant as an action-taking dashboard controller

- Understand natural-language commands and execute supported dashboard actions through authenticated backend functions.
- Examples: "Show this email as priority", "Remove this email from follow-up", "Get a task update", "Show my active tasks", "Prepare a reply", "Add a reminder".
- Resolve "this email", "this conversation" and "this task" from current selection/context.
- Low-risk, reversible actions may execute when target is unambiguous; show the result in the dashboard.
- Ask a focused clarification when target or intent is ambiguous.
- Do not claim success until backend/provider/Shortcut confirms completion.
- Use idempotency controls and record action results/timestamps without storing unnecessary email content in logs.

## 10. Automatic updates to linked AI conversations

- User can link an email thread to a persistent, application-managed OpenAI conversation.
- Store provider/account/thread identity to OpenAI Conversation ID mapping.
- On arrival of a new email in that thread, detect the message, prevent duplicates, append it once to the linked AI conversation, refresh both summaries and reassess follow-ups.
- The linked AI conversation should show source sender, account, received time and thread reference.
- If no link exists, do not guess; ask the user to link or create a conversation.
- User can disable automatic updates per thread/account.
- Automatic context updates must not send email or perform consequential actions.
- This is an Email Assistant-managed AI conversation, not arbitrary modification of a regular ChatGPT history chat.

## 11. AI-assigned tasks and independent cloud execution — approved

The AI Assistant supports multi-step tasks delegated in natural language, separate from email follow-up records.

### Independent execution
- Once accepted, a task must continue processing in the cloud even when the user closes the dashboard, closes the browser, switches devices, or leaves the related ChatGPT conversation.
- The task must not depend on an open browser tab or the user's Mac being switched on.
- Use durable database-backed job/task records and a cloud worker/queue. Do not rely on an in-memory process or client-side timers.
- The worker orchestrates finite steps and calls the configured OpenAI model as needed; do not imply a model is continuously running in the background by itself.
- Progress, current step, completed steps, pending steps, blockers, timestamps and errors must be saved server-side.
- Tasks must survive worker restarts/deployments and resume safely from the last confirmed checkpoint.
- Use idempotency keys, retry policies with backoff, bounded retries and failure states to prevent duplicate side effects.
- Task states: Queued, In Progress, Waiting for User, Completed, Failed, and Cancelled.
- If a task needs a user decision, missing information, account reconnection, or approval for a consequential operation, pause at **Waiting for User** and explain what is needed. Resume after the user responds.
- User can inspect progress, request an update, pause or cancel eligible tasks from the dashboard.
- Do not claim background progress unless a worker is actually executing and task state has been persisted.
- No push/email/WhatsApp/desktop notifications; progress is visible only when the user visits the dashboard.

### Task status updates
When asked for a task update, report the real saved state, completed work, remaining work, latest checkpoint, blockers, and the next step. If the task is queued or waiting, say so plainly.

### Safety boundary
Automatic background execution does not grant permission to send emails, permanently delete messages, change blocking rules, or perform other consequential actions. Such steps pause for the required user approval. Apple Notes/Reminders tasks can be queued while devices are offline, but native actions execute only when an authorised Apple Shortcut device is available.

## 12. Compose and send new email from AI Assistant chat

- User can compose a new email in the AI Assistant.
- ChatGPT can draft and revise it conversationally.
- User can explicitly instruct the assistant to send the final email.
- The From account must be selected through a dropdown unless explicitly named.
- Validate exact recipients, sending account, subject, final body and attachments.
- If required information is ambiguous, ask before sending.
- An explicit send instruction is approval of the current final content and recipients; no second confirmation is required if everything is unambiguous.
- If the assistant changes content after approval, seek approval for the new final version.
- Report actual provider acceptance/submission separately from delivery.
- Prevent duplicate sends and inspect provider state before retrying uncertain sends.

## 13. Reply draft storage

- Canonical AI reply drafts live in the Email Assistant PostgreSQL database.
- Do not automatically create provider drafts in Gmail or iCloud.
- User can edit, chat to revise, save, discard, or approve/send.
- "Save to Email Drafts" is an optional, explicit action.
- Preserve user edits and draft versions. Repeated syncs must not create duplicate drafts.

## 14. Apple Notes and Reminders

- Add Note must create a real native Apple Note.
- Add Reminder must create a real native Apple Reminder.
- Cloud backend parses and queues authenticated, device-bound Shortcut commands.
- The dashboard shows Pending on Device until Shortcut completion is confirmed.
- Only mark Completed after a confirmed Shortcut result.
- Use device enrolment, short-lived authentication and idempotency to prevent unauthorised/duplicate actions.
- If no device is available, queue the command; do not claim the native note/reminder has been created.

## 15. Security and approvals

- Authenticated private access, HTTPS, secure sessions and least privilege.
- iCloud app-specific passwords and Google OAuth tokens stored only in secret storage.
- No secrets in browser code or GitHub.
- Database encryption, backups, audit trail and minimal logs.
- Email/attachment content is untrusted input, not system instructions.
- Delete moves to Trash after confirmation; permanent deletion requires a separate explicit confirmation.
- Sending replies/forwards requires approval. A direct explicit send instruction authorises only that specific final new email.
- Block action must disclose provider-level vs application-level scope.
- No proactive notifications of any kind.


## 24. AI task scheduling, priority and limited parallel execution — approved

### Concurrency policy
- The AI Assistant may execute **up to three independent delegated tasks simultaneously** for this workspace.
- Three is the maximum, not a target. It may run fewer tasks when there are fewer independent tasks, provider limits, rate limits, or worker capacity constraints.
- Tasks with dependencies must run in the correct sequence. Do not start a dependent task until its prerequisite is complete.
- Independent tasks can run in parallel while respecting the maximum of three active tasks.
- Tasks in **Waiting for User**, user-paused tasks, and tasks waiting for an Apple device to execute a native Shortcut do not consume one of the three active AI task slots.
- The limit must be enforced server-side in the durable scheduler, not merely in the dashboard.

### Queue priorities
Use four priority levels:
- **Urgent** — critical or time-sensitive work.
- **High** — important business work.
- **Normal** — standard assignments.
- **Low** — non-urgent work.

The user and AI Assistant can set or change a task's priority. The AI may recommend a priority based on deadlines and importance, but must show the reason. User-set priority takes precedence over AI recommendations until the user changes or resets it.

Queued tasks are selected in priority order: Urgent, High, Normal, Low. Within the same priority, use first-in-first-out ordering unless an explicit due-date policy is configured. A higher-priority queued task may move ahead of lower-priority queued tasks, but must not abruptly interrupt a running operation. Any pre-emption must occur only at a safe, persisted checkpoint.

### User controls and status
- User can ask: "Make this urgent", "Lower the priority", "Show high-priority tasks", or "What is next in the queue?"
- Show priority, queue status, current step, dependency state and latest persisted progress in the AI Assistant task panel.
- Respect provider/API rate limits and use bounded retries/backoff. Do not exceed the three-task limit to speed up work.
- The backend must enforce a configurable concurrency limit, with **3** as the approved initial setting.
- No proactive notifications when task priority or queue state changes.
