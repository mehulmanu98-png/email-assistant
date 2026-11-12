# Email Assistant — UI Specification

**Status:** Approved Inbox layout decisions  
**Visual direction:** Modern productivity — clean typography, subtle colours, compact navigation, restrained borders and generous spacing.  
**Devices:** Responsive browser UI for Mac and iPhone.

## 1. Global navigation

Keep the primary navigation simple, with four main sections:

1. **Inbox** — main working area for all connected email accounts.
2. **Follow-ups** — email follow-up tracking and task statuses.
3. **AI Assistant** — natural-language commands, delegated tasks and task updates.
4. **Accounts & Settings** — connected iCloud/Gmail accounts, sync schedule, security and preferences.

Avoid separate top-level Conversations, Overview, or Notes pages for the initial release. Conversations open from email cards. Apple Notes and Reminders are created through the command centre and email actions.

## 2. Inbox — approved desktop layout

Use a three-column layout:

- **Left column:** persistent primary navigation.
- **Centre column:** email list, account filters, search and sorting.
- **Right column:** selected email detail, summaries and actions.

The selected email detail panel must display:
- Sender, subject, account, date/time and read state.
- Summary of the current email.
- A separate summary of the entire available conversation/thread.
- All required email actions.

The default email display is summarised. The full original email is hidden initially.

## 3. Approved email actions presentation

**Show all email action buttons directly on the selected-email panel. Do not hide them behind a More menu.**

Required visible controls:
- Delete Email
- Create Reply
- Block User
- Add Reminder
- Add Note
- Forward
- Update a particular ChatGPT Chat
- Show Original Email (expand/collapse control)

The actual availability and outcome of provider-specific operations must be explicit. Do not render these controls as decorative placeholders in a released app; each must call its implemented backend operation and show its real result.

## 4. Original email behaviour

- The original email content is hidden by default.
- Selecting **Show Original Email** expands the original message inline in the right-hand selected-email panel.
- The action toggles to **Hide Original Email** when expanded.
- Expanding the original message must not change the email's read status.
- The original can include safely rendered body content and available attachment controls.

## 5. Reply workspace

Selecting **Create Reply** opens an interactive ChatGPT-style reply workspace.

- Reply All is the default recipient mode.
- The user can switch to replying to one person and edit To, CC and BCC.
- The user can converse with AI to request or revise draft content.
- The user can edit the draft directly at any time.
- Save Draft is available.
- Sending requires explicit approval of the final draft and recipients.

The reply workspace may occupy the selected-email panel or open as a focused overlay, but should preserve the underlying selected conversation.

## 6. Responsive mobile behaviour

On iPhone:
- Replace the three desktop columns with a simple navigation and email-list view.
- Tapping an email opens its summary and actions in a full-screen detail view.
- Original email expands inline within that detail view.
- All actions remain available without horizontal scrolling.
- The same cloud data and backend are used as on desktop.

## 7. Visual language

Use a modern productivity aesthetic:
- Light, neutral background.
- Clear typographic hierarchy.
- Subtle dividers and restrained accent colour.
- Compact, consistent icons.
- Strong whitespace and readable email summaries.
- Avoid excessive cards, bright status badges, gradients and decorative charts.

## 8. Explicitly approved Inbox decisions

| Decision | Approved value |
|---|---|
| Desktop layout | Three columns |
| Email action buttons | All visible directly |
| Original email | Hidden by default; expands inline |
| Visual direction | Modern productivity |
| Mobile layout | Responsive list-to-detail flow |


## 9. Follow-ups screen — approved design

The Follow-ups screen uses the same modern productivity visual language as the Inbox: clean typography, neutral surfaces, subtle separators, compact status labels, and no decorative charts or excess cards.

### Main sections

Use three primary working filters:
1. **All** — all active follow-up records.
2. **Action Required** — tasks where the user needs to act.
3. **Awaiting Response** — tasks where another person or organisation owes a response.

Overdue status should be visible as a status/date indicator within the relevant task, not as a separate large navigation area.

### Follow-up item content

Each item should show:
- Clear task title.
- Person, organisation or responsible party.
- Source email conversation and provider/account.
- Short explanation of what is required or awaited.
- Due date or expected response date, when known.
- Status such as Pending, Waiting, or Overdue.

### Actions on every active follow-up

- **Open Email Trail** — open the related conversation.
- **Mark Complete** — immediately remove the item from the active Follow-ups screen.
- **Edit** — change task title, description, owner or due date.
- **Snooze** — choose a later review date.
- **Remove from Follow-ups** — remove only the tracking item; never delete or alter the email, conversation, or linked AI conversation.

The **Remove from Follow-ups** action must always be available for each active item, not hidden in an inaccessible menu. It may use a compact text action to keep the visual design uncluttered.

### Completed items — approved behaviour

- When a follow-up is marked complete, it disappears immediately from all active Follow-ups views.
- Do not show a Completed tab or separate Completed section in the Follow-ups interface.
- The completion event may be retained internally for audit/history and duplicate prevention, but must not clutter the user's active task view.
- Completion must not delete the underlying email trail or AI conversation.

### AI Assistant integration

The AI Assistant can:
- Remove a specified email trail from follow-ups.
- Mark a follow-up complete.
- Edit or snooze a follow-up.
- List all active follow-ups.
- Report task status and explain what is awaited or overdue.

For ambiguous commands, ask which task the user means. After a successful action, show a clear result inside the dashboard. No notifications.

## 10. Final approved primary navigation

The initial application uses only four primary sections:
1. **Inbox**
2. **Follow-ups**
3. **AI Assistant**
4. **Accounts & Settings**

Do not create separate top-level Conversations, Overview, or Notes pages for the first release. Open conversations from the Inbox; use the AI Assistant and email actions to create Apple Notes and Reminders.

The four-section navigation supersedes earlier exploratory navigation concepts in this document.


## 11. AI Assistant screen — approved layout

The AI Assistant is a ChatGPT-style workspace for natural-language commands, email analysis and delegated tasks.

### Layout

- Main conversation area occupies the majority of the screen.
- A compact side panel shows active AI-assigned tasks and their status.
- The side panel must remain visually secondary and must not crowd the conversation.
- On narrow/mobile screens, the task panel becomes a collapsible panel or separate drawer; the chat remains the primary view.
- The user can start a new AI conversation and switch between named persistent Email Assistant conversations.
- Each conversation may be linked to one or more relevant email threads. New messages in linked email threads update the linked application-managed AI conversation automatically, subject to the functional-spec platform boundary.

### Chat functionality

- Natural-language instructions to control supported Email Assistant actions.
- Delegate multi-step tasks to the AI.
- Ask questions about selected emails or linked conversations.
- Request summaries, quotation comparisons, reports, and reply preparation.
- Ask for task updates, all active tasks, completed work, remaining work, or blockers.
- Create Apple Notes and Reminders through authenticated device Shortcuts.
- AI can propose actions and execute only the supported operations under the approval rules in the functional specification.

### Task side panel

Show compact task rows with:
- Task title.
- Status: Queued, In Progress, Waiting for You, Completed, or Failed.
- Brief progress or next action.
- Last updated time.

Completed tasks should not dominate the active-task panel; they can be collapsed or reached through task history. No proactive notifications.

### AI conversation controls

- New conversation.
- Rename conversation.
- Search or switch conversations.
- Link/unlink email trails.
- See when a linked email trail last updated the AI conversation.
- Ask the AI to summarise the current task or conversation.

### Approved design decision

**Main Chat + Compact Side Task Panel** is the approved desktop layout. On mobile, the task panel collapses into a drawer or separate view.


## 12. Accounts & Settings screen — approved design

Keep Accounts & Settings as one clean page with four grouped sections. Avoid deep, nested settings navigation.

### A. Email Accounts

- List all connected iCloud Mail and Gmail accounts.
- Show provider, email address, connection status, last successful sync, and any recent sync error.
- Provide Add Account, Manage, Reconnect, Sync Now, and Disconnect actions as appropriate.
- Support multiple accounts of each supported provider.
- Disconnecting an account must not silently delete previously stored email history, thread summaries, AI conversations, or follow-ups.

### B. Automatic Email Review

- The review schedule is **editable**.
- Default review times: 08:00, 12:00, and 17:00.
- Default timezone: Asia/Kolkata.
- User can add, edit, enable/disable, and remove review times.
- User can change the timezone.
- Provide a manual Sync Now action for each individual account and for all accounts.
- Clearly display the next scheduled review and last successful review.
- Changes to schedule must update the cloud scheduler, not merely the local browser.
- No notification delivery is associated with scheduled reviews.

### C. AI Preferences

- Show OpenAI / ChatGPT model connection status and configuration.
- Show whether automatic linked AI conversation updates are enabled.
- Allow automatic updates to be enabled or disabled per email thread and, where sensible, per account.
- Clearly disclose the chosen AI integration and any separately billed API usage.

### D. Security & Privacy

- Account security and sign-in methods.
- Authorised Mac/iPhone devices for Apple Shortcuts.
- Connected service permissions and account connections.
- Activity log and synchronisation history.
- Credential and token management must remain server-side; never expose secrets in the browser.

### Notifications

- Notifications remain disabled. Do not add push, email, WhatsApp, SMS, desktop, or other proactive notification settings or delivery features.

### Approved screen structure

1. Email Accounts
2. Automatic Email Review
3. AI Preferences
4. Security & Privacy

Use inline rows/cards with subtle separators, clear connection states, and concise action controls.


## 13. Inbox Sync Now control — approved addition

- Display a clearly visible **Sync Now** button in the Inbox header.
- The default action synchronises all connected email accounts.
- Provide an account selector or adjacent menu to synchronise one selected account only.
- While running, show a clear syncing state and prevent accidental duplicate sync submissions.
- On completion, show the result in the dashboard: accounts checked, new messages found, updates processed, and any account-specific errors.
- Show the last successful sync time for each account.
- Manual sync must trigger the same safe, idempotent processing pipeline as scheduled reviews.
- Syncing must not send notifications.
- Accounts & Settings must also retain a per-account Sync Now action.


## 14. Initial email synchronisation — approved preference

- On first connection of each iCloud or Gmail account, initially import the most recent **90 days** of email.
- Show initial import progress and account-specific status in Accounts & Settings.
- Clearly show the date range being imported and whether the initial import is still running or has completed.
- Older messages are not bulk-imported during initial setup. When the user searches for or opens an older message/thread, the application may retrieve the required older data on demand from the relevant provider, subject to provider search/history access.
- After the initial import, normal incremental synchronisation continues from the saved sync cursor/history and includes new messages and supported mailbox state changes.
- The 90-day initial import preference applies independently to each newly connected email account.


## 15. Original attachment viewing — approved requirement

- Show every attachment in a compact list within the selected email detail panel.
- Each attachment row displays its filename, file type, size and analysis status.
- Provide an explicit **View Original Attachment** button for each attachment, in addition to Download.
- PDFs open in an in-app viewer with page navigation and zoom; images open in an image viewer; supported Office documents use an original-file preview when available.
- If a format cannot be previewed, clearly state this and provide a download/open-original action.
- Always distinguish the original attachment from AI-extracted text and summaries. Never replace the original with a transformed version.
- Provide an obvious way to return to the email detail panel.


## 16. Reply draft UI — approved internal storage

- The default **Create Reply** workspace edits an internal Email Assistant draft.
- Autosave changes to the application database; do not automatically create a Gmail or iCloud provider draft.
- Show an obvious saved/saving state in the reply workspace.
- Provide controls for Edit, Ask ChatGPT to revise, Save, Discard, and Approve & Send.
- Provide **Save to Email Drafts** only as a separate optional action, with the destination account displayed.
- The draft remains accessible from its source email and conversation.


## 17. New outbound email — sending account selection

- When a user composes a new email in the AI Assistant, the sending account must be selected for that particular message.
- Do not preselect a default sending account.
- If the user explicitly names a connected account in their instruction, show that account as selected.
- Otherwise, ask the user to choose from their connected iCloud/Gmail accounts before sending.
- Replies and forwards default to the source email account, with an editable account choice.


## 18. From dropdown and reply account display — approved

- The new-email composer must contain a visible **From** dropdown listing the connected and authorised iCloud/Gmail sending addresses. No account is preselected by default.
- The user selects the From account for each new outbound email, unless the account was explicitly named in their command.
- In the reply workspace, display the original receiving email address in the **From** field. This field is read-only/locked: replies and Reply All must use the exact account that received the selected original email.
- If that receiving account is disconnected or cannot send, show a reconnect/error state. Never silently send the reply from another account.
- For a forwarded email, show the original receiving account as the default From account. An explicit alternative can be chosen in the forward composer.
- If a visually grouped duplicate exists across accounts, actions are scoped to the exact selected source copy. The source account determines the reply From address.


## 19. Independent cloud AI task execution — approved

- The compact task side panel shows tasks that continue running in the cloud even after the user closes the dashboard or leaves the related AI conversation.
- Task status and progress are stored server-side and are available when the user returns on Mac or iPhone.
- Show the latest persisted status, current step, completed steps, next step, last update time and any blocker.
- Use the following states: Queued, In Progress, Waiting for User, Completed, Failed, Cancelled.
- Tasks waiting for the user must clearly state what input or approval is needed.
- Provide task details with a progress timeline and controls to request an update, pause, resume or cancel when the task state allows it.
- Do not show fabricated percentage progress. Progress must reflect actual completed steps or checkpoints.
- No proactive notifications. New progress is visible when the dashboard is opened or refreshed.
- Closing the browser or switching devices must not cancel an accepted task.


## 20. AI task queue and concurrency display — approved

- The compact task panel may show a small queue summary: active tasks (for example, 2 of 3) and queued tasks.
- Each task row shows its priority, current status, last update time and next action.
- Queued tasks show that they are waiting for an execution slot or prerequisite.
- Waiting for User tasks are clearly distinguished and do not count as occupying an active execution slot.
- The UI must not promise that a queued task has started until a worker claims it.
- No notifications are sent when tasks start or finish.


## 21. AI task priority display and controls — approved

### Priority colour mapping
Use these restrained semantic label colours consistently in the AI task list and task details:
- **Urgent** — red
- **High** — amber/orange
- **Normal** — blue
- **Low** — green

Colour is supplementary to the written priority label; never communicate priority by colour alone.


- Every AI-assigned task row displays one priority label: Urgent, High, Normal or Low.
- New tasks default to Normal unless an explicit user priority or justified AI recommendation is present.
- Provide a task detail control to change priority.
- The AI Assistant also supports natural-language priority changes, for example:
  - "Make Tony's quotation comparison urgent."
  - "Set the supplier research task to High."
  - "Lower this task to Low."
- Show a short explanation when the AI automatically assigns Urgent or High.
- Distinguish user-set priority from AI-recommended priority where useful.
- The task panel should show active slot usage (maximum 3), queued tasks and their priority-aware ordering.
- Priority changes reorder queued tasks only. Never imply that an already-running task was interrupted.
