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
pg_url="$(python3 - "$DATABASE_URL" "$tmp/pgpass" <<'PY'
import os, sys
from urllib.parse import urlsplit, unquote, parse_qs
raw, passfile = sys.argv[1], sys.argv[2]
u = urlsplit(raw)
if not u.scheme.startswith("postgresql") or not u.hostname or not u.path:
    raise SystemExit("DATABASE_URL must be a PostgreSQL URL")
host, port = u.hostname, u.port or 5432
user, password, dbname = unquote(u.username or ""), unquote(u.password or ""), unquote(u.path.lstrip("/"))
def esc(value): return value.replace("\\", "\\\\").replace(":", "\\:")
with open(passfile, "w", encoding="utf-8") as f:
    if password:
        f.write(":".join(esc(x) for x in (host, str(port), dbname, user, password)) + "\n")
os.chmod(passfile, 0o600)
query = parse_qs(u.query)
params = []
for key in ("sslmode", "connect_timeout", "application_name"):
    if query.get(key): params.append(key + "=" + query[key][0])
authority = (user + "@" if user else "") + host + ":" + str(port)
return_url = "postgresql://" + authority + "/" + dbname + (("?" + "&".join(params)) if params else "")
print(return_url)
PY
)"
export PGPASSFILE="$tmp/pgpass"

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
