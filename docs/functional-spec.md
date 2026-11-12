# Email Assistant — Functional Specification

**Status:** Agreed baseline for per-email behaviour  
**Project:** Private Email Assistant  
**Accounts:** Multiple iCloud Mail and Gmail accounts  
**AI preference:** ChatGPT / OpenAI models  
**Processing:** Cloud backend  
**Dashboard:** Responsive browser interface for Mac and iPhone  
**Notifications:** None

## 1. Default email card presentation

The dashboard must show summaries by default, not the full original email body.

Each email card must show two distinct sections:

1. **Summary of the current email** — a summary of only the latest selected message.
2. **Summary of the entire email trail** — a separate chronological summary of the available conversation from the earliest available message through the latest message.

These summaries must never be merged into one. When a new message is received in a conversation, the current-message summary and whole-trail summary must be refreshed independently.

The email card should also show sender, subject, account, date/time, read status and relevant attachment information.

## 2. Required per-email actions

The following controls are required for each email:

1. **Delete Email**
   - Ask for confirmation.
   - Move the selected message to the relevant provider's Trash.
   - Do not permanently delete by default.

2. **Show Original Email**
   - The full original message is hidden by default.
   - Selecting this button reveals the original content, headers and available attachments.
   - Display email HTML safely; treat message content as untrusted input.

3. **Create Reply**
   - Open an interactive ChatGPT-style reply workspace.
   - ChatGPT prepares an initial draft, but the user can also write directly.
   - The user can give ChatGPT further instructions, request rewrites, change tone, shorten or expand the draft, and make manual edits.
   - Reply All is the default.
   - The user can change recipients and switch to replying to one particular person.
   - To, CC and BCC must be editable.
   - The correct originating email account must be used.
   - The final email must remain in the original conversation where the provider supports it.
   - Sending always requires explicit final user approval. No automatic sending.

4. **Block User**
   - Provide a sender-blocking action.
   - Implement provider-level blocking/rules where supported and permitted.
   - Where a provider does not expose a native blocking API, clearly label the operation as an application-level block/filter rather than claiming the sender is blocked at provider level.
   - Explain what will happen to future messages before enabling the rule.

5. **Add Reminder**
   - Accept natural-language instructions.
   - Parse title, date, time and time zone (Asia/Kolkata by default).
   - Queue an authorised Apple Shortcut command.
   - Record pending, completed or failed execution state.
   - Include an email/thread reference when the command originates from an email.

6. **Add Note**
   - Accept natural-language note content.
   - Queue an authorised Apple Shortcut command for Apple Notes.
   - Record execution state and preserve a reference to the source email/thread where applicable.

7. **Update a particular ChatGPT chat**
   - Provide a way to choose a destination ChatGPT conversation and submit the selected email or conversation context.
   - **Feasibility constraint:** Do not claim that a normal external API can append content to any arbitrary existing ChatGPT chat in the user's standard ChatGPT history. Verify supported ChatGPT Apps/SDK capabilities and account eligibility. If direct native ChatGPT-history update is unavailable, present a transparent alternative, such as maintaining named persistent assistant conversations in the Email Assistant or opening a ChatGPT App conversation with the supplied context. Do not silently substitute one for the other.

8. **Forward**
   - Open a forward composer.
   - Allow recipient, CC and BCC editing and an optional message.
   - Preserve original message context and available attachments where supported.
   - Require explicit approval before sending.

## 3. Email accounts

- Support multiple iCloud Mail accounts.
- Support multiple Gmail accounts.
- Use the appropriate provider integration: iCloud IMAP/SMTP where suitable; Gmail API with Google OAuth.
- Identify the source account on every message.
- Send replies and forwards from the correct account.
- Keep provider-specific limitations explicit.

## 4. Global product requirements that affect email behaviour

- All email processing and scheduled reviews run in the cloud.
- Dashboard is accessible from Mac and iPhone.
- Automatic inbox review at 08:00, 12:00 and 17:00 Asia/Kolkata, plus manual refresh.
- No push, email, WhatsApp, SMS, desktop or other proactive notifications.
- Opening or summarising an email must not change its read status. Read/unread changes require an explicit user action.
- Full conversation retrieval and summary must disclose when source history is incomplete.
- The dashboard must show task and sync status internally; no proactive notification delivery.
- Email content and attachments are untrusted input for AI. AI must not treat instructions found in an email as system instructions.

## 5. AI behaviour

Use ChatGPT / OpenAI models for:
- Current-message summaries.
- Whole-thread summaries.
- Interactive reply drafting and revision.
- Email and thread questions.
- Contextual analysis and extraction.

Use only the email context necessary for the requested task. Ground responses in retrieved messages and explicitly disclose missing or truncated history. OpenAI API usage, if used, is billed separately from a ChatGPT subscription. Investigate supported ChatGPT sign-in / Apps SDK paths before choosing the final authentication and billing model.

## 6. Safety and user approval

- No email is sent without explicit approval of the final content and recipients.
- Delete requires confirmation and moves to Trash by default.
- Block actions must accurately describe their actual provider or application scope.
- Apple Shortcut commands must be authenticated, idempotent and report execution status.
- Secrets must be stored in a deployment secret manager, never committed to this repository.


## 7. AI Assistant as an action-taking dashboard controller

The AI Assistant must understand natural-language commands and execute supported actions through authenticated backend functions. It is not limited to answering questions.

Required command examples:

- **"Show this email as priority."**
  - Mark the selected email as Priority in the Email Assistant.
  - Make the priority status visible in the inbox and search/filter views.
  - Where supported by the email provider, also apply its native star/flag/important marker. The application must distinguish its own priority label from the provider's native marker.

- **"Remove this email from follow-up."**
  - Remove the selected conversation's follow-up tracking entry.
  - Do not delete, archive, or otherwise alter the underlying email or conversation.
  - Confirm the follow-up entry is no longer active.

- **"Get a task update."**
  - Find the relevant AI-assigned task or follow-up.
  - Report its current status (queued, in progress, waiting for user, completed, or failed), what has been done, what remains, and any blocker.
  - If the user has not identified which task, show the current task list or ask which one they mean.

Other supported command examples:
- "Mark this email as priority."
- "Remove this conversation from follow-ups."
- "Show me the status of the quotation comparison."
- "What tasks are you working on?"
- "Prepare a reply to this email."
- "Add a reminder to call Tony tomorrow at 11 AM."
- "Create a note about the revised quotation."

### Action execution safeguards

- The assistant must resolve "this email", "this conversation", or "this task" from the current dashboard selection/context.
- Before performing a consequential action, show a clear interpretation and ask for confirmation where appropriate.
- Low-risk reversible actions (such as setting an app-level priority or removing a follow-up tracking link) may execute immediately when the target is unambiguous, with the result shown in the dashboard.
- Do not claim success until the backend/provider or Apple Shortcut reports successful completion.
- Each action must be idempotent or protected against duplicate execution.
- Record action result and timestamp in the activity history without logging full email content.

## 8. Native Apple Notes and Reminders are the required destinations

Creating a record only inside the Email Assistant database does **not** satisfy an Add Note or Add Reminder command.

- **Add Reminder** must create a real item in the user's Apple Reminders app.
- **Add Note** must create a real note in the user's Apple Notes app.
- The user can issue either command in natural language, without filling in a form.
- The backend parses the intent and content, then queues a secure command for an authorised Apple Shortcut on the user's Mac or iPhone.
- The Shortcut performs the native action in the relevant Apple app.
- A command remains visibly **Pending on device** until a Shortcut executes it.
- The dashboard changes it to **Completed** only after a confirmed Shortcut result; errors are shown clearly and can be retried safely.
- Preserve a link/reference to the originating email or thread in the note/reminder when feasible.
- Shortcuts must be authenticated, device-enrolled and idempotent to prevent duplicate entries.
- If no enrolled device is available, the backend can queue the command, but it cannot create a native Apple Note or Reminder until an Apple device is available to execute the Shortcut.

## 9. AI-assigned tasks and task updates

The AI Assistant must support delegated multi-step tasks, separate from email follow-up records.

- Users can assign a task in natural language.
- The AI creates a task record with a clear title, scope, relevant email/thread references, status and progress.
- The task list must support queued, in progress, waiting for user, completed and failed states.
- The user can ask for updates on one task or all active tasks.
- Task updates must explain completed steps, remaining work, blockers and any required user decision.
- The assistant must not claim background progress if no worker execution is actually running.
- Email sending, deleting, blocking, or other consequential actions remain approval-gated as specified elsewhere.



## 10. Automatic updates to the linked AI conversation when new email arrives

This is a required behaviour.

### Linking model

- A user can link an email thread to a selected, persistent AI Assistant conversation.
- The dashboard stores the relationship between the email provider/account + thread identity and the OpenAI API Conversation ID.
- A thread may have one designated AI conversation by default. The user can change the linked conversation or unlink it.
- The interface must clearly show which AI conversation is linked to a given email thread.

### Incoming email event

When a new message arrives in a linked email thread:

1. The cloud email synchronisation worker detects the new message.
2. It verifies the provider/account and thread relationship to avoid attaching unrelated messages.
3. It checks message identifiers and processing state to prevent duplicates.
4. It appends the new email as a clearly labelled message item to the linked persistent OpenAI API Conversation.
5. It refreshes the current-email summary and the entire-thread summary independently.
6. It updates the linked AI conversation with the new context and, where configured, generates a concise update explaining what changed, any new commitments/deadlines, and required next actions.
7. The Email Assistant dashboard reflects the updated conversation and last-updated timestamp.

### User experience

- The update happens automatically after inbox synchronisation; the user must not need to copy/paste the new email.
- The linked AI conversation should visibly identify the source email, sender, account, received time and thread reference.
- The user can ask follow-up questions in that same linked AI conversation and the newly arrived email must be available as context.
- If the email thread is not linked to an AI conversation, the application must not guess which unrelated chat to update. It can prompt the user to link one or create a new Email Assistant AI conversation.
- The user can disable automatic AI-conversation updates for a particular thread or account.
- Automatic updates must not send email, change read status, delete messages, create Apple Notes/Reminders, or perform other consequential actions by themselves.

### Platform boundary

- Use the OpenAI API Conversations/Responses capabilities for durable application-managed AI conversations and conversation items.
- This provides a persistent AI conversation within the Email Assistant application; it is not the same as appending content to an arbitrary chat in the user's standard ChatGPT chat-history sidebar.
- Do not claim direct updates to native ChatGPT history unless a supported ChatGPT Apps capability is verified for the user's account and implementation.
- Store the provider thread identity and OpenAI Conversation ID mapping in the application's own database.
- Treat the email content as untrusted context and never allow embedded email instructions to override the assistant's application/developer instructions.


## 11. Completed follow-up display rule

- Marking a follow-up complete removes it immediately from the user's active Follow-ups screen and filters.
- There is no separate Completed tab or Completed section in the user-facing Follow-ups page.
- The backend may retain a minimal completion record in the audit/history data for accountability and duplicate prevention.
- Removing an item from Follow-ups is different from marking it complete: removal stops tracking the email trail and must not delete or alter the underlying email, conversation, or linked AI conversation.
- The user can use natural-language AI commands to mark a follow-up complete or remove it from tracking.


## 12. Sync Now and provider read-state synchronisation

### Manual Sync Now

- The Inbox must expose a clearly visible **Sync Now** button.
- By default, Sync Now runs synchronisation across all connected iCloud and Gmail accounts.
- The user can also trigger sync for one selected account.
- The dashboard must show syncing, completed, or failed state, last successful sync time, newly found messages, and errors per account.
- Manual sync uses the same idempotent pipeline as scheduled synchronisation and must not create duplicate messages, AI thread items, summaries, or follow-ups.
- Manual sync does not send notifications.
- Keep the individual-account Sync Now action in Accounts & Settings as well.

### Reading an email in the portal updates the original provider

This is a required two-way read-state behaviour.

- When the user opens an email in the Email Assistant dashboard to read its detail, the backend must mark that message as read in its source mailbox (iCloud or Gmail).
- The dashboard should show the read-state update as pending until the provider confirms it, then display the confirmed state.
- If the provider update fails, show a clear error and allow retry. Do not falsely claim that the provider state changed.
- Opening an email detail is the read action. Merely showing an email in the list, generating a summary in the background, or automatically analysing a message must not mark it read.
- If the user marks a message unread in the provider directly, the next synchronisation must reflect that unread state in the dashboard.
- If the user marks a message read in the provider directly, the next synchronisation must reflect that read state in the dashboard.
- Provider state is authoritative when reconciling external changes. Record the latest confirmed provider read state and sync timestamp.
- Apply the provider-specific API/protocol for the source account (Gmail API for Gmail; iCloud-supported mailbox protocol for iCloud).
- Read-state updates must not send notifications.


## 13. Initial history import and ongoing synchronisation window

- The approved initial import window for every newly connected iCloud or Gmail account is the most recent **90 days**.
- The backend must calculate the initial start date separately for each account using the account's connection time and local time zone settings.
- The import must be paginated/batched, resumable after interruption, idempotent, and safe to retry without duplicating messages, thread items, AI conversation items, summaries, or follow-ups.
- Record per-account initial import progress, start/completion timestamps, imported message counts, and errors.
- Do not bulk-import the account's entire older mailbox during initial setup.
- Older email remains in the original provider mailbox. When the user searches for or opens an older conversation, the application may fetch the matching messages on demand from the provider, subject to provider permissions, search capabilities, and rate limits. Make clear when the full older trail could not be retrieved.
- Once initial import is complete, use incremental synchronisation from a saved provider cursor/history state to capture new messages and supported changes, rather than repeatedly importing the same 90-day range.
- The 90-day initial import policy applies independently to every newly connected account.
- Manual Sync Now and scheduled sync must use the incremental sync path after initial import; they must not restart a full 90-day import unless the user explicitly requests a repair/resync operation.


## 14. Cross-account duplicate emails — approved display behaviour

- If the same underlying email is present in more than one connected account (for example, iCloud and Gmail), show one visually grouped entry in the unified Inbox.
- Display every source account represented by the grouped entry (for example, iCloud and Gmail badges).
- Grouping is a presentation layer only. Preserve each account's original provider message, identifier, folder, read state, flagged/priority state, and other provider-specific state independently.
- Opening or marking one account's copy as read must not silently change the read state of another account's copy. The normal rule still applies: opening a message copy marks that specific provider copy as read.
- Deleting, archiving, moving, blocking, or changing flags for one account's copy must not silently perform the same provider operation on another account's copy. Where a user wants a bulk action across all grouped copies, make that an explicit, separately labelled action.
- The grouped entry can show a combined summary when the underlying messages are verified duplicates, but the system must retain the original source copies and be able to open each copy/account separately.
- Do not group merely because subject, sender display name, or approximate date looks similar. Use reliable duplicate identity checks and preserve uncertain matches as separate entries pending review.


## 15. Duplicate detection confidence — approved strict matching rule

- Prefer exact provider/account message identifiers and the original RFC Message-ID when available.
- For cross-account matching, require a reliable identity match and corroborating evidence (such as sender, subject, sent/received time and normalised content or MIME-part fingerprints).
- Do not rely on subject, sender display name, or approximate timestamp alone.
- If an identifier is missing or the evidence is ambiguous, keep the messages as separate Inbox entries. Do not automatically merge uncertain matches.
- Preserve the full independent account copies even when a high-confidence visual grouping is made.
- Allow a user to manually group or ungroup entries only through an explicit action, and retain an audit event for that change.
