# Apple Notes and Reminders — device Shortcut setup

This guide connects one personally owned iPhone, iPad or Mac to the Email Assistant's Apple command queue.

## Important operating distinction

The Email Assistant cloud service can queue a Note or Reminder while your MacBook is closed. **An enrolled Apple device must still run the Shortcut to poll the queue and create the native item.** The current bridge uses polling, not Apple push notifications. A queued command remains Pending on Device until an enrolled device runs the polling Shortcut and confirms the result.

Mailbox synchronisation is separate: the Cloud Run worker continues independently of your MacBook at the saved mailbox sync times.

A native Apple Reminder may produce the usual alert according to your Reminders settings. The Email Assistant itself does not send push, email or WhatsApp notifications.

## Prerequisites

- The Email Assistant is deployed at an HTTPS dashboard URL.
- You can sign in to the dashboard.
- Notes and Reminders are enabled on the Apple device and you have granted Shortcuts the required permission when prompted.
- Keep the device token private. Do not share the Shortcut, paste the token into GitHub, or put it into a public note.

Apple's Shortcuts app supports API requests through **Get Contents of URL**. The action can use POST and send JSON request bodies and headers. See [Apple's API request guide](https://support.apple.com/guide/shortcuts/request-your-first-api-apd58d46713f/10.0/ios/27).

## 1. Enrol the Apple device

1. Open the Email Assistant dashboard and go to **Accounts & Settings → Apple Notes & Reminders**.
2. Enter a device name such as `Mehul iPhone` and select **Create enrollment code**.
3. The code is one-time and expires after 15 minutes. Keep the dashboard open while enrolling.
4. On the Apple device, open the **Shortcuts** app and create a shortcut named **Email Assistant — Enrol Device**.
5. Add a **URL** action containing:

   `https://YOUR-DASHBOARD-HOST/api/apple/device/enroll`

   Replace `YOUR-DASHBOARD-HOST` with the hostname printed after deployment. Keep `https://`.
6. Add **Get Contents of URL** after the URL action. Expand its options and set:
   - Method: **POST**
   - Request Body: **JSON**
   - `enrollment_token`: the one-time code from the dashboard
   - `device_name`: the same device name you entered in the dashboard
7. Add **Get Dictionary from Input** if Shortcuts has not already interpreted the response as a dictionary. Add **Get Dictionary Value** for the key `device_token`, then **Show Result** so you can copy the returned token once.
8. Copy the `device_token` into a **Text** action at the top of the next shortcut, **Email Assistant — Poll Commands**. Store it only in that private Shortcut. The server stores only a hash and will not show the device token again.
9. Return to the Email Assistant dashboard and refresh the Apple devices section. The enrolled device should appear as Active.

The enrolment request does not use your dashboard password or browser session cookie. The one-time code is exchanged for a separate device token.

## 2. Build the polling Shortcut

Create a second Shortcut named **Email Assistant — Poll Commands**. This version handles one command each time it runs. You can run it manually for acceptance testing; you can later attach it to a Personal Automation supported by your device.

### Poll the queue

1. Add a **Text** action at the top and paste the private `device_token` from step 1.
2. Add a **URL** action with:

   `https://YOUR-DASHBOARD-HOST/api/apple/device/commands/poll`

3. Add **Get Contents of URL**:
   - Method: **POST**
   - Headers: `X-Apple-Device-Token` = the Text action containing your device token
   - No request body is required.
4. Read the JSON response. It has a `commands` array:
   - An empty array means there is nothing waiting.
   - A non-empty array contains one command. Get the first item from the list and read its `id`, `command_type`, `payload` and `lease_token`.
5. Use an **If** action to branch on `command_type`.

The command payload contains:
- `title`: the Note or Reminder title
- `body`: Note content or Reminder notes
- `due_at`: Reminder due date as an ISO 8601 timestamp, or empty for Notes
- `timezone`: the original timezone (normally `Asia/Kolkata`)
- `idempotency_marker`: a unique marker for duplicate prevention

A poll leases the command for three minutes. Process it promptly and submit the result before the lease expires. If it expires, poll again for a renewed lease.

### Note branch

1. Build the Note text using the command's `title`, `body` and `idempotency_marker`. Keep the marker in the saved Note so a retry can identify the item.
2. Before creating anything, use **Find Notes** to look for an existing Note containing the exact idempotency marker. If one exists, treat the command as already completed rather than creating a duplicate.
3. If no matching Note exists, use **Create Note** with the prepared text. Turn off **Show Compose Sheet** if that option is available, so the Shortcut can create it without waiting for you to press Done.
4. Capture the created Note's native identifier only if Shortcuts exposes it on your device. The server accepts an empty identifier; do not invent one.

### Reminder branch

1. Build the Reminder notes field from the command's `body` plus the `idempotency_marker`. The marker must be saved with the Reminder.
2. Before creating the Reminder, search Reminders for an existing item containing that exact marker. If one exists, treat the command as already completed and do not create a second item.
3. If no match exists, use **New Reminder**:
   - Title: command `title`
   - Notes: prepared text containing the marker
   - Due date: parse the command `due_at` ISO timestamp as a Date and use that Date for the Reminder due date
4. Capture the created Reminder's native identifier only if Shortcuts exposes it. The server accepts an empty identifier.

The exact filter labels exposed by **Find Notes** and **Find Reminders** can vary by OS version. Use the available content/body/notes filter that searches for the full marker, and test that a second run finds the first item.

## 3. Report the result to the server

After the Note or Reminder exists (or the idempotency check finds that it already exists), submit a result so the dashboard can change the command from Pending on Device to Completed.

1. Add a **URL** action. Use this endpoint, substituting the command `id` returned by the poll:

   `https://YOUR-DASHBOARD-HOST/api/apple/device/commands/COMMAND_ID/result`

2. Add **Get Contents of URL**:
   - Method: **POST**
   - Header: `X-Apple-Device-Token` = your private device token
   - Request Body: **JSON**
   - `lease_token`: the command's `lease_token` from the poll response
   - `success`: `true`
   - `native_record_id`: the native identifier if available, otherwise an empty string
   - `error_message`: an empty string

For example, the JSON result has this shape (replace the placeholders with Shortcut variables):

```json
{
  "lease_token": "LEASE_TOKEN_FROM_POLL",
  "success": true,
  "native_record_id": "",
  "error_message": ""
}
```

If native creation fails, do **not** report success. Submit `success: false` with a short `error_message` while the lease is still valid. If the Shortcut stops before it reports a result, the command lease expires and can be polled again. The idempotency marker is what prevents a retry from creating a duplicate after a native item was created but the server response was lost.

## 4. Test in this order

Use non-sensitive test content first.

1. Enrol the device and confirm that it appears as Active in the dashboard.
2. From an email's detail panel, queue a test Note. Run **Email Assistant — Poll Commands** once. Confirm the Note appears in Apple Notes and the dashboard command changes to Completed.
3. Queue a test Reminder with a due time a few minutes in the future. Run the Shortcut again. Confirm the Reminder exists with the expected due time and the dashboard reports Completed.
4. Verify the idempotency behaviour: repeat processing of the same command must find the marker and must not create a second Note or Reminder.
5. Revoke the device from the dashboard and verify that the old token can no longer poll commands.

## 5. Limitations and recovery

- The server does not wake an Apple device. A manual run or an automation configured on that device is required to poll the queue.
- The Shortcut above polls one command per run. Run it again when more commands are waiting, or extend it with a bounded Repeat loop after the single-command flow is working.
- A device that is offline, powered off or has not run the Shortcut leaves commands pending. This does not affect cloud mailbox synchronisation.
- A command lease is three minutes. If the result submission fails, the server permits a later poll after lease expiry.
- Only the owner can revoke the device in **Accounts & Settings**. Revocation invalidates the device token.
- Never share a Shortcut that contains the device token. To add a second Apple device, create a separate enrolment code and a separate device token for that device.

