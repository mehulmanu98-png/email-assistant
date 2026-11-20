# Gemini AI setup for Email Assistant

The Gemini integration is implemented server-side. It uses the Gemini Interactions API with `store: false`; the browser never receives the API key.

## Required Render environment variables

On the existing Render service `email-assistant-mehul`, open **Environment** and add:

- `GEMINI_API_KEY` — API key created in Google AI Studio
- `GEMINI_MODEL` — optional; defaults to `gemini-3.8-flash`

Do not put the API key in GitHub source, frontend variables, chat messages, or screenshots. Save the variables and let Render redeploy.

Create the key in Google AI Studio: https://aistudio.google.com/api-keys

## Privacy and billing decision

Google's published Gemini API pricing currently lists free-tier standard model input/output as free of charge, but says free-tier content may be used to improve Google's products. Paid-tier content is not used for product improvement. See https://ai.google.dev/gemini-api/docs/pricing

Because email can contain confidential or personal information, do not use the free tier with real mailbox content unless the account owner explicitly accepts Google's free-tier data-use terms. A free-tier key is suitable for testing with synthetic or non-sensitive email text. Paid tier may have charges and must not be enabled without separate approval.

No billing is enabled by this integration. Do not upgrade the Google project to paid tier without explicit approval.

## Available features after the key is configured

- Draft a reply from the selected email/thread
- Rephrase the current edited draft
- Correct grammar and spelling only
- Continue a conversational editing session (for example: "make it shorter", "more polite", "add the delivery point")
- Ask a question about the selected email/thread
- Generate an individual email summary on demand
- Generate an entire-thread summary on demand

AI suggestions only update the editable internal draft when the user chooses **Apply to draft**. Sending still requires the existing explicit **Approve & Send** action.

The integration sends only the email/thread selected by the user when they request an AI action. It does not automatically process the whole inbox.

## Privacy implementation

- API key is read only from server environment variable `GEMINI_API_KEY`.
- Requests are sent server-to-server to Google's Gemini Interactions API.
- Requests use `store: false` (stateless request mode).
- Email body content is treated as untrusted data, not instructions.
- AI never sends email or performs mailbox actions.
- Thread retrieval is read-only and reports whether the provider scan was complete.
