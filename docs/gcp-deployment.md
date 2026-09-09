# CLIO GCP deployment

Project: `clio-continuity-20260909`  
Primary Firebase site: [clio-agentic.web.app](https://clio-agentic.web.app)

## Runtime topology

```text
Browser
  -> Firebase Hosting (clio-agentic)
       /api/** -> Cloud Run clio-api (us-central1)
                         -> ClickHouse Cloud (TLS, repository reads/writes)
                         -> Agent Runtime resources (ADK + Memory Bank)
                              3.8 Flash -> 3.7 Flash -> 2.5 Flash
                         -> OpenRouter fallback (DeepSeek)
```

Firebase Hosting owns the static TanStack client and pins `/api/**` rewrites
to the current Cloud Run revision. Cloud Run reads ClickHouse credentials and
the OpenRouter key from Secret Manager; no browser credential is exposed.

## Agent routing

The primary and fallback Agent Runtime resources are regional control-plane
resources in `us-central1`. Their ADK Gemini clients use Vertex's `global`
model endpoint, which is required for Gemini 3.x availability in this project.
The primary resource has Memory Bank enabled and scopes durable context to
`user_id` and the `editorial-preferences` topic. Each run still receives the
current ClickHouse graph snapshot, and every mutation remains behind an
explicit human approval.

Each managed agent has only read-only tools: revision context, impact,
lineage, timing, screenplay search, removal arithmetic, and a critic check.
The tools call Cloud Run's narrow `/api/v1/agent-tools/*` boundary; Cloud Run
then uses its normal MCP-first/direct-ClickHouse fallback. Agent Runtime never
holds ClickHouse credentials and cannot write a screenplay graph. The agent is
instructed to make a bounded evidence pass before a final human-reviewable
proposal; all graph mutations remain explicit Cloud Run approval operations.

Memory Bank uses a stable `user_id` supplied by the browser. Cloud Run
explicitly retrieves up to four relevant memories before each managed-agent
turn and records the retrieval count in the agent event stream. It is suitable
only for durable, approved editorial preferences and decisions. ClickHouse
remains the source of truth for screenplay text, timed graph nodes, revisions,
and workflow events. The current demo uses an anonymous browser identifier;
production authentication must replace it with signed user/workspace claims.

If a managed resource errors or times out, CLIO tries the next resource and
finally the OpenRouter provider configured by `AGENT_PROVIDER_*`. The event
stream records `gemini_adk` or the fallback provenance so a reviewer can see
which provider served the result.

## Deploy commands

```bash
gcloud config set project clio-continuity-20260909
GOOGLE_APPLICATION_CREDENTIALS=... PYTHONPATH=. \
  python agent_runtime/deploy.py --project=clio-continuity-20260909 \
  --location=us-central1 \
  --staging-bucket=gs://clio-continuity-20260909-agent-runtime \
  --display-name=clio-global-gemini-3-8-flash-memory \
  --model=gemini-3.8-flash \
  --api-base-url="$(gcloud run services describe clio-api --region=us-central1 --format='value(status.url)')"
./infra/gcp/deploy.sh
npx firebase-tools deploy --only hosting:clio-agentic --project clio-continuity-20260909
```

The checked-in `infra/gcp/deploy.sh` contains the current resource IDs and
ordered fallback environment variable. Rotate any local deployer credential
after use.
