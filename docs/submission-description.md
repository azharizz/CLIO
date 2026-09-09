<p align="center">
  <img src="https://raw.githubusercontent.com/azharizz/CLIO/main/docs/assets/clio-readme-banner.svg" alt="CLIO — Continuity and Lineage Intelligence Operator" width="100%">
</p>

# CLIO — Continuity & Lineage Intelligence Operator

## See the consequence before you make the cut.

A screenplay change can ripple far beyond the line being revised. It can affect
later scenes, timed beats, narration, payoffs, and runtime—often without being
obvious until much later in the edit.

CLIO makes that chain visible. It connects a revision to the screenplay map,
lets an editor inspect the affected beats, and returns evidence for a decision.
The editor remains in control of every change.

## A change should be reviewable, not surprising

Script tools are excellent at showing pages and comments. They are less useful
when an editor needs to answer a harder question: what does this revision
change downstream?

CLIO turns that question into a visual review loop. Instead of hunting through
versions and relying on memory, an editor can trace the path, inspect the
timing, ask for an explanation, and decide with the context in view.

## What CLIO delivers

| Capability | Editorial value |
| --- | --- |
| <strong>Script map</strong> | Keeps the active revision, scenes, and their relationships on one screen. |
| <strong>Beat-level detail</strong> | Opens a scene into timed beats without losing the wider story context. |
| <strong>Impact trace</strong> | Follows the scenes, action, narration, and timing connected to a change. |
| <strong>Evidence-backed review</strong> | Returns the context behind a proposal alongside the recommendation. |
| <strong>Runtime awareness</strong> | Makes the duration effect of a proposed removal concrete. |
| <strong>Source comparison</strong> | Loads a screenplay source for comparison before an editor chooses to update the map. |

The demonstration follows a fictional Titanic storyboard: 25 scenes, 125 timed
beats, and one V5 collision revision centered on SC 17.

## Watch the workflow

<p align="center">
  <img src="https://raw.githubusercontent.com/azharizz/CLIO/main/docs/assets/clio-workflow.gif" alt="CLIO workflow: onboarding, screenplay map, impact inspection, agent proposal, and Script Git comparison" width="100%">
</p>

| Script map | Evidence review |
| --- | --- |
| ![CLIO screenplay map](https://raw.githubusercontent.com/azharizz/CLIO/main/docs/screenshots/01-workspace-loaded.png) | ![CLIO agent evidence overlay](https://raw.githubusercontent.com/azharizz/CLIO/main/docs/screenshots/04-agent-recommendation.png) |
| The V5 source and every scene share one visual dependency surface. | The proposal exposes the context behind its recommendation for inspection. |

| Scene detail | Source comparison |
| --- | --- |
| ![CLIO scene inspector and expanded beats](https://raw.githubusercontent.com/azharizz/CLIO/main/docs/screenshots/03-impact-inspector.png) | ![CLIO Script Git comparison](https://raw.githubusercontent.com/azharizz/CLIO/main/docs/screenshots/10-script-git-loaded.png) |
| SC 17 expands into timed beats while keeping its story context. | A loaded screenplay source stays in review until an editor chooses to apply it. |

## From change to decision

1. Select a revision or scene.
2. Expand the beats and trace the connected path.
3. Ask CLIO to explain, model, remove, or add.
4. Review the evidence and make the editorial call.

## CLIO prepares. The editor decides.

| CLIO prepares | The editor decides |
| --- | --- |
| Linked scenes, beats, timing, and revision context. | Whether the relationship is editorially meaningful. |
| An explanation or a proposed consequence. | Whether to retain, edit, remove, or add material. |
| A comparison with a loaded screenplay source. | Whether to apply that source to the map. |

This keeps the agent useful without turning it into an invisible co-writer.
Its role is to surface the context; the person making the cut owns the
decision.

## Why it matters

Continuity problems are expensive because they are discovered late. CLIO makes
the dependency chain visible earlier, while the change is still easy to
understand and discuss.

The same review pattern can help with any versioned narrative that carries
dependencies: product requirements, release plans, legal documents, and more.

## Try CLIO

- **Live app:** [clio-agentic.web.app](https://clio-agentic.web.app/)
- **Workspace:** [clio-agentic.web.app/workspace](https://clio-agentic.web.app/workspace)
- **Source:** [github.com/azharizz/CLIO](https://github.com/azharizz/CLIO)
- **Technical workflow:** [docs/workflow.md](https://github.com/azharizz/CLIO/blob/main/docs/workflow.md)

Suggested review path:

1. Enter the workspace and inspect the V5 collision revision.
2. Select SC 17, then choose <strong>SHOW MAP</strong>.
3. Open <strong>AGENT</strong>, choose <strong>EXPLAIN</strong>, and read the evidence.
4. Open <strong>GIT</strong> to compare the current map with a loaded source.

## Built with

TanStack Start · React · TypeScript · Vite · React Flow · FastAPI · Python ·
ClickHouse · Firebase Hosting · Cloud Run · Playwright · Vitest

## Source and license

The source is public at [github.com/azharizz/CLIO](https://github.com/azharizz/CLIO)
and licensed under [Apache-2.0](https://github.com/azharizz/CLIO/blob/main/LICENSE).
