<p align="center">
  <img src="docs/assets/clio-readme-banner.svg" alt="CLIO — Continuity and Lineage Intelligence Operator" width="100%">
</p>

<div align="center">
  <p><strong>CLIO — Continuity &amp; Lineage Intelligence Operator</strong></p>
  <p>One script revision. A visible chain of consequences. A human decision at the end.</p>
  <p><em>CLIO turns screenplay changes into a map of scenes, timed beats, lineage, and downstream impact before an editor has to discover the break by hand.</em></p>
  <p>
    <a href="https://clio-agentic.web.app/"><img src="https://img.shields.io/badge/OPEN_LIVE_CLIO-00C9E8?style=for-the-badge&logo=firebase&logoColor=white" alt="Open live CLIO"></a>
    <a href="docs/submission-description.md"><img src="https://img.shields.io/badge/SUBMISSION_DESCRIPTION-FF2E93?style=for-the-badge&logo=readme&logoColor=white" alt="Read the submission description"></a>
    <a href="https://github.com/azharizz/CLIO"><img src="https://img.shields.io/badge/SOURCE_ON_GITHUB-171717?style=for-the-badge&logo=github&logoColor=white" alt="Open source on GitHub"></a>
  </p>
  <p>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-2F5D50.svg" alt="Apache 2.0 license"></a>
    <a href="https://tanstack.com/start"><img src="https://img.shields.io/badge/frontend-TanStack_Start_%2B_React-00E5FF.svg" alt="TanStack Start and React"></a>
    <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/API-FastAPI-009688.svg" alt="FastAPI"></a>
    <a href="https://clickhouse.com/"><img src="https://img.shields.io/badge/graph-ClickHouse-FFCC01.svg" alt="ClickHouse"></a>
  </p>
  <p>
    <a href="https://clio-agentic.web.app/">Live app</a> ·
    <a href="docs/submission-description.md">Submission description</a> ·
    <a href="docs/assets/clio-readme-banner.svg">Banner source</a> ·
    <a href="docs/assets/clio-workflow.gif">Workflow GIF</a> ·
    <a href="docs/workflow.md">Complete local workflow</a>
  </p>
  <p><sub>Map the script → inspect the dependency → ask for evidence → approve the change yourself.</sub></p>
</div>

<details>
<summary><kbd>Contents</kbd></summary>

- [At a glance](#-at-a-glance)
- [The problem](#the-problem)
- [What CLIO does](#what-clio-does)
- [Product walkthrough](#product-walkthrough)
- [The editorial loop](#the-editorial-loop)
- [Human and agent boundaries](#human-and-agent-boundaries)
- [Architecture and provenance](#architecture-and-provenance)
- [Try the live app](#try-the-live-app)
- [Quick start](#-quick-start)
- [Verify](#verify)
- [Truth boundaries](#truth-boundaries)
- [Repository map](#repository-map)
- [License](#license)

</details>

> [!IMPORTANT]
> The public URL is a live, publicly hosted interface. Its default demonstration state is visibly labelled <strong>LOCAL DEMO</strong>, <strong>LOCAL FALLBACK</strong>, and <strong>LOCAL SIMULATION</strong> whenever the configured API, graph store, or provider is unavailable. The fictional Titanic data and simulated agent prove the product interaction; they are not a claim of production screenplay data or autonomous edits.

## 🧭 At a glance

<table>
  <tr>
    <td width="25%" align="center"><strong>01 / MAP</strong><br><br>Keep the revision source, 25 scenes, and 125 timed beats in one screenplay-first dependency surface.</td>
    <td width="25%" align="center"><strong>02 / TRACE</strong><br><br>Follow a changed line through relationships, child beats, timing, and affected downstream scenes.</td>
    <td width="25%" align="center"><strong>03 / ASK</strong><br><br>Request bounded <em>explain</em>, <em>edit</em>, <em>remove</em>, or <em>add</em> evidence from the selected node.</td>
    <td width="25%" align="center"><strong>04 / CONTROL</strong><br><br>Review a proposal, then explicitly edit the graph or apply a loaded Git revision yourself.</td>
  </tr>
</table>

<p align="center"><sub>CLIO is a change-understanding workspace, not a screenplay generator or an autonomous editorial system.</sub></p>

## The problem

A screenplay revision rarely changes one line in isolation. A changed action
can invalidate a later narration line, create a timing problem, weaken a
payoff, or make a whole beat sequence unnecessary. Conventional script views
make that downstream reasoning a manual scavenger hunt across tabs, notes, and
versions.

An agent can accelerate the investigation, but a chat answer alone is not an
editorial record. The editor needs the original revision, the affected graph,
the timing calculation, the proposed consequence, and a clear point where
human judgment takes over.

CLIO asks the practical question:

> Which parts of this film depend on the change, and what evidence should an editor review before deciding?

## What CLIO does

| Editorial friction | CLIO response | Why it matters |
| --- | --- | --- |
| A revision hides its consequences. | A source revision links to scene parents and timed child beats in one map. | The changed line stays connected to the work it may affect. |
| A scene card is too coarse for a local rewrite. | Expand one scene into five timed beats without losing the all-film overview. | An editor can inspect a narrow change without abandoning the context. |
| “What breaks next?” becomes memory work. | Trace paths and show upstream/downstream links, duration, narration, and action text. | Evidence is visible before a recommendation. |
| Agent advice is hard to audit. | Stream narrative, graph, timing, revision, and critic phases with provenance labels. | The proposal exposes what it read and how it reasoned. |
| A rewrite may have a cost in minutes. | The remove action recomputes the remaining film duration for the selected dependency path. | Editorial tradeoffs become concrete. |
| A Git import can erase working context. | Load and compare a screenplay revision read-only; apply only through an explicit action and restore only when safe. | Source history is useful without silently replacing the current map. |
| Storage/source ambiguity erodes trust. | The header names the current source: ClickHouse MCP, direct ClickHouse, or local fallback. | Reviewers can distinguish data provenance from a UI promise. |

The bundled demonstration is intentionally bounded: a fictional Titanic map
from 00:00 to 03:15:00, with 25 scene nodes, 125 timed beat nodes, and a V5
collision revision focused on SC 17.

## Product walkthrough

The GIF below is built from the repository's deterministic workflow captures:
onboarding, full map, a scene-level impact inspection, an agent evidence pass,
and the read-only Git comparison. It documents the actual product states
rather than an invented mockup.

<p align="center">
  <img src="docs/assets/clio-workflow.gif" alt="CLIO workflow: onboarding, screenplay map, impact inspection, agent proposal, and Script Git comparison" width="100%">
</p>

| Stop | What is visible | What it proves |
| --- | --- | --- |
| <strong>Map</strong> | The V5 source revision sits beside the 25-scene script map. | The change is a first-class object, not a note beside the screenplay. |
| <strong>Inspect</strong> | SC 17 expands into timed child beats with its own action and narration. | CLIO can drill down without flattening the film. |
| <strong>Ask agent</strong> | The agent shows graph, timing, revision, and critic phases. | A recommendation remains an inspectable proposal. |
| <strong>Script Git</strong> | A GitHub source is loaded, parsed, compared, and held read-only until apply. | Import is a reviewed transition, not an invisible replacement. |

<p align="center">
  <img src="docs/screenshots/10-script-git-loaded.png" alt="CLIO Script Git overlay showing loaded screenplay revision, history, map diff, before and after comparison, and apply boundary" width="100%">
</p>

## The editorial loop

One focused change is enough to demonstrate the loop:

1. Open the V5 source revision: <strong>CALM COURSE → ICEBERG COLLISION</strong>.
2. Select SC 17, the bridge/lookout collision scene, and expand its five child beats.
3. Trace the path to see which later scenes, beats, and timings are connected.
4. Ask CLIO to explain, model an edit, estimate a removal, or suggest where a new scene could connect.
5. Read the returned graph, timing, revision, and critic evidence.
6. Make the editorial decision explicitly: change a node, keep the script, or load a reviewed Git revision.

The agent is useful because it assembles context across the same graph the
editor sees. It never becomes the authority that changes the screenplay.

## Human and agent boundaries

| CLIO agent can | The editor still decides |
| --- | --- |
| Read the selected scene/beat, nearby lineage, timing, and revision context. | Whether the evidence supports a script change. |
| Explain upstream and downstream relationships. | Which relationship matters editorially. |
| Propose affected scenes after an edit or a duration after removal. | Whether to rewrite, remove, or retain any material. |
| Suggest a possible insertion path. | Whether a new scene belongs in the screenplay. |
| Load a public GitHub screenplay for a read-only comparison. | Whether to press <strong>APPLY TO MAP</strong>. |
| Show a previous state that is eligible for recovery. | Whether to restore it; a later graph edit blocks a destructive restore. |

Node creation, edits, and deletion are explicit product actions. Scene deletion
asks for confirmation and removes its child beats only after the editor accepts
that operation. Agent runs may be simulated or live depending on configuration,
but neither mode receives an automatic write path.

## Architecture and provenance

CLIO keeps the graph source and the proposal source visible instead of hiding
fallbacks behind a generic success state.

~~~text
Browser
  → Firebase Hosting / TanStack Start client
      → /api path when the service is configured
          → FastAPI / Cloud Run
              → read: ClickHouse MCP first, then direct ClickHouse
              → write: explicit FastAPI repository operation
              → agent: bounded graph, lineage, timing, revision, and critic tools
      → local fallback snapshot when no authoritative service answers
~~~

| Layer | Responsibility | Boundary |
| --- | --- | --- |
| Browser workspace | Shows the map, source labels, overlays, trace state, and local onboarding. | It never receives provider or database credentials. |
| Firebase Hosting | Serves the public client and routes configured API traffic. | A reachable UI is not presented as proof that every backend dependency is live. |
| FastAPI repository | Applies explicit graph, workflow, and Script Git mutations. | It is the mutation boundary; the MCP adapter is read-only. |
| ClickHouse / MCP | Supplies graph, revision, lineage, and impact reads when configured. | The workspace labels direct, MCP, and fallback sources differently. |
| Agent provider | Produces a bounded evidence stream for the selected operation. | It proposes; it cannot approve, apply, or delete screenplay state. |

The configured deployment topology is documented in
[docs/gcp-deployment.md](docs/gcp-deployment.md). The live public page is
designed to remain honest when that service path is unavailable.

## Try the live app

- [Open CLIO](https://clio-agentic.web.app/)
- [Open the workspace directly](https://clio-agentic.web.app/workspace)
- [Read the submission description](docs/submission-description.md)
- [Read the full local workflow](docs/workflow.md)
- [Open the public source repository](https://github.com/azharizz/CLIO)

Suggested two-minute review:

1. Open the landing page and choose <strong>ENTER</strong>.
2. Inspect the V5 source and select SC 17.
3. Press <strong>SHOW MAP</strong> to reveal the timed beats.
4. Open <strong>AGENT</strong>, choose <strong>EXPLAIN</strong>, then review the evidence stream.
5. Open <strong>GIT</strong>, load the built-in offline GitHub fixture, and inspect the current-to-loaded comparison.
6. Notice the <strong>LOCAL DEMO</strong>, graph-source, and agent-mode labels before interpreting any result.

## ⚡ Quick start

Requirements: Node 22, pnpm, Python 3.13, and Docker Desktop/Engine only when
you want to exercise the local ClickHouse store.

From the repository root:

~~~bash
pnpm install

# Optional terminal 1: local ClickHouse
docker compose -f infra/docker-compose.yml up -d

# Terminal 2: FastAPI
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
CLIO_DATABASE_MODE=local CLIO_CLICKHOUSE_HOST=127.0.0.1 \
CLIO_CLICKHOUSE_PORT=8123 CLIO_CLICKHOUSE_USER=clio \
CLIO_CLICKHOUSE_PASSWORD=clio-local CLIO_CLICKHOUSE_DATABASE=filmgraph \
CLIO_CLICKHOUSE_SECURE=false uvicorn filmgraph.main:app \
  --host 127.0.0.1 --port 8000 --reload

# Terminal 3: TanStack Start
cd ..
pnpm dev
~~~

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). If Docker or FastAPI is
not running, CLIO remains usable with its explicitly labelled local fallback.

For provider, Cloud, and GitHub configuration, copy [.env.example](.env.example)
to a local environment file and read [docs/workflow.md](docs/workflow.md).
Never commit provider keys, GitHub tokens, database credentials, or real
screenplay data.

## Verify

~~~bash
pnpm typecheck
pnpm test
pnpm e2e
pnpm build
cd backend && .venv/bin/python -m pytest -q
git diff --check
~~~

Regenerate the named workflow captures after a material UI change:

~~~bash
CLIO_CAPTURE_DIR="$PWD/docs/screenshots" pnpm capture
~~~

## Truth boundaries

- The Titanic storyboard is fictional local-demo data, not a complete screenplay or a production integration.
- The public frontend is live. The page itself labels whether a graph came from ClickHouse MCP, direct ClickHouse, or the local fallback, and whether the agent is simulated or live.
- A simulated agent uses deterministic local evidence. A live provider needs explicit configuration and remains a proposal-only path.
- CLIO does not generate scenes, shoot footage, assemble a master, localize a film, or create delivery assets in this script-first slice.
- Script Git reads public GitHub files without a token; private reads need <code>CLIO_GITHUB_TOKEN</code>. Import timing is exact only when the source carries time markers; estimates are marked.
- <strong>APPLY TO MAP</strong> is explicit. <strong>RESTORE BEFORE</strong> is intentionally unavailable after a later graph/workflow change that it could overwrite.
- MCP is a read-only adapter. Graph mutations go through the configured FastAPI repository.

## Repository map

| Path | Purpose |
| --- | --- |
| [src/routes/index.tsx](src/routes/index.tsx) | The screenplay workspace, graph controls, trace state, agent overlay, and Script Git entry point. |
| [src/components/](src/components/) | Focused graph, inspector, editor, onboarding, agent, decision, and Git UI components. |
| [src/lib/workspace.ts](src/lib/workspace.ts) | Browser-side workspace state, fallback snapshot, graph mapping, and event handling. |
| [backend/filmgraph/](backend/filmgraph/) | FastAPI API, graph repositories, Script Git integration, agent provider seam, and ClickHouse adapters. |
| [agent_runtime/](agent_runtime/) | Deployable agent-runtime integration path and deployment helper. |
| [infra/](infra/) | Local ClickHouse compose file plus GCP and Firebase deployment material. |
| [docs/screenshots/](docs/screenshots/) | Deterministic workflow captures used in this README and the animated walkthrough. |
| [docs/workflow.md](docs/workflow.md) | Detailed local runtime, graph model, configuration, and screenshot reference. |
| [docs/submission-description.md](docs/submission-description.md) | Paste-ready project description with visual proof and boundaries. |

## License

CLIO is licensed under [Apache-2.0](LICENSE). The repository contains a
synthetic storyboard and local-demo artifacts. Verify third-party screenplay,
provider, and brand permissions before using it with real production material.
