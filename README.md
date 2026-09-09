# CLIO

CLIO (Continuity & Lineage Intelligence Operator) is a script-first change map for a fictional local film. One React
Flow graph keeps the full screenplay in view: a revision source plus timed
scene nodes. Each scene carries action text and narration; longer scenes can
be opened into timed child beats. Select a scene to see its script, narration,
start/end, duration, and graph neighbors, then ask the local agent what an
edit, removal, or insertion would affect.

The synthetic demo is always marked `LOCAL DEMO`: the Titanic storyboard runs
from 00:00 to 03:15:00 across 25 scenes and 125 timed beats. Revision **V5**
marks **SC 17**, the bridge/lookout iceberg collision, as the breaking source
whose downstream survival beats need review.

## Requirements

- Node 22 and pnpm
- Python 3.13
- Docker Desktop/Engine for the local ClickHouse store

## Start locally

From this directory:

```bash
pnpm install

# optional terminal 1 — ClickHouse
docker compose -f infra/docker-compose.yml up -d

# terminal 2 — FastAPI
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
# The checked-in example is local. If your .env targets Cloud, these
# overrides keep this process on the Docker database.
CLIO_DATABASE_MODE=local CLIO_CLICKHOUSE_HOST=127.0.0.1 \
CLIO_CLICKHOUSE_PORT=8123 CLIO_CLICKHOUSE_USER=clio \
CLIO_CLICKHOUSE_PASSWORD=clio-local CLIO_CLICKHOUSE_DATABASE=filmgraph \
CLIO_CLICKHOUSE_SECURE=false uvicorn filmgraph.main:app \
  --host 127.0.0.1 --port 8000 --reload

# terminal 3 — TanStack Start
cd ..
pnpm dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The Python API uses
`127.0.0.1:8000`; ClickHouse uses HTTP `8123` and native `9000`.

## Configuration

```text
GRAPH_QUERY_MODE=auto
AGENT_MODE=live
AGENT_PROVIDER_URL=https://openrouter.ai/api/v1/chat/completions
AGENT_PROVIDER_MODEL=deepseek/deepseek-v4-flash-0731
AGENT_PROVIDER_API_KEY=your-openrouter-key
CLIO_MCP_ENDPOINT=
CLIO_MCP_COMMAND=
CLIO_GITHUB_TOKEN=
CLIO_CLICKHOUSE_HOST=127.0.0.1
CLIO_CLICKHOUSE_PORT=8123
CLIO_CLICKHOUSE_DATABASE=filmgraph
CLIO_CLICKHOUSE_SECURE=false
CLIO_DATABASE_MODE=local
CLIO_BOOTSTRAP_SCHEMA=true
CLIO_CREATE_DATABASE=true
CLIO_SEED_DEMO=true
CLIO_ALLOW_DEMO_RESET=false
CLIO_USE_MEMORY_STORE=false
```

In `auto` mode, reads try a configured ClickHouse MCP tool first, then
`clickhouse-connect`, then the in-memory local seed. The UI labels the selected
source (`CLICKHOUSE MCP`, `DIRECT CLICKHOUSE`, or `LOCAL FALLBACK`). MCP is
read-only; mutations append events in the Python repository. `CLIO_*` is the
current configuration prefix; the older `FILMGRAPH_*` names remain accepted as
backward-compatible aliases.

### ClickHouse Cloud or local Docker

The repository uses the configured database name rather than assuming
`filmgraph`. For the current Cloud target, keep these values in `.env`:

```text
CLIO_DATABASE_MODE=cloud
CLIO_CLICKHOUSE_HOST=<service-host>.clickhouse.cloud
CLIO_CLICKHOUSE_PORT=8443
CLIO_CLICKHOUSE_SECURE=true
CLIO_CLICKHOUSE_DATABASE=clio
CLIO_CREATE_DATABASE=true
CLIO_BOOTSTRAP_SCHEMA=true
CLIO_SEED_DEMO=true
CLIO_ALLOW_DEMO_RESET=false
```

On the first API request CLIO connects to the default database, creates
`clio` when the configured user has permission, applies the shared schema, and
seeds the fictional graph. If the database contains only the earlier
synthetic CLIO fixture, bootstrap performs a bounded demo-scope migration to
the Titanic seed; unrelated Cloud rows are never touched. If the Cloud user
cannot create a database, run `CREATE DATABASE IF NOT EXISTS clio` in the
ClickHouse SQL console (or grant that permission), then set
`CLIO_CREATE_DATABASE=false`.

The same checkout can still run against Docker without editing `.env` by
overriding the connection variables for the FastAPI process:

```bash
CLIO_DATABASE_MODE=local \
CLIO_CLICKHOUSE_HOST=127.0.0.1 \
CLIO_CLICKHOUSE_PORT=8123 \
CLIO_CLICKHOUSE_USER=clio \
CLIO_CLICKHOUSE_PASSWORD=clio-local \
CLIO_CLICKHOUSE_DATABASE=filmgraph \
CLIO_CLICKHOUSE_SECURE=false \
PYTHONPATH=backend backend/.venv/bin/python -m uvicorn filmgraph.main:app --host 127.0.0.1 --port 8000
```

Cloud services conventionally expose the secure ClickHouse HTTP endpoint on
8443; the Python adapter passes `secure=true` for that target. See the
[ClickHouse Python integration](https://clickhouse.com/integrations/python)
for the supported `clickhouse-connect` connection shape.

### First paint and workspace cache

The route renders the CLIO shell and a compact map skeleton immediately; it
does not block the first HTML response on the remote workspace read. The
browser then hydrates the authoritative snapshot in the background and shows
`SYNCED`, `SYNCING`, or `CACHED` in the top metadata. A successful
ClickHouse/MCP snapshot is kept in a short-lived in-memory/session cache (30
seconds fresh, up to 5 minutes stale). Mutations invalidate that cache, and
explicit refreshes bypass it, so the cache cannot replace the authoritative
FastAPI/ClickHouse write path.

With `AGENT_MODE=live`, CLIO uses the configured OpenRouter model as a real
tool-using agent: it reads impact, lineage, timing, and revision tools before
returning a recommendation. The provider emits the same ADK-shaped event
stream as the simulator and never writes without an explicit human action.
Set `AGENT_MODE=simulated` to run offline; Vertex Gemini/ADK credentials can be
added later without changing the browser contract.

## Script Git

Open `GIT` in the workspace to load a screenplay directly from GitHub. Paste the
built-in offline demo URL `https://github.com/owner/repository/blob/main/script.fountain`
or a real file URL such as `https://github.com/mattdaly/Fountain.js/blob/master/samples/bigfish.fountain`
or use `owner/repo:path/to/script.fountain`; an optional ref can be a branch or
commit SHA. CLIO reads the file and commit history through the GitHub REST API,
parses Fountain/Markdown/plain text into revision → scene → timed beat nodes,
and shows a compact current-map diff. Loading is read-only; `APPLY TO MAP` is
the explicit human action that replaces the script graph and appends
`script.git.applied` to the workflow event trail. The overlay keeps an explicit
`BEFORE / AFTER` comparison; after an apply, `RESTORE BEFORE` can recover the
captured prior script graph from the append-only event (and refuses to erase a
later graph edit). Public files need no token;
set `CLIO_GITHUB_TOKEN` for private repositories. Imported timings stay exact
when `[MM:SS-MM:SS]` markers exist and are marked `~` when estimated from script
length.

## Node model and agent actions

On a first visit, CLIO opens a short MAP → TRACE → CONTROL onboarding guide.
After entering the map, use `NEW` or the inspector's `NODE CONTROL` section
to create scenes and timed child beats, edit script/narration/timing, or
delete a node after confirmation. Scene deletion cascades its child beats;
all writes are persisted by the Python repository and recorded as workflow
events.

Each scene node represents screenplay action plus narration and four timing values:

```text
SC 17 · INT. BRIDGE / LOOKOUT — NIGHT
script text
↳ narration line
01:50:00 → 01:58:30 · 08:30
```

Scenes are parents. Every Titanic scene owns five child beat nodes. `SHOW MAP`
expands that one scene into its beat sequence; each beat has
its own action text, narration, start, end, and duration. The full graph stays
available to lineage and agent queries even when child nodes are collapsed.

`EXPLAIN` traces neighbors, `EDIT` names affected downstream scenes, `REMOVE`
lists scenes that may become unnecessary and recomputes total time, and `ADD`
suggests possible connections. The default provider is visibly marked
`LOCAL SIMULATION`; it proposes but never writes.

No master, language, delivery, shot, take, or asset rows are seeded in this
first slice. Their compatibility API seams are intentionally empty. The
storyboard is deliberately script-only: heading, action, narration, start,
end, duration, and lineage edges.

## Verification

```bash
pnpm typecheck
pnpm test
pnpm build
cd backend && .venv/bin/python -m pytest -q
```

For the workflow screenshots and the full local walkthrough, see
[docs/workflow.md](docs/workflow.md).
