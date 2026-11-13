#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Desktop, then run this script again."
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required."
  exit 1
fi
if [[ ! -f .env.example ]]; then
  echo "Run this script from the repository root."
  exit 1
fi
if [[ -f .env ]]; then
  echo ".env already exists; refusing to overwrite it."
  exit 1
fi

read -r -p "Owner email for the private dashboard: " OWNER_EMAIL
if [[ -z "$OWNER_EMAIL" ]]; then echo "Email is required."; exit 1; fi
read -r -s -p "Choose a unique dashboard password (at least 12 characters): " OWNER_PASSWORD
echo
if [[ ${#OWNER_PASSWORD} -lt 12 ]]; then echo "Password must be at least 12 characters."; exit 1; fi

JWT_SECRET="$(openssl rand -hex 48)"
FIELD_ENCRYPTION_KEY="$(openssl rand -hex 48)"
POSTGRES_PASSWORD="$(openssl rand -hex 32)"

umask 077
cat > .env <<EOF
APP_ENV=development
DATABASE_URL=postgresql+psycopg://emailassistant:${POSTGRES_PASSWORD}@db:5432/emailassistant
JWT_SECRET=${JWT_SECRET}
BOOTSTRAP_EMAIL=${OWNER_EMAIL}
BOOTSTRAP_PASSWORD=${OWNER_PASSWORD}
FIELD_ENCRYPTION_KEY=${FIELD_ENCRYPTION_KEY}
FRONTEND_ORIGIN=http://localhost:8080
TIMEZONE=Asia/Kolkata
MAX_ACTIVE_TASKS=3
AI_PROVIDER=disabled
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
EOF
chmod 600 .env
unset OWNER_PASSWORD JWT_SECRET FIELD_ENCRYPTION_KEY POSTGRES_PASSWORD

echo "Building and starting the local Email Assistant containers..."
docker compose up --build -d
echo
echo "Local dashboard: http://localhost:8080"
echo "API health:      http://localhost:8000/api/health"
echo "Your .env contains generated secrets. Keep it private and do not commit it."
echo "This is a local foundation; remote production use requires HTTPS and the pending integrations listed in CHECKLIST.md."
