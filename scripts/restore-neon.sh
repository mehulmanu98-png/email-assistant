#!/usr/bin/env bash
set -Eeuo pipefail

# Restore an encrypted Email Assistant dump into a target PostgreSQL database.
# The target should be a NEW/EMPTY database. This does not drop existing objects.
# Requires: pg_restore, openssl, python3. DATABASE_URL is the TARGET URL.

if [[ $# -ne 1 ]]; then echo "Usage: DATABASE_URL=... $0 /path/to/backup.dump.enc" >&2; exit 2; fi
if [[ -z "${DATABASE_URL:-}" ]]; then echo "ERROR: Set target DATABASE_URL in your private shell." >&2; exit 2; fi
for cmd in pg_restore openssl python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: Missing required command: $cmd" >&2; exit 2; }
done
backup="$1"
[[ -f "$backup" ]] || { echo "ERROR: Backup file not found." >&2; exit 2; }
if [[ -f "$backup.sha256" ]]; then (cd "$(dirname "$backup")" && sha256sum -c "$(basename "$backup").sha256"); fi

echo "WARNING: Restore writes database objects and data into the TARGET database."
echo "Use a fresh empty database. This script does not drop existing objects."
read -r -p "Type RESTORE to continue: " confirm
[[ "$confirm" == "RESTORE" ]] || { echo "Cancelled."; exit 1; }

umask 077
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
raw="$tmp/email-assistant.dump"
echo "Decrypting backup. Enter its passphrase when prompted."
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in "$backup" -out "$raw"
pg_url="$(python3 - "$DATABASE_URL" <<'PY'
import sys
from sqlalchemy.engine import make_url
url = make_url(sys.argv[1])
if not url.drivername.startswith("postgresql"):
    raise SystemExit("DATABASE_URL must be a PostgreSQL URL")
print(url.set(drivername="postgresql").render_as_string(hide_password=False))
PY
)"
pg_restore --no-owner --no-acl --exit-on-error --dbname "$pg_url" "$raw"
unset pg_url
echo "Restore completed. Verify the app health endpoint and mailbox counts before switching production traffic."
