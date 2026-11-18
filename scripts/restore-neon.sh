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
pg_url="$(python3 - "$DATABASE_URL" "$tmp/pgpass" <<'PY'
import os, sys
from urllib.parse import urlsplit, unquote, parse_qs
raw, passfile = sys.argv[1], sys.argv[2]
u = urlsplit(raw)
if not u.scheme.startswith("postgresql") or not u.hostname or not u.path:
    raise SystemExit("DATABASE_URL must be a PostgreSQL URL")
host, port = u.hostname, u.port or 5432
user, password, dbname = unquote(u.username or ""), unquote(u.password or ""), unquote(u.path.lstrip("/"))
def esc(value): return value.replace("\\\\", "\\\\\\\\").replace(":", "\\\\:")
with open(passfile, "w", encoding="utf-8") as f:
    if password:
        f.write(":".join(esc(x) for x in (host, str(port), dbname, user, password)) + "\\n")
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
pg_restore --no-owner --no-acl --exit-on-error --dbname "$pg_url" "$raw"
unset pg_url
echo "Restore completed. Verify the app health endpoint and mailbox counts before switching production traffic."
