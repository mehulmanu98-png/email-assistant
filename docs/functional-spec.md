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
