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
