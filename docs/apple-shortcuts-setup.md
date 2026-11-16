# Apple Notes and Reminders — Shortcut setup

**Purpose:** connect a personal Mac or iPhone Shortcut to the Email Assistant command queue so it can create a native Apple Note or Reminder.

This is a device bridge, not a cloud Notes/Reminders API. The server stores each command until an enrolled Apple device runs the Shortcut, performs the native action and sends a receipt. Email synchronisation can run with the MacBook off; native Notes/Reminders creation requires an enrolled device to be available and run the Shortcut.

## Before starting

1. Deploy the Email Assistant over HTTPS and sign in.
2. Open **Accounts & Settings → Apple Notes & Reminders**.
3. Keep the deployed dashboard base URL handy, for example `https://your-dashboard.example`. Use your actual host in every URL below, without a trailing slash.
4. Create one enrolment code per Mac/iPhone. It is single-use and expires after 15 minutes.

Treat enrolment codes and device tokens like passwords. Never put them in source control, a shared Shortcut or a public document.

## Part A — Enrol the device

Create a Shortcut named **Email Assistant Enrol**.

1. Add a **Text** action containing the one-time enrolment code copied from the dashboard.
2. Add a **Dictionary** with:
   - `enrollment_token`: the Text action output
   - `device_name`: a label such as `Mehul iPhone` or `Mehul MacBook`
3. Add a **URL** action:
   `https://YOUR-DASHBOARD-HOST/api/apple/device/enroll`
4. Add **Get Contents of URL**. Set Method to **POST**, Request Body to **JSON**, and pass the Dictionary from step 2.
5. Run the Shortcut once before the enrolment code expires. The response contains `device_id`, `device_name` and `device_token`.
6. Copy the returned `device_token` into a private Text action in the queue-runner Shortcut (Part B). Treat it like a password. The server stores only its hash and returns the token once.
7. Remove the one-time enrolment-code Text action after successful enrolment. The code cannot be reused.

Repeat these steps for each device. Revoke a lost/shared device in dashboard settings, then enrol it again using a new code.

## Part B — Create the queue-runner Shortcut

Create a Shortcut named **Email Assistant Process Queue**.

### 1. Poll the server

1. Add a **Text** action containing the private device token from Part A.
2. Add a **URL** action:
   `https://YOUR-DASHBOARD-HOST/api/apple/device/commands/poll`
3. Add **Get Contents of URL**:
   - Method: **POST**
   - Request Headers: `X-Apple-Device-Token` = the private token from step 1
   - No request body is required.
4. The response is a dictionary with a `commands` list. If it is empty, stop successfully.
5. Use **Repeat with Each** on the `commands` list. The server leases at most one command per poll, for three minutes.

### 2. Read the command values

Within the Repeat loop, get these values from the current command dictionary:

- `id`
- `command_type` (`note` or `reminder`)
- `payload.title`
- `payload.body`
- `payload.due_at` (ISO 8601 timestamp for Reminders)
- `payload.idempotency_marker`
- `lease_token`

Keep the idempotency marker in the native item. If a network interruption occurs after creating the item but before returning a receipt, the next attempt can find the marker and avoid creating a duplicate.

### 3. Handle a Note

When `command_type` is `note`:

1. Use **Find Notes** to search for a Note whose body contains the exact `idempotency_marker`.
2. If a match exists, do not create another Note. Continue to the receipt step and report success.
3. Otherwise use **Create Note**. Set the note content to the title, a blank line, the body, and the idempotency marker on its own final line.
4. Allow Shortcuts to request Notes access when prompted.

### 4. Handle a Reminder

When `command_type` is `reminder`:

1. Use **Find Reminders** to search for a Reminder whose Notes contain the exact `idempotency_marker`.
2. If a match exists, do not create another Reminder. Continue to the receipt step and report success.
3. Otherwise parse `payload.due_at` as a Date (ISO 8601), then use **Create Reminder** with:
   - Title: `payload.title`
   - Notes: `payload.body` followed by the idempotency marker on a separate line
   - Due Date: the parsed `payload.due_at` date/time
4. The server converts the supplied Asia/Kolkata date/time to UTC before queueing. Parse the ISO timestamp as a date/time value, not as plain text.
5. Allow Shortcuts to request Reminders access when prompted.

### 5. Return a receipt

After creating the native item (or finding the same idempotency marker), send a receipt:

1. Add a **Dictionary**:
   - `lease_token`: the current command's `lease_token`
   - `success`: Boolean `true`
   - `error_message`: empty text
   - `native_record_id`: optional; omit if Shortcuts does not expose a stable identifier
2. Add a **URL** whose path ends with the current command's `id`:
   `https://YOUR-DASHBOARD-HOST/api/apple/device/commands/COMMAND_ID/result`
   Use the command ID variable in place of `COMMAND_ID`.
3. Add **Get Contents of URL**:
   - Method: **POST**
   - Request Headers: `X-Apple-Device-Token` = the private device token
   - Request Body: **JSON**, using the Dictionary from step 1
4. Confirm the returned command status is `completed`. The dashboard marks the action complete only after this receipt is accepted.

On a native-action error, send a receipt with `success` = Boolean `false` and place the error details in `error_message`. The dashboard will show the command as failed; you can retry it after fixing the issue.

## Part C — Run the Shortcut

Run **Email Assistant Process Queue** manually first. Queue a test Note and Reminder from the dashboard and confirm both appear in Apple Notes/Reminders and show as completed in Email Assistant.

Then, on devices that support it, create a personal **Time of Day** automation to run the queue Shortcut around the review times (for example, 08:05, 12:05 and 17:05 Asia/Kolkata). Keep the Shortcut available for manual runs too.

A Time of Day automation cannot make an unavailable or powered-off device run. Enrol an iPhone as well if you want a second device to process commands while the Mac is off.

## Recovery and security

- **No device available:** commands remain `pending_on_device`; the dashboard must not claim a native item exists.
- **Shortcut stops before receipt:** the three-minute lease expires and a later poll may lease the command again. Search for its idempotency marker before creating anything.
- **Command fails:** inspect the dashboard error, correct the Shortcut or permissions, then use **Retry**. The retry retains the same idempotency marker.
- **Device lost or token exposed:** revoke the device in dashboard settings.
- **Do not share/export the queue-runner Shortcut** while it contains the private device token.
- Native Notes/Reminders access is on the enrolled device. The Email Assistant does not gain general access to your Apple Notes or Reminders library.

## API reference used by the Shortcut

| Operation | Method and path | Authentication |
|---|---|---|
| Enrol device | `POST /api/apple/device/enroll` | One-time enrolment code in JSON |
| Poll command | `POST /api/apple/device/commands/poll` | `X-Apple-Device-Token` header |
| Submit result | `POST /api/apple/device/commands/{id}/result` | Device-token header and leased `lease_token` in JSON |

The dashboard creates enrolment codes and queues commands. The device endpoints are separate so a Shortcut does not need your dashboard login cookie.

## Apple references

- [Request your first API in Shortcuts on iPhone or iPad](https://support.apple.com/en-ge/guide/shortcuts/apd58d46713f/10.0/ios/27)
- [Request your first API in Shortcuts on Mac](https://support.apple.com/en-sg/guide/shortcuts-mac/apd58d46713f/mac)
- [What’s new in Shortcuts for iOS, iPadOS, macOS and other Apple platforms](https://support.apple.com/en-in/125148)
- [Intro to Find and Filter actions in Shortcuts on Mac](https://support.apple.com/en-in/guide/shortcuts-mac/apd3c845e881/mac)
