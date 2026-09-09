#!/usr/bin/env bash
set -euo pipefail

# Deploys the application boundary. The Agent Runtime resources are deployed
# separately by deploy-agent-runtime.sh because they use managed ADK sessions
# and Memory Bank rather than Cloud Run containers.

CLIO_PROJECT_ID="${CLIO_PROJECT_ID:-clio-continuity-20260909}"
CLIO_REGION="${CLIO_REGION:-us-central1}"
CLIO_REPOSITORY="${CLIO_REPOSITORY:-clio}"
CLIO_SERVICE="${CLIO_SERVICE:-clio-api}"
CLIO_BUILD_TAG="${CLIO_BUILD_TAG:-$(date +%Y%m%d%H%M%S)}"
CLIO_AGENT_RUNTIME_RESOURCES="${CLIO_AGENT_RUNTIME_RESOURCES:-projects/606988591756/locations/us-central1/reasoningEngines/6594832810249289728,projects/606988591756/locations/us-central1/reasoningEngines/3613449856930021376,projects/606988591756/locations/us-central1/reasoningEngines/5524101998841954304}"

required=(
  CLIO_CLICKHOUSE_HOST
  CLIO_CLICKHOUSE_USER
  CLIO_CLICKHOUSE_PASSWORD
  CLIO_CLICKHOUSE_DATABASE
  AGENT_PROVIDER_URL
  AGENT_PROVIDER_MODEL
  AGENT_PROVIDER_API_KEY
)
for item in "${required[@]}"; do
  if [[ -z "${!item:-}" ]]; then
    echo "Missing required environment variable: ${item}" >&2
    exit 1
  fi
done

gcloud config set project "${CLIO_PROJECT_ID}"
gcloud artifacts repositories describe "${CLIO_REPOSITORY}" --location="${CLIO_REGION}" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "${CLIO_REPOSITORY}" --repository-format=docker --location="${CLIO_REGION}" --description="CLIO container images"
gcloud tasks queues describe clio-agent-runs --location="${CLIO_REGION}" >/dev/null 2>&1 || \
  gcloud tasks queues create clio-agent-runs --location="${CLIO_REGION}"

upsert_secret() {
  local name="$1"
  local value="$2"
  gcloud secrets describe "${name}" >/dev/null 2>&1 || gcloud secrets create "${name}" --replication-policy=automatic
  printf '%s' "${value}" | gcloud secrets versions add "${name}" --data-file=-
}

upsert_secret clio-clickhouse-password "${CLIO_CLICKHOUSE_PASSWORD}"
upsert_secret clio-openrouter-api-key "${AGENT_PROVIDER_API_KEY}"

gcloud builds submit --config=infra/gcp/cloudbuild.yaml \
  --substitutions="_REGION=${CLIO_REGION},_REPOSITORY=${CLIO_REPOSITORY},_IMAGE=${CLIO_SERVICE},_TAG=${CLIO_BUILD_TAG}" .

CLIO_IMAGE="${CLIO_REGION}-docker.pkg.dev/${CLIO_PROJECT_ID}/${CLIO_REPOSITORY}/${CLIO_SERVICE}:${CLIO_BUILD_TAG}"
gcloud run deploy "${CLIO_SERVICE}" \
  --image="${CLIO_IMAGE}" \
  --region="${CLIO_REGION}" \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=3 \
  --set-env-vars="CLIO_ENV=production,CLIO_DATABASE_MODE=cloud,CLIO_CLICKHOUSE_PORT=8443,CLIO_CLICKHOUSE_SECURE=true,CLIO_USE_MEMORY_STORE=false,CLIO_CREATE_DATABASE=false,CLIO_SEED_DEMO=false,CLIO_BOOTSTRAP_SCHEMA=true,AGENT_MODE=live,GOOGLE_CLOUD_PROJECT=${CLIO_PROJECT_ID},GOOGLE_CLOUD_LOCATION=${CLIO_REGION},CLIO_GEMINI_MODEL_PRIMARY=gemini-3.8-flash,CLIO_GEMINI_MODEL_FALLBACK_1=gemini-3.7-flash,CLIO_GEMINI_MODEL_FALLBACK_2=gemini-2.5-flash,CLIO_AGENT_RUNTIME_RESOURCES=${CLIO_AGENT_RUNTIME_RESOURCES},CLIO_AGENT_EVENT_TRANSPORT=poll" \
  --set-env-vars="CLIO_CLICKHOUSE_HOST=${CLIO_CLICKHOUSE_HOST},CLIO_CLICKHOUSE_USER=${CLIO_CLICKHOUSE_USER},CLIO_CLICKHOUSE_DATABASE=${CLIO_CLICKHOUSE_DATABASE},AGENT_PROVIDER_URL=${AGENT_PROVIDER_URL},AGENT_PROVIDER_MODEL=${AGENT_PROVIDER_MODEL}" \
  --set-secrets="CLIO_CLICKHOUSE_PASSWORD=clio-clickhouse-password:latest,AGENT_PROVIDER_API_KEY=clio-openrouter-api-key:latest"

pnpm build
echo "Cloud Run deployed. Deploy Firebase Hosting with: npx firebase-tools deploy --only hosting:clio-agentic --project ${CLIO_PROJECT_ID}"
