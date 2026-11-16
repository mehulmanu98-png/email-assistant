#!/usr/bin/env bash
set -euo pipefail

SERVICE="${SERVICE:-email-assistant}"
WORKER_JOB="${WORKER_JOB:-email-assistant-mail-worker}"
SCHEDULER_JOB="${SCHEDULER_JOB:-email-assistant-mail-sync}"
REGION="${REGION:-asia-south1}"
RUNTIME_SA_NAME="email-assistant-runtime"
SCHEDULER_SA_NAME="email-assistant-scheduler"

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
gcloud config set project "$PROJECT_ID" >/dev/null
echo
echo "Enabling Cloud Run, Cloud Build, Secret Manager and Cloud Scheduler APIs..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com

secret_exists() {
  gcloud secrets describe "$1" --project "$PROJECT_ID" >/dev/null 2>&1
}
read_secret() {
  gcloud secrets versions access latest --secret="$1" --project "$PROJECT_ID"
}

if gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" >/dev/null 2>&1; then
  SERVICE_EXISTS=true
  EXISTING_EMAIL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(spec.template.spec.containers[0].env[?(@.name=="BOOTSTRAP_EMAIL")].value)')"
else
  SERVICE_EXISTS=false
  EXISTING_EMAIL=""
fi
if [[ "$SERVICE_EXISTS" == "true" ]] && { ! secret_exists "email-assistant-field-key" || ! secret_exists "email-assistant-jwt-secret" || ! secret_exists "email-assistant-bootstrap-password" || ! secret_exists "email-assistant-neon-url"; }; then
  echo "The existing Cloud Run service is missing one or more persistent database/authentication secrets in Secret Manager. Stop and restore the original secrets before redeploying; generating replacements could make mailbox credentials unreadable or lock you out."
  exit 1
fi
if [[ "$SERVICE_EXISTS" == "true" && -z "$EXISTING_EMAIL" ]]; then
  echo "Could not safely read the existing dashboard login email from Cloud Run. Stop and inspect the service BOOTSTRAP_EMAIL before redeploying."
  exit 1
fi
if [[ -n "$EXISTING_EMAIL" ]]; then
  read -r -p "Dashboard login email [$EXISTING_EMAIL] (press Enter to keep): " ENTERED_EMAIL
  if [[ -n "$ENTERED_EMAIL" && "$ENTERED_EMAIL" != "$EXISTING_EMAIL" ]]; then
    echo "The existing Neon user is not renamed by redeployment. Keep the current login email or change it separately in the database."
    exit 1
  fi
  BOOTSTRAP_EMAIL="$EXISTING_EMAIL"
else
  read -r -p "Dashboard login email: " BOOTSTRAP_EMAIL
  [[ -n "$BOOTSTRAP_EMAIL" ]] || { echo "Dashboard email is required."; exit 1; }
fi

if secret_exists "email-assistant-neon-url"; then
  read -r -s -p "New Neon pooled PostgreSQL URL (press Enter to keep the saved one): " NEW_NEON_DATABASE_URL; echo
  if [[ -n "$NEW_NEON_DATABASE_URL" ]]; then
    NEON_DATABASE_URL="$NEW_NEON_DATABASE_URL"
  else
    NEON_DATABASE_URL="$(read_secret "email-assistant-neon-url")"
  fi
else
  read -r -s -p "Neon pooled PostgreSQL connection URL: " NEON_DATABASE_URL; echo
fi
[[ "$NEON_DATABASE_URL" == postgresql://* || "$NEON_DATABASE_URL" == postgresql+psycopg://* ]] || {
  echo "Use the Neon pooled PostgreSQL connection URL, not a SQLite URL."; exit 1;
}

if secret_exists "email-assistant-bootstrap-password"; then
  BOOTSTRAP_PASSWORD="$(read_secret "email-assistant-bootstrap-password")"
  echo "Existing dashboard bootstrap secret retained; redeployment will not change the current database login password."
else
  read -r -s -p "Choose a unique dashboard password (12+ characters): " BOOTSTRAP_PASSWORD; echo
  [[ ${#BOOTSTRAP_PASSWORD} -ge 12 ]] || { echo "Password must be at least 12 characters."; exit 1; }
fi

if secret_exists "email-assistant-jwt-secret"; then
  JWT_SECRET="$(read_secret "email-assistant-jwt-secret")"
else
  JWT_SECRET="$(openssl rand -hex 48)"
fi
if secret_exists "email-assistant-field-key"; then
  FIELD_ENCRYPTION_KEY="$(read_secret "email-assistant-field-key")"
  echo "Existing mailbox encryption key retained."
else
  FIELD_ENCRYPTION_KEY="$(openssl rand -hex 48)"
fi

if secret_exists "email-assistant-google-client-id" && secret_exists "email-assistant-google-client-secret"; then
  GOOGLE_CLIENT_ID="$(read_secret "email-assistant-google-client-id")"
  GOOGLE_CLIENT_SECRET="$(read_secret "email-assistant-google-client-secret")"
  read -r -p "Replace the saved Google OAuth client? (y/N): " REPLACE_GOOGLE
  if [[ "$REPLACE_GOOGLE" =~ ^[Yy]$ ]]; then
    read -r -p "New Google OAuth Web Client ID: " GOOGLE_CLIENT_ID
    read -r -s -p "New Google OAuth Web Client Secret: " GOOGLE_CLIENT_SECRET; echo
    [[ -n "$GOOGLE_CLIENT_ID" && -n "$GOOGLE_CLIENT_SECRET" ]] || { echo "Both Google OAuth values are required."; exit 1; }
  fi
else
  read -r -p "Google OAuth Web Client ID (optional; Enter to connect Gmail later): " GOOGLE_CLIENT_ID
  if [[ -n "$GOOGLE_CLIENT_ID" ]]; then
    read -r -s -p "Google OAuth Web Client Secret: " GOOGLE_CLIENT_SECRET; echo
    [[ -n "$GOOGLE_CLIENT_SECRET" ]] || { echo "Client ID and secret must be supplied together."; exit 1; }
  else
    GOOGLE_CLIENT_SECRET=""
  fi
fi

RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

create_service_account() {
  local name="$1" email="$2"
  if ! gcloud iam service-accounts describe "$email" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$name" --display-name="$name" --project "$PROJECT_ID"
  fi
}
create_service_account "$RUNTIME_SA_NAME" "$RUNTIME_SA"
create_service_account "$SCHEDULER_SA_NAME" "$SCHEDULER_SA"

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
echo "Building and deploying the dashboard/API to Cloud Run in $REGION..."
gcloud run deploy "$SERVICE" \
  --source . --project "$PROJECT_ID" --region "$REGION" \
  --service-account "$RUNTIME_SA" --allow-unauthenticated \
  --port 8080 --memory 512Mi --cpu 1 --max 1 \
  --set-env-vars "APP_ENV=production,BOOTSTRAP_EMAIL=$BOOTSTRAP_EMAIL,TIMEZONE=Asia/Kolkata,INITIAL_SYNC_DAYS=90,MAX_MESSAGES_PER_SYNC=500,FRONTEND_ORIGIN=https://placeholder.invalid,GOOGLE_REDIRECT_URI=https://placeholder.invalid/api/oauth/gmail/callback" \
  --set-secrets "$SECRET_MAP"

IMAGE_URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(spec.template.spec.containers[0].image)')"
SERVICE_URL_PUBLIC="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
GOOGLE_REDIRECT_URI="$SERVICE_URL_PUBLIC/api/oauth/gmail/callback"
gcloud run services update "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --update-env-vars "FRONTEND_ORIGIN=$SERVICE_URL_PUBLIC,GOOGLE_REDIRECT_URI=$GOOGLE_REDIRECT_URI" >/dev/null

echo
echo "Deploying the one-shot mailbox worker job..."
gcloud run jobs deploy "$WORKER_JOB" \
  --project "$PROJECT_ID" --region "$REGION" --image "$IMAGE_URL" \
  --service-account "$RUNTIME_SA" --tasks 1 --parallelism 1 \
  --max-retries 0 --task-timeout 900s --cpu 1 --memory 512Mi \
  --command python --args="-m,app.worker,--scheduled-once" \
  --set-env-vars "TIMEZONE=Asia/Kolkata,MAX_MESSAGES_PER_SYNC=500" \
  --set-secrets "$SECRET_MAP"

# Only this separate scheduler identity can start the worker job.
gcloud run jobs add-iam-policy-binding "$WORKER_JOB" \
  --project "$PROJECT_ID" --region "$REGION" \
  --member="serviceAccount:$SCHEDULER_SA" --role="roles/run.invoker" >/dev/null

echo "Testing worker-to-Neon connectivity before enabling the recurring schedule..."
gcloud run jobs execute "$WORKER_JOB" --project "$PROJECT_ID" --region "$REGION" --wait

SCHEDULER_URI="https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/$WORKER_JOB:run"
SCHEDULER_FLAGS=(
  "--project=$PROJECT_ID"
  "--location=$REGION"
  "--schedule=*/15 * * * *"
  "--time-zone=Asia/Kolkata"
  "--uri=$SCHEDULER_URI"
  "--http-method=POST"
  "--headers=Content-Type=application/json"
  "--message-body={}"
  "--oauth-service-account-email=$SCHEDULER_SA"
  "--oauth-token-scope=https://www.googleapis.com/auth/cloud-platform"
  "--attempt-deadline=60s"
)

if gcloud scheduler jobs describe "$SCHEDULER_JOB" --project "$PROJECT_ID" --location "$REGION" >/dev/null 2>&1; then
  echo "Updating existing Cloud Scheduler job..."
  gcloud scheduler jobs update http "$SCHEDULER_JOB" "${SCHEDULER_FLAGS[@]}"
else
  echo "Creating Cloud Scheduler job..."
  gcloud scheduler jobs create http "$SCHEDULER_JOB" "${SCHEDULER_FLAGS[@]}"
fi

echo
echo "Dashboard URL: $SERVICE_URL_PUBLIC"
echo "Gmail OAuth redirect URI: $GOOGLE_REDIRECT_URI"
echo "Add that redirect URI to the Google OAuth Web client to enable Gmail."
echo "Cloud Scheduler now starts the Cloud Run worker every 15 minutes in Asia/Kolkata."
echo "The worker performs actual mailbox syncs at the saved times (default 08:00, 11:00, 14:00, 17:00) and handles manual Sync Now jobs."
echo "The GitHub NEON_DATABASE_URL secret you added earlier is not needed for the primary scheduler; you may leave it there."
echo "Review Cloud Billing and set a budget alert; free-tier limits are not a hard spending cap."
unset NEON_DATABASE_URL BOOTSTRAP_PASSWORD GOOGLE_CLIENT_SECRET JWT_SECRET FIELD_ENCRYPTION_KEY
