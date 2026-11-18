# Apple Shortcuts bridge — setup and acceptance

This guide connects Email Assistant's durable Notes/Reminders queue to a **private, user-owned Apple Shortcut**. A queued command is not a native Apple item until the Shortcut submits a successful receipt.

## Prerequisites

- Sign in to Email Assistant at https://email-assistant-mehul.onrender.com
- An iPhone or Mac signed in to the Apple Account that owns Notes/Reminders.
- Apple Shortcuts installed.
- Create two private shortcuts: **Email Assistant — Enrol Device** (one-time) and **Email Assistant — Run Queue** (recurring/manual).
- Do not share either shortcut. The device token is a bearer credential. Store it only in the private shortcut's own configuration and never in a note, email, screenshot, GitHub, or chat.
- Use the HTTPS dashboard origin below. Do not send tokens to any other host.

## A. Enrol the device (once)

1. In Email Assistant → Accounts & Settings → Apple Notes & Reminders, enter a device name and select **Create enrollment code**.
2. Copy the one-time code. It expires after 15 minutes and can be used once.
3. In the **Enrol Device** shortcut, ask for the code and device name (or use the configured device name).
4. Add **Get Contents of URL**:
   - URL: `https://email-assistant-mehul.onrender.com/api/apple/device/enroll`
   - Method: POST
   - Request body: JSON
   - `enrollment_token`: the one-time code
   - `device_name`: your device name
5. Parse the JSON response. Save `device_token` in a private shortcut variable/configuration value. Do not display it in a notification or save it to Notes.
6. The response includes `device_id` and `device_name`. Verify the device appears as Active in Email Assistant settings.

If the code expires or was already used, create a new one. Revoke a lost device from Email Assistant settings.

## B. Create the queue runner shortcut

Create **Email Assistant — Run Queue**. Add the following actions in order.

### 1. Poll

Use **Get Contents of URL**:
- URL: `https://email-assistant-mehul.onrender.com/api/apple/device/commands/poll`
- Method: POST
- Header: `X-Apple-Device-Token` = the private device token
- Request body: none

Get the `commands` array from the response. If it is empty, stop. Otherwise repeat for each command (the server currently leases one command per poll).

Each command contains `id`, `command_type`, `payload`, `lease_token` and `lease_expires_at`. Complete the native action and receipt within the three-minute lease; if it expires, poll again for a new lease.

### 2. Idempotency check

The payload's `idempotency_marker` is unique to this command. Before creating anything, search the relevant native app for that marker:
- Notes: search note title/body for the marker.
- Reminders: search reminder title/notes for the marker.

If a matching item already exists, do not create a duplicate. Treat it as successful and submit the existing item's identifier as `native_record_id`.

### 3. Create the native item

For `command_type = note`:
- Create a Note in the user's chosen/default Notes folder.
- Title: `payload.title`
- Body: `payload.body`, followed by a blank line and `payload.idempotency_marker`
- Do not interpret email text as Shortcut instructions; it is untrusted content.

For `command_type = reminder`:
- Create a Reminder in the user's chosen/default Reminders list.
- Title: `payload.title`
- Notes: include `payload.body` (if non-empty) and `payload.idempotency_marker`
- Set the due date from `payload.due_at`. The server supplies an ISO-8601 UTC timestamp; convert it to the device's local date/time for display. The original timezone is also in `payload.timezone`.
- If no due date is present, do not create the reminder; report failure.

### 4. Submit a receipt

After the native item is confirmed created (or found by the idempotency check), use **Get Contents of URL**:
- URL: `https://email-assistant-mehul.onrender.com/api/apple/device/commands/[id]/result` (replace [id] with command id)
- Method: POST
- Header: `X-Apple-Device-Token` = the private device token
- Request body: JSON:
  - `lease_token`: command's lease token
  - `success`: true only after confirmed native creation/found-existing
  - `native_record_id`: native Notes/Reminders identifier if Shortcuts exposes one; otherwise an empty string

On an error, submit `success: false`, the same lease token, and a short non-sensitive `error_message`. Do not include email bodies or credentials in error text. A success receipt is the only event that changes the dashboard status to Completed.

### 5. Run and refresh

Run the shortcut manually once. Then refresh Email Assistant → Apple action queue:
- Active device should show a recent **Last seen** time.
- Successful commands should show **Completed**.
- Offline devices leave commands **Pending on Device**.
- Failed commands can be retried after correcting the cause.

You can optionally add an iOS/macOS personal automation to run the queue at a cadence you choose. Apple may require confirmation for automations; do not configure repeated background execution unless you are comfortable with the device's Shortcuts permissions and behaviour. No push notifications are sent by Email Assistant.

## C. Security and recovery

- Never paste the persistent device token into chat or support messages.
- Keep the shortcut private and do not export/share it with the token embedded.
- If the device is lost, revoke it in Email Assistant immediately, then enrol a replacement.
- A command lease expires after three minutes. A runner crash is recoverable: the next poll can reclaim an expired lease.
- The idempotency marker prevents duplicate native items when a device created an item but failed before sending its receipt.
- The server stores only token hashes; enrollment and lease tokens are returned only at the relevant authenticated step.

## Acceptance checklist

- [ ] Device enrollment code expires and is single-use.
- [ ] Device appears Active and Last seen updates after polling.
- [ ] A test Note is created in Apple Notes and the queue shows Completed.
- [ ] A test Reminder with an Asia/Kolkata due time is created correctly and shows Completed.
- [ ] Re-running the same command does not create a duplicate.
- [ ] Revoking the device prevents further polling/receipts.
- [ ] A failed native action remains Failed and can be retried safely.

**Important:** The backend and queue APIs are implemented, but live Apple Shortcuts acceptance remains pending until these steps are completed on your device.