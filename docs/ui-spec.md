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
