#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/backups"

cat > "$tmp/bin/pg_dump" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
[[ -f "$PGPASSFILE" ]]
[[ "$(stat -c '%a' "$PGPASSFILE")" == "600" ]]
grep -Fq 'host.example:5432:neondb:user:p@ss\\:word' "$PGPASSFILE"
[[ "$*" != *'p@ss:word'* ]]
out=""
while (($#)); do
  if [[ "$1" == "--file" ]]; then out="$2"; shift 2; else shift; fi
done
printf 'fake-postgres-dump' > "$out"
SH
cat > "$tmp/bin/pg_restore" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
[[ -f "$PGPASSFILE" ]]
[[ "$(stat -c '%a' "$PGPASSFILE")" == "600" ]]
grep -Fq 'host.example:5432:neondb:user:p@ss\\:word' "$PGPASSFILE"
[[ "$*" != *'p@ss:word'* ]]
SH
cat > "$tmp/bin/openssl" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
input=""; output=""
while (($#)); do
  case "$1" in
    -in) input="$2"; shift 2;;
    -out) output="$2"; shift 2;;
    *) shift;;
  esac
done
cp "$input" "$output"
SH
chmod +x "$tmp/bin/"*
export PATH="$tmp/bin:$PATH"
export DATABASE_URL='postgresql+psycopg://user:p%40ss%3Aword@host.example:5432/neondb?sslmode=require'
export BACKUP_DIR="$tmp/backups"

bash "$ROOT/scripts/backup-neon.sh" </dev/null
backup="$(find "$BACKUP_DIR" -name '*.dump.enc' -print -quit)"
[[ -n "$backup" && -s "$backup" && -s "$backup.sha256" ]]
printf 'RESTORE\n' | bash "$ROOT/scripts/restore-neon.sh" "$backup"
echo "Backup/restore script harness passed."
