#!/usr/bin/env bash
set -euo pipefail
umask 077

CREDENTIALS_PATH="${SIWC_CREDENTIALS_PATH:-$HOME/.config/email-assistant/siwc/credentials.json}"
SIWC_DIR="$(dirname "$CREDENTIALS_PATH")"
HOST_ID_PATH="${SIWC_HOST_ID_PATH:-$SIWC_DIR/host_id}"

mkdir -p "$SIWC_DIR"
chmod 700 "$SIWC_DIR"

if [[ -f "$HOST_ID_PATH" ]]; then
  HOST_ID="$(cat "$HOST_ID_PATH")"
  [[ "$HOST_ID" == urn:uuid:* ]] || {
    echo "Existing host ID file is not a supported UUID URI. Stop and inspect it locally."
    exit 1
  }
else
  HOST_ID="$(python3 -c 'import uuid; print("urn:uuid:" + str(uuid.uuid4()))')"
  TEMP_FILE="$\{HOST_ID_PATH}.tmp.$$"
  printf '%s' "$HOST_ID" > "$TEMP_FILE"
  chmod 600 "$TEMP_FILE"
  mv "$TEMP_FILE" "$HOST_ID_PATH"
fi

chmod 600 "$HOST_ID_PATH"
echo "Email Assistant AI VM host ID prepared:"
echo "$HOST_ID"
echo
echo "This is a non-secret identifier. Copy it to the Mac for the first SIWC sign-in."
echo "Do not delete or regenerate it after credentials have been imported."
echo "Credential directory: $SIWC_DIR (owner-only permissions)"
