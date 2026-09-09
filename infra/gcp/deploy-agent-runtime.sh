#!/usr/bin/env bash
set -euo pipefail

CLIO_PROJECT_ID="${CLIO_PROJECT_ID:-clio-continuity-20260909}"
CLIO_REGION="${CLIO_REGION:-us-central1}"
CLIO_STAGING_BUCKET="${CLIO_STAGING_BUCKET:-gs://${CLIO_PROJECT_ID}-agent-runtime}"
CLIO_SERVICE="${CLIO_SERVICE:-clio-api}"
CLIO_API_BASE_URL="${CLIO_AGENT_API_BASE_URL:-}"
CLIO_PYTHON="${CLIO_PYTHON:-python3}"
CLIO_GCLOUD_ACCESS_TOKEN="${CLIO_GCLOUD_ACCESS_TOKEN:-$(gcloud auth print-access-token)}"

if [[ -z "${CLIO_API_BASE_URL}" ]]; then
  CLIO_API_BASE_URL="$(gcloud run services describe "${CLIO_SERVICE}" --project="${CLIO_PROJECT_ID}" --region="${CLIO_REGION}" --format='value(status.url)')"
fi
if [[ -z "${CLIO_API_BASE_URL}" ]]; then
  echo "Unable to resolve CLIO Agent tool API URL" >&2
  exit 1
fi

gcloud storage buckets describe "${CLIO_STAGING_BUCKET}" >/dev/null 2>&1 || \
  gcloud storage buckets create "${CLIO_STAGING_BUCKET}" --location="${CLIO_REGION}" --uniform-bucket-level-access

"${CLIO_PYTHON}" -m pip install --upgrade -r agent_runtime/requirements.txt
for model in gemini-3.8-flash gemini-3.7-flash gemini-2.5-flash; do
  PYTHONPATH=. "${CLIO_PYTHON}" agent_runtime/deploy.py \
    --project="${CLIO_PROJECT_ID}" \
    --location="${CLIO_REGION}" \
    --staging-bucket="${CLIO_STAGING_BUCKET}" \
    --display-name="clio-${model}" \
    --model="${model}" \
    --api-base-url="${CLIO_API_BASE_URL}" \
    --access-token="${CLIO_GCLOUD_ACCESS_TOKEN}"
done
