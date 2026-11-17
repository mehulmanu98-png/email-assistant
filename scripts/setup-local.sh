#!/usr/bin/env bash
set -euo pipefail
if ! command -v docker >/dev/null 2>&1; then echo "Docker is required. Install Docker Desktop, then retry."; exit 1; fi
if ! docker compose version >/dev/null 2>&1; then echo "Docker Compose v2 is required."; exit 1; fi
if [[ ! -f .env.example ]]; then echo "Run this script from the repository root."; exit 1; fi
if [[ -f .env ]]; then echo ".env already exists; refusing to overwrite it."; exit 1; fi

read -r -p "Owner email for the private dashboard: " OWNER_EMAIL
if [[ -z "$OWNER_EMAIL" ]]; then echo "Email is required."; exit 1; fi
read -r -s -p "Choose a unique dashboard password (at least 12 characters): " OWNER_PASSWORD
echo
if [[ \${#OWNER_PASSWORD} -lt 12 ]]; then echo "Password must be at least 12 characters."; exit 1; fi
read -r -s -p "Neon pooled PostgreSQL connection URL: " DATABASE_URL
echo
if [[ "$DATABASE_URL" != postgresql://* && "$DATABASE_URL" != postgresql+psycopg://* ]]; then
  echo "Use the Neon pooled PostgreSQL URL. No local database is configured by this zero-cost setup."
  exit 1
fi
read -r -p "Google OAuth Client ID (optional; leave blank to configure Gmail later): " GOOGLE_CLIENT_ID
read -r -s -p "Google OAuth Client Secret (optional; leave blank to configure Gmail later): " GOOGLE_CLIENT_SECRET
echo
if [[ -n "$GOOGLE_CLIENT_ID" && -z "$GOOGLE_CLIENT_SECRET" ]] || [[ -z "$GOOGLE_CLIENT_ID" && -n "$GOOGLE_CLIENT_SECRET" ]]; then
  echo "Google OAuth Client ID and Secret must be supplied together."
  exit 1
fi

JWT_SECRET="$(openssl rand -hex 48)"
FIELD_ENCRYPTION_KEY="$(openssl rand -hex 48)"
umask 077
cat > .env <<EOF
APP_ENV=development
DATABASE_URL=$DATABASE_URL
JWT_SECRET=$JWT_SECRET
BOOTSTRAP_EMAIL=$OWNER_EMAIL
BOOTSTRAP_PASSWORD=$OWNER_PASSWORD
FIELD_ENCRYPTION_KEY=$FIELD_ENCRYPTION_KEY
FRONTEND_ORIGIN=http://localhost:8080
TIMEZONE=Asia/Kolkata
MAX_ACTIVE_TASKS=3
AI_PROVIDER=disabled
GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=$GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI=http://localhost:8080/api/oauth/gmail/callback
AUTO_SYNC_TIMES=08:00,12:00,17:00
INITIAL_SYNC_DAYS=90
MAX_MESSAGES_PER_SYNC=500
EOF
chmod 600 .env
unset OWNER_PASSWORD JWT_SECRET FIELD_ENCRYPTION_KEY GOOGLE_CLIENT_SECRET DATABASE_URL

echo "Building and starting the local Email Assistant containers..."
docker compose up --build -d
echo
echo "Local dashboard: http://localhost:8080"
echo "API health:      http://localhost:8080/api/health"
echo "The dashboard and API run on this Mac; GitHub Actions handles scheduled mailbox sync while it is off."
echo "Your .env contains the Neon URL and private secrets. Keep it private and do not commit it."
echo "AI processing remains disabled; no paid hosting or API is configured."
