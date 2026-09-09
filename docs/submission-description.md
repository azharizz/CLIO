<p align="center">
  <img src="https://raw.githubusercontent.com/azharizz/CLIO/main/docs/assets/clio-readme-banner.svg" alt="CLIO — Continuity and Lineage Intelligence Operator" width="100%">
</p>

# CLIO — Continuity & Lineage Intelligence Operator

## See the consequence before you make the cut.

CLIO is a script-first editorial workspace for tracing what a screenplay
revision changes. It connects a revision source to scene parents, timed child
beats, dependency paths, duration, agent evidence, and an explicit human
decision.

It does not ask an agent to rewrite a film autonomously. It gives an editor a
better way to see the downstream cost of a change before committing it.

## The short version

An editor changes one story beat. That change may quietly affect a later
narration line, a payoff, a sequence of child beats, or the runtime of the
film. Today, finding those dependencies is mostly a manual hunt across script
versions, notes, and memory.

CLIO makes the relationship visible. It maps a screenplay as a graph, lets the
editor drill from scene to timed beat, traces the chain around a revision, and
asks a bounded agent to return evidence for four questions:

- What comes before and after this scene?
- Which scenes are affected if the text changes?
- What becomes unnecessary if it is removed, and how does runtime change?
- Where could a new scene connect?

The answer is not an opaque chat paragraph. CLIO returns a visible graph,
timing calculation, revision reference, and critic note. The editor still
decides whether anything changes.

## The problem

Script tools are good at displaying text and comments. They are much weaker at
showing causal structure: which scene motivates a later scene, which beat pays
off a change, or which revision turned a stable sequence into a continuity
risk.

Generative AI can make this worse if it is allowed to sound certain without
showing what it inspected. A useful editorial agent should be able to navigate
the same structured story state as the human, identify evidence, calculate a
bounded impact, and stop at the decision boundary.

CLIO is built around that boundary:

> The agent can propose a consequence. The editor remains the screenplay authority.

## What we built

| CLIO capability | What it does | Why it matters |
| --- | --- | --- |
| Script map | Shows the revision source alongside scene nodes and their relationships. | A change has a visible place in the film instead of living in a comment thread. |
| Timed beat expansion | Opens a scene into five timed child beats with action text and narration. | A local revision can be inspected at the level where continuity breaks. |
| Dependency trace | Follows upstream/downstream relationships while dimming unrelated work. | The editor can reason about a path without losing the full-map context. |
| Bounded agent run | Supports explain, edit, remove, and add proposals. | The agent helps investigate; it does not become an invisible co-writer. |
| Evidence stream | Separates narrative, graph, analytics, revision, and critic phases. | Each recommendation carries inspectable inputs and provenance. |
| Runtime impact | Calculates the selected removal against the current timed map. | Consequences are concrete, not hand-wavy. |
| Script Git | Loads a GitHub screenplay, parses scenes/beats, shows revision history and map diff, then waits for an explicit apply. | Source-control context becomes a reviewable editorial transition. |
| Recovery guard | Restores the captured pre-import graph only when no later change would be overwritten. | A reversible path does not silently erase newer work. |

The current demonstration is a fictional Titanic storyboard: 25 scenes, 125
timed beats, and one V5 collision revision focused on SC 17. The scope is
deliberate. It proves a full change-understanding loop without pretending to
be a production asset-management or delivery platform.

## Product walkthrough

<p align="center">
  <img src="https://raw.githubusercontent.com/azharizz/CLIO/main/docs/assets/clio-workflow.gif" alt="CLIO workflow GIF: onboarding, screenplay map, impact inspection, agent proposal, and Script Git comparison" width="100%">
</p>

| 1. Script map | 2. Bounded agent evidence |
| --- | --- |
| ![CLIO screenplay map](https://raw.githubusercontent.com/azharizz/CLIO/main/docs/screenshots/01-workspace-loaded.png) | ![CLIO agent evidence overlay](https://raw.githubusercontent.com/azharizz/CLIO/main/docs/screenshots/04-agent-recommendation.png) |
| The V5 source and every scene share one visual dependency surface. | The agent exposes graph, timing, revision, and critic phases without auto-writing the map. |

| 3. Scene and beat impact | 4. Git comparison before apply |
| --- | --- |
| ![CLIO scene inspector and expanded beats](https://raw.githubusercontent.com/azharizz/CLIO/main/docs/screenshots/03-impact-inspector.png) | ![CLIO Script Git comparison](https://raw.githubusercontent.com/azharizz/CLIO/main/docs/screenshots/10-script-git-loaded.png) |
| SC 17 can expand into timed child beats while retaining its lineage. | A loaded source remains read-only until an editor chooses to apply it. |

## What people and agents can now do together

The editor selects the change and supplies the judgment. CLIO gathers the
cross-cutting context that is tedious to reconstruct by hand.

| Agent can | Editor must decide |
| --- | --- |
| Read the selected node, linked scenes, timed beats, and active revision. | Whether the path represents a real continuity issue. |
| Summarize upstream/downstream relationships. | Whether to retain, edit, or remove the material. |
| Estimate affected scenes and runtime after a proposed removal. | Whether a runtime tradeoff is acceptable. |
| Suggest a new connection in the story graph. | Whether the proposed connection belongs in the screenplay. |
| Load and parse a GitHub source for comparison. | Whether to press <strong>APPLY TO MAP</strong> or <strong>RESTORE BEFORE</strong>. |

This is a stronger interaction than an assistant guessing from isolated text.
The agent works against visible, structured state. The person can verify the
output, correct the premise, and only then make a durable change.

## How it works

~~~text
editor selects a revision or scene
              ↓
CLIO reads the script graph, lineage, timing, and revision context
              ↓
agent emits a bounded evidence pass
              ↓
workspace shows the proposal and provenance
              ↓
editor explicitly changes the graph or keeps the current script
~~~

| Layer | Implementation | Boundary |
| --- | --- | --- |
| Workspace | TanStack Start, React, React Flow-style graph surface, keyboard navigation, and overlay panels. | The browser shows source and runtime labels rather than concealing fallbacks. |
| Graph | ClickHouse-backed repository with a local fallback snapshot. An optional MCP adapter is tried before the direct store for reads. | MCP is read-only; mutations do not travel through it. |
| API | FastAPI routes for graph operations, impact, agent streams, and Script Git transitions. | Create, update, delete, apply, and restore stay explicit operations. |
| Agent | A simulated local stream by default; a configured live provider can use bounded graph, lineage, timing, revision, and critic tools. | The agent has no automatic approval or screenplay-write capability. |
| Deployment | Firebase Hosting serves the public client and can route configured API calls to the service path. | A live page is not mislabeled as live graph/provider evidence when it is using fallback state. |

## Why this matters

CLIO treats a screenplay revision as an operational decision, not merely a
line of text.

- It makes the dependency graph visible before a revision becomes a late-stage continuity surprise.
- It keeps a granular scene/beat view connected to a film-wide map.
- It makes agent reasoning inspectable through graph, timing, revision, and critic evidence.
- It keeps the irreversible moments explicit: edit, delete, apply a Git map, and restore a prior map.
- It names the active source and runtime mode so reviewers can see the difference between a configured service and a local demonstration.

The pattern applies beyond film: product requirements, release plans, legal
documents, and other versioned narratives all carry dependencies that deserve
the same visible review loop.

## Try it

- **Live app:** [clio-agentic.web.app](https://clio-agentic.web.app/)
- **Workspace:** [clio-agentic.web.app/workspace](https://clio-agentic.web.app/workspace)
- **Source:** [github.com/azharizz/CLIO](https://github.com/azharizz/CLIO)
- **Detailed workflow:** [docs/workflow.md](https://github.com/azharizz/CLIO/blob/main/docs/workflow.md)

Suggested live path:

1. Enter the workspace and inspect the V5 collision revision.
2. Select SC 17 and use <strong>SHOW MAP</strong> to reveal its beats.
3. Toggle <strong>TRACE</strong> to isolate the dependency path.
4. Open <strong>AGENT</strong>, choose <strong>EXPLAIN</strong>, and read the evidence phases.
5. Open <strong>GIT</strong>, load the included offline fixture, and compare the current map with the loaded source.
6. Read the labels in the header before interpreting the data source or agent result.

## Honest limits

- The built-in story is synthetic demo data, not a real screenplay or a production integration.
- The public URL hosts the interface. The page visibly says whether it is using ClickHouse MCP, direct ClickHouse, local fallback, a live provider, or local simulation.
- The simulated agent is deterministic and proposal-only. A live provider requires explicit configuration and remains proposal-only.
- CLIO does not generate new screenplay content, handle production footage, or make delivery decisions in this script-first slice.
- Git timing is exact only when source markers exist; estimated timing is labelled as such.
- Public GitHub files can load without a token. Private reads need <code>CLIO_GITHUB_TOKEN</code>.
- A restore refuses to overwrite a later graph or workflow change.

## Built with

TanStack Start · React · TypeScript · Vite · React Flow · FastAPI · Python ·
ClickHouse · optional read-only MCP · Firebase Hosting · Cloud Run deployment
material · OpenRouter-compatible agent provider seam · Playwright · Vitest

## Source and license

The source is public at [github.com/azharizz/CLIO](https://github.com/azharizz/CLIO)
and is licensed under [Apache-2.0](https://github.com/azharizz/CLIO/blob/main/LICENSE).
The walkthrough uses synthetic data and repository-owned screenshots.
