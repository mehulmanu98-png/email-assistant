#!/usr/bin/env bash
set -Eeuo pipefail

# Encrypted logical backup for the Email Assistant Neon PostgreSQL database.
# Requires: pg_dump, openssl, python3. DATABASE_URL is read from the environment.
# The database URL and passphrase are never printed or written to the backup.

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: Set DATABASE_URL in your private shell environment." >&2
  exit 2
fi
for cmd in pg_dump openssl python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: Missing required command: $cmd" >&2; exit 2; }
done

BACKUP_DIR="${BACKUP_DIR:-$HOME/email-assistant-backups}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
raw="$tmp/email-assistant.dump"
out="$BACKUP_DIR/email-assistant-$stamp.dump.enc"

# pg_dump expects a libpq URL, not SQLAlchemy's driver-qualified URL.
pg_url="$(python3 - "$DATABASE_URL" <<'PY'
import sys
from sqlalchemy.engine import make_url
url = make_url(sys.argv[1])
if not url.drivername.startswith("postgresql"):
    raise SystemExit("DATABASE_URL must be a PostgreSQL URL")
print(url.set(drivername="postgresql").render_as_string(hide_password=False))
PY
)"

echo "Creating logical database dump..."
pg_dump --format=custom --no-owner --no-acl --file "$raw" "$pg_url"
unset pg_url
if [[ ! -s "$raw" ]]; then echo "ERROR: pg_dump produced an empty file." >&2; exit 1; fi

echo "Encrypting backup. Enter a strong backup passphrase when prompted."
openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -in "$raw" -out "$out"
(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$out")" > "$(basename "$out").sha256"
)
chmod 600 "$out" "$out.sha256"
echo "Encrypted backup created: $out"
echo "Store the passphrase separately from this backup. Keep an offline second copy."
