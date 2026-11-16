#!/usr/bin/env bash
set -euo pipefail
umask 077

CREDENTIALS_PATH="${SIWC_CREDENTIALS_PATH:-$HOME/.config/email-assistant/siwc/credentials.json}"
SIWC_DIR="$(dirname "$CREDENTIALS_PATH")"
HOST_ID_PATH="${SIWC_HOST_ID_PATH:-$SIWC_DIR/host_id}"
LOCK_PATH="${HOST_ID_PATH}.lock"

mkdir -p "$SIWC_DIR"
chmod 700 "$SIWC_DIR"

# Prevent two first-time setup attempts from generating different VM identities.
exec 9>"$LOCK_PATH"
chmod 600 "$LOCK_PATH"
flock -x 9

if [[ -L "$HOST_ID_PATH" ]]; then
  echo "Host ID path must not be a symbolic link. Stop and inspect it locally."
  exit 1
elif [[ -f "$HOST_ID_PATH" ]]; then
  HOST_ID="$(cat "$HOST_ID_PATH")"
  python3 - "$HOST_ID" <<'PY'
import sys
import uuid
value = sys.argv[1]
if not value.startswith("urn:uuid:"):
    raise SystemExit("Existing host ID is not a UUID URI.")
try:
    parsed = uuid.UUID(value[len("urn:uuid:"):])
except ValueError:
    raise SystemExit("Existing host ID is not a valid UUID URI.")
if parsed.version != 4:
    raise SystemExit("Existing host ID must be UUIDv4.")
PY
elif [[ -e "$HOST_ID_PATH" ]]; then
  echo "Host ID path exists but is not a regular file. Stop and inspect it locally."
  exit 1
else
  HOST_ID="$(python3 -c 'import uuid; print("urn:uuid:" + str(uuid.uuid4()))')"
  TEMP_FILE="$(mktemp "${HOST_ID_PATH}.tmp.XXXXXX")"
  trap 'rm -f "$TEMP_FILE"' EXIT
  printf '%s' "$HOST_ID" > "$TEMP_FILE"
  chmod 600 "$TEMP_FILE"
  mv "$TEMP_FILE" "$HOST_ID_PATH"
  trap - EXIT
fi

chmod 600 "$HOST_ID_PATH"
echo "Email Assistant AI VM host ID prepared:"
echo "$HOST_ID"
echo
echo "This is a non-secret identifier. Copy it to the Mac for the first SIWC sign-in."
echo "Do not delete or regenerate it after credentials have been imported."
echo "Credential directory: $SIWC_DIR (owner-only permissions)"
