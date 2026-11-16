#!/usr/bin/env bash
set -euo pipefail

REPO="mehulmanu98-png/email-assistant"
SERVICE="${SERVICE:-email-assistant}"
REGION="${REGION:-asia-south1}"
RUNTIME_SA_NAME="email-assistant-runtime"

if [[ ! -f Dockerfile || ! -d backend || ! -d frontend ]]; then
  echo "Run this script from the Email Assistant repository root."
  exit 1
fi
command -v gcloud >/dev/null 2>&1 || { echo "Install Google Cloud CLI first."; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "OpenSSL is required."; exit 1; }
gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q . || {
  echo "Sign in first with: gcloud auth login"; exit 1;
}

read -r -p "Google Cloud project ID: " PROJECT_ID
[[ -n "$PROJECT_ID" ]] || { echo "Project ID is required."; exit 1; }
read -r -p "Dashboard login email: " BOOTSTRAP_EMAIL
[[ -n "$BOOTSTRAP_EMAIL" ]] || { echo "Dashboard email is required."; exit 1; }
read -r -s -p "Neon pooled PostgreSQL connection URL: " NEON_DATABASE_URL; echo
[[ "$NEON_DATABASE_URL" == postgresql://* || "$NEON_DATABASE_URL" == postgresql+psycopg://* ]] || {
  echo "Use the Neon PostgreSQL pooled connection URL, not a SQLite URL."; exit 1;
}
read -r -s -p "Unique dashboard password (12+ characters): " BOOTSTRAP_PASSWORD; echo
[[ ${#BOOTSTRAP_PASSWORD} -ge 12 ]] || { echo "Password must be at least 12 characters."; exit 1; }
read -r -p "Google OAuth Web Client ID (optional; Enter to connect Gmail later): " GOOGLE_CLIENT_ID
if [[ -n "$GOOGLE_CLIENT_ID" ]]; then
  read -r -s -p "Google OAuth Web Client Secret: " GOOGLE_CLIENT_SECRET; echo
  [[ -n "$GOOGLE_CLIENT_SECRET" ]] || { echo "Client ID and secret must be supplied together."; exit 1; }
else
  GOOGLE_CLIENT_SECRET=""
fi

JWT_SECRET="$(openssl rand -hex 48)"
FIELD_ENCRYPTION_KEY="$(openssl rand -hex 48)"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo
echo "Enabling required Google Cloud services..."
gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

if ! gcloud iam service-accounts describe "$RUNTIME_SA" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$RUNTIME_SA_NAME" --display-name="Email Assistant runtime" --project "$PROJECT_ID"
fi

put_secret() {
  local name="$1" value="$2"
  if gcloud secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- --project "$PROJECT_ID" >/dev/null
  else
    gcloud secrets create "$name" --replication-policy=automatic --project "$PROJECT_ID" >/dev/null
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- --project "$PROJECT_ID" >/dev/null
  fi
  gcloud secrets add-iam-policy-binding "$name" --member="serviceAccount:$RUNTIME_SA" --role="roles/secretmanager.secretAccessor" --project "$PROJECT_ID" >/dev/null
}

put_secret "email-assistant-neon-url" "$NEON_DATABASE_URL"
put_secret "email-assistant-jwt-secret" "$JWT_SECRET"
put_secret "email-assistant-bootstrap-password" "$BOOTSTRAP_PASSWORD"
put_secret "email-assistant-field-key" "$FIELD_ENCRYPTION_KEY"

SECRET_MAP="DATABASE_URL=email-assistant-neon-url:latest,JWT_SECRET=email-assistant-jwt-secret:latest,BOOTSTRAP_PASSWORD=email-assistant-bootstrap-password:latest,FIELD_ENCRYPTION_KEY=email-assistant-field-key:latest"
if [[ -n "$GOOGLE_CLIENT_ID" ]]; then
  put_secret "email-assistant-google-client-id" "$GOOGLE_CLIENT_ID"
  put_secret "email-assistant-google-client-secret" "$GOOGLE_CLIENT_SECRET"
  SECRET_MAP="$SECRET_MAP,GOOGLE_CLIENT_ID=email-assistant-google-client-id:latest,GOOGLE_CLIENT_SECRET=email-assistant-google-client-secret:latest"
fi

echo
echo "Deploying the private-login dashboard/API to Cloud Run in $REGION..."
gcloud run deploy "$SERVICE" \
  --source . --project "$PROJECT_ID" --region "$REGION" \
  --service-account "$RUNTIME_SA" --allow-unauthenticated \
  --port 8080 --memory 512Mi --cpu 1 --max 1 \
  --set-env-vars "APP_ENV=production,BOOTSTRAP_EMAIL=$BOOTSTRAP_EMAIL,TIMEZONE=Asia/Kolkata,INITIAL_SYNC_DAYS=90,MAX_MESSAGES_PER_SYNC=500,FRONTEND_ORIGIN=https://placeholder.invalid" \
  --set-secrets "$SECRET_MAP"

SERVICE_URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
GOOGLE_REDIRECT_URI="$SERVICE_URL/api/oauth/gmail/callback"
gcloud run services update "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --update-env-vars "FRONTEND_ORIGIN=$SERVICE_URL,GOOGLE_REDIRECT_URI=$GOOGLE_REDIRECT_URI" >/dev/null

echo
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  printf '%s' "$NEON_DATABASE_URL" | gh secret set NEON_DATABASE_URL --repo "$REPO"
  printf '%s' "$FIELD_ENCRYPTION_KEY" | gh secret set EMAIL_ASSISTANT_FIELD_KEY --repo "$REPO"
  echo "GitHub Actions Neon secrets configured."
else
  echo "GitHub CLI is not authenticated. Add these Actions secrets manually:"
  echo "  NEON_DATABASE_URL"
  echo "  EMAIL_ASSISTANT_FIELD_KEY"
fi

echo "Dashboard URL: $SERVICE_URL"
echo "Google OAuth redirect URI: $GOOGLE_REDIRECT_URI"
echo "Add that redirect URI to the Google OAuth Web client. The app's Gmail connection will not work until that is done."
echo "The scheduled mailbox worker checks the Neon queue every 15 minutes via GitHub Actions."
echo "Review Cloud Billing and set a budget alert; free-tier limits are not a hard spending cap."
unset NEON_DATABASE_URL BOOTSTRAP_PASSWORD GOOGLE_CLIENT_SECRET JWT_SECRET FIELD_ENCRYPTION_KEY
