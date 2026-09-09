# CLIO local workflow

CLIO (Continuity & Lineage Intelligence Operator) is one script-change workspace. The graph is the primary surface;
the scene index, inspector, and agent run open as small overlays only when
needed. The current demo is synthetic and marked `LOCAL DEMO`.

## What a node means

The active slice uses one visible revision source, eight scene parents, and
sixteen timed child beats. Every scene carries the same compact payload:

| Field | Meaning |
| --- | --- |
| `SC 42` … `SC 49` | Stable screenplay scene identity. |
| Heading | Scene heading such as `INT. RESTAURANT — NIGHT`. |
| Script text | The short screenplay description used by the agent. |
| Narration | Spoken/voice-over line attached to the scene. |
| Start → end | Position in the current cut, in `MM:SS`. |
| Duration | `end - start`, computed in seconds and displayed as a clock. |
| Edge | A relationship such as `follows`, `sets_up`, `motivates`, or `pays_off`. |

`V5 · SC 47` is the source node. It records the before/after script line:
restaurant interior → moving car. There are no seeded master, language,
delivery, shot, take, or asset nodes in this first slice.

### Scene children

A scene is a parent, not a flat paragraph. Its `Bnn` count is visible on the
card. Selecting it reveals a compact child-beat list with action, narration,
and exact timing. `SHOW MAP` expands only that scene into child nodes joined by
`contains` and `follows` edges; `HIDE MAP` returns to the all-scene overview.
SC 47 intentionally demonstrates four beats (pull away, argue, handoff, and
decide) inside its 02:12 span.

## Prerequisites and exact startup

Use Node 22, pnpm, Python 3.13, and Docker Desktop/Engine when exercising
ClickHouse. From `/Users/azharie/Documents/azhar_project/filmm/filmgraph`:

```bash
pnpm install

# terminal 1 (optional memory fallback if Docker is unavailable)
docker compose -f infra/docker-compose.yml up -d

# terminal 2
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn filmgraph.main:app --host 127.0.0.1 --port 8000 --reload

# terminal 3
cd ..
pnpm dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). FastAPI is on
`127.0.0.1:8000`; ClickHouse HTTP/native are `127.0.0.1:8123` and
`127.0.0.1:9000`. If Docker is stopped, the UI remains usable and labels the
source `LOCAL FALLBACK`.

## ClickHouse and MCP

`001_schema.sql` keeps the shared graph, revision, workflow, and agent event
tables. `002_seed.sql` inserts only the timed script graph. Compatibility
tables for later production/release slices are intentionally empty.

With `GRAPH_QUERY_MODE=auto`:

1. A configured `CLIO_MCP_ENDPOINT` or `CLIO_MCP_COMMAND` is tried
   first with a read-only ClickHouse query (`clickhouse_mcp`).
2. An unavailable or timed-out MCP path falls back to `clickhouse-connect`
   (`direct_clickhouse`).
3. If neither is available, the memory seed is used (`computed`, shown as
   `LOCAL FALLBACK`).

`CLIO_*` is the current configuration prefix. Existing local environments using
the older `FILMGRAPH_*` names continue to work as compatibility aliases.

The fake MCP adapter test covers both the preferred path and fallback without a
live server. All writes append workflow or agent events through FastAPI.

## Complete user workflow

1. Open CLIO. On the first visit, the three-step guide explains MAP, TRACE,
   and HUMAN CONTROL. `SKIP`/`ENTER MAP` records the choice locally; `CREATE
   NODE` starts a scene draft immediately.
2. Open the workspace. The map shows the source revision and all eight scenes,
   with their action text, narration preview, beat count, and exact timing.
3. Select a scene or open `SCENES` to jump to one. The inspector shows heading,
   script text, narration, start, end, duration, child beats, and
   upstream/downstream links.
4. Press `SHOW MAP` for a complex scene (SC 47 is the demo). The parent stays
   connected while each child beat appears as a smaller timed node. Select a
   beat to inspect its own narration and jump back to its parent.
5. Use `NODE CONTROL` for human CRUD. `EDIT` changes heading, script,
   narration, start, or end; `ADD BEAT` creates a timed child inside a scene;
   `NEW`/`ADD SCENE` creates a scene; `DELETE` asks for confirmation and
   cascades a scene's child beats. Invalid timing or duplicate identity returns
   a visible conflict and leaves the graph unchanged.
6. Toggle `TRACE` to mute unrelated nodes while following a dependency path.
   `FIT` restores the whole map; arrow keys move selection and `Space` toggles
   trace.
7. Open `AGENT` and choose one question:
   - `EXPLAIN` — what comes before and after this scene?
   - `EDIT` — which scenes are affected if its text changes?
   - `REMOVE` — which dependent scenes become unnecessary and how much time is
     left?
   - `ADD` — where could a new scene connect?
8. Press `ANALYZE`. The stream emits narrative, graph, timing, revision, and
   critic phases. It is visibly marked `LOCAL SIMULATION · NO AUTO-WRITES`.
9. Treat the response as a proposal. The agent never edits a node or silently
   approves a decision; a future editorial gate can append a human event.
10. Open `GIT` to connect a GitHub screenplay. Paste a file URL or
    `owner/repo:path` plus an optional branch/commit ref. CLIO shows the file,
    commit history, parsed scene/beat/time counts, and a `CURRENT → LOADED` map
    diff. Select an older commit to inspect it, then press `APPLY TO MAP`; the
    graph refreshes to the imported revision and the append-only
    `script.git.applied` event makes the source visible after a reload.

## Browser/API boundary

TanStack Start keeps the browser same-origin and proxies the optional Python
service:

```text
GET  /api/workspace?filmId=demo-feature&revisionId=rev-05
GET  /api/nodes/:nodeId/impact
POST /api/graph/nodes
PATCH /api/graph/nodes/:nodeId
DELETE /api/graph/nodes/:nodeId
POST /api/agent-runs
GET  /api/agent-runs/:runId/events        (SSE)
GET  /api/health
POST /api/script-git/load
POST /api/script-git/apply
```

FastAPI exposes the corresponding `/api/v1` routes. Node writes use the
repository and append `graph.node.created`, `graph.node.updated`, or
`graph.node.deleted` events; refreshing reconstructs the graph from that
authoritative store. The legacy runtime and
delivery routes remain compatibility seams but return no seeded records in the
script-first workspace.

## Provenance and agent modes

Every read and streamed event carries one of the shared provenance values:
`direct_clickhouse`, `clickhouse_mcp`, `agent_simulation`, `gemini_adk`,
`computed`, or `estimate`.

Default local mode:

```text
AGENT_MODE=simulated
```

The future live seam accepts:

```text
AGENT_MODE=live
GEMINI_API_KEY=...
GOOGLE_CLOUD_PROJECT=...
GOOGLE_CLOUD_LOCATION=...
```

No live credentials or production claims are included.

## Screenshot index

Captures are 1440×900 unless noted. They document the script-first workflow:

0. [00 — first-run onboarding](screenshots/00-onboarding.png)
1. [01 — workspace loaded](screenshots/01-workspace-loaded.png)
2. [02 — revision trace](screenshots/02-revision-trace.png)
3. [03 — scene inspector + expanded beats](screenshots/03-impact-inspector.png)
4. [04 — agent recommendation](screenshots/04-agent-recommendation.png)
5. [05 — edit proposal](screenshots/05-runtime-decision.png)
6. [06 — remove proposal](screenshots/06-editorial-approved.png)
7. [07 — add connection proposal](screenshots/07-delivery-variants.png)
8. [08 — complete script provenance](screenshots/08-provenance-complete.png)
9. [09 — mobile workspace](screenshots/09-mobile-workspace.png)
10. [10 — GitHub screenplay loaded](screenshots/10-script-git-loaded.png)

Regenerate them with:

```bash
CLIO_CAPTURE_DIR="$PWD/docs/screenshots" pnpm capture
```

## Known local-demo limits

- Data is fictional; no media uploads, authentication, GCP deployment, or
  production migration are included.
- Docker is required to exercise the live ClickHouse adapter; the memory path
  is intentional and clearly labelled.
- The Gemini/ADK provider is a seam only; the simulator is the default.
- Scene text is concise demo copy, not a complete screenplay.
- GitHub history is read through the REST API (public files are unauthenticated;
  private files need `CLIO_GITHUB_TOKEN`). The parser supports common
  Fountain/Markdown headings and optional time markers; production screenplay
  dialects may need a future parser adapter.
