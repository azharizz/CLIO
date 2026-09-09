# CLIO

CLIO (Continuity & Lineage Intelligence Operator) is a script-first change map for a fictional local film. One React
Flow graph keeps the full screenplay in view: a revision source plus timed
scene nodes. Each scene carries action text and narration; longer scenes can
be opened into timed child beats. Select a scene to see its script, narration,
start/end, duration, and graph neighbors, then ask the local agent what an
edit, removal, or insertion would affect.

The synthetic demo is always marked `LOCAL DEMO`: revision **V5** changes
**SC 47** from an interior restaurant to a moving car.

## Requirements

- Node 22 and pnpm
- Python 3.13
- Docker Desktop/Engine for ClickHouse mode (optional; memory fallback works)

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
uvicorn filmgraph.main:app --host 127.0.0.1 --port 8000 --reload

# terminal 3 — TanStack Start
cd ..
pnpm dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). The Python API uses
`127.0.0.1:8000`; ClickHouse uses HTTP `8123` and native `9000`.

## Configuration

```text
GRAPH_QUERY_MODE=auto
AGENT_MODE=simulated
CLIO_MCP_ENDPOINT=
CLIO_MCP_COMMAND=
CLIO_GITHUB_TOKEN=
CLIO_CLICKHOUSE_HOST=127.0.0.1
CLIO_CLICKHOUSE_PORT=8123
CLIO_USE_MEMORY_STORE=true
```

In `auto` mode, reads try a configured ClickHouse MCP tool first, then
`clickhouse-connect`, then the in-memory local seed. The UI labels the selected
source (`CLICKHOUSE MCP`, `DIRECT CLICKHOUSE`, or `LOCAL FALLBACK`). MCP is
read-only; mutations append events in the Python repository. `CLIO_*` is the
current configuration prefix; the older `FILMGRAPH_*` names remain accepted as
backward-compatible aliases.

## Script Git

Open `GIT` in the workspace to load a screenplay directly from GitHub. Paste a
file URL such as `https://github.com/mattdaly/Fountain.js/blob/master/samples/bigfish.fountain`
or use `owner/repo:path/to/script.fountain`; an optional ref can be a branch or
commit SHA. CLIO reads the file and commit history through the GitHub REST API,
parses Fountain/Markdown/plain text into revision → scene → timed beat nodes,
and shows a compact current-map diff. Loading is read-only; `APPLY TO MAP` is
the explicit human action that replaces the script graph and appends
`script.git.applied` to the workflow event trail. Public files need no token;
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
SC 47 · MOVING CAR — NIGHT
script text
↳ narration line
07:36 → 09:48 · 02:12
```

Scenes are parents. A scene with `B04`, for example, owns four child beat
nodes. `SHOW MAP` expands that one scene into its beat sequence; each beat has
its own action text, narration, start, end, and duration. The full graph stays
available to lineage and agent queries even when child nodes are collapsed.

`EXPLAIN` traces neighbors, `EDIT` names affected downstream scenes, `REMOVE`
lists scenes that may become unnecessary and recomputes total time, and `ADD`
suggests possible connections. The default provider is visibly marked
`LOCAL SIMULATION`; it proposes but never writes.

No master, language, delivery, shot, take, or asset rows are seeded in this
first slice. Their compatibility API seams are intentionally empty.

## Verification

```bash
pnpm typecheck
pnpm test
pnpm build
cd backend && .venv/bin/python -m pytest -q
```

For the workflow screenshots and the full local walkthrough, see
[docs/workflow.md](docs/workflow.md).
