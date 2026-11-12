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

