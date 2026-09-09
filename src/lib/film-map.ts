import type { WorkspaceEdge, WorkspaceNode, WorkspaceSnapshot } from './contracts'

export interface FilmMapGraph {
  nodes: WorkspaceNode[]
  edges: WorkspaceEdge[]
}

const FRAME_WIDTH = 237
const SOURCE_X = 24
const SCENE_X = 320
const SCENE_Y = 72
const SCENE_COLUMN_GAP = 278
const SCENE_ROW_GAP = 172

function numericSceneOrder(node: WorkspaceNode): number {
  const parsed = Number(node.data.sceneNumber)
  return Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER
}

/**
 * The data store keeps authoring coordinates, which may include a long raw
 * timeline. Those coordinates are useful for editing, but make a very poor
 * overview: a single revision can sit thousands of pixels away from its
 * scenes. The map is therefore a deterministic projection, not a persisted
 * canvas. It packs chronological scenes into a serpentine storyboard so every
 * consecutive edge travels horizontally, then turns down only at a row edge.
 */
function layoutOverview(nodes: WorkspaceNode[], edges: WorkspaceEdge[], selectedNodeId: string): WorkspaceNode[] {
  const scenes = nodes
    .filter((node) => node.data.kind === 'scene')
    .sort((left, right) => {
      const byTime = (left.data.startSeconds ?? Number.MAX_SAFE_INTEGER) - (right.data.startSeconds ?? Number.MAX_SAFE_INTEGER)
      return byTime || numericSceneOrder(left) - numericSceneOrder(right) || left.id.localeCompare(right.id)
    })

  if (scenes.length === 0) return nodes.map((node) => ({ ...node, data: { ...node.data } }))

  // Three columns keep a short script readable; five keeps a feature-sized
  // script inside the viewport without the source being marooned above it.
  const columns = scenes.length <= 12 ? 3 : 5
  const positions = new Map<string, { x: number; y: number }>()
  scenes.forEach((scene, index) => {
    const row = Math.floor(index / columns)
    const columnInSequence = index % columns
    const column = row % 2 === 0 ? columnInSequence : columns - 1 - columnInSequence
    positions.set(scene.id, {
      x: SCENE_X + column * SCENE_COLUMN_GAP,
      y: SCENE_Y + row * SCENE_ROW_GAP,
    })
  })

  const revision = nodes.find((node) => node.data.kind === 'revision')
  const revisedSceneId = revision
    ? edges.find((edge) => edge.source === revision.id && positions.has(edge.target))?.target
    : undefined
  const anchorScene = scenes.find((scene) => scene.id === revisedSceneId)
    ?? scenes.find((scene) => scene.id === selectedNodeId)
    ?? scenes.find((scene) => scene.data.scope === 'focus')
    ?? scenes[Math.floor(scenes.length / 2)]!
  const anchor = positions.get(anchorScene.id)!
  if (revision) positions.set(revision.id, { x: SOURCE_X, y: anchor.y })

  // Expanded beats form a deliberate lower strip. They never occupy the same
  // coordinate band as their parent scene cards, so opening one cannot wreck
  // the overview layout.
  const beats = nodes
    .filter((node) => node.data.kind === 'beat')
    .sort((left, right) => {
      const byParent = (left.data.parentSceneId ?? '').localeCompare(right.data.parentSceneId ?? '')
      return byParent || (left.data.beatNumber ?? 0) - (right.data.beatNumber ?? 0) || left.id.localeCompare(right.id)
    })
  const sceneRows = Math.ceil(scenes.length / columns)
  const beatY = SCENE_Y + sceneRows * SCENE_ROW_GAP + 42
  beats.forEach((beat, index) => {
    positions.set(beat.id, {
      x: SCENE_X + (index % columns) * (FRAME_WIDTH + 38),
      y: beatY + Math.floor(index / columns) * 138,
    })
  })

  return nodes.map((node) => ({
    ...node,
    position: positions.get(node.id) ?? node.position,
    data: { ...node.data },
  }))
}

/**
 * Keep the overview at scene level and reveal each scene's child beats on
 * demand. The snapshot still contains the complete graph, so lineage and
 * agent queries can traverse every child even while the canvas stays legible.
 */
export function buildFilmMap(
  snapshot: WorkspaceSnapshot,
  expandedSceneIds: ReadonlySet<string> | string | null = null,
): FilmMapGraph {
  // Accept the old single-id shape for callers/tests while the UI uses a set
  // so every parent scene owns its own independent visibility toggle.
  const expanded = typeof expandedSceneIds === 'string'
    ? new Set([expandedSceneIds])
    : expandedSceneIds ?? new Set<string>()
  const allNodes = snapshot.graph.nodes
  const visibleNodes = allNodes.filter((node) => {
    if (node.data.kind !== 'beat') return true
    return Boolean(node.data.parentSceneId && expanded.has(node.data.parentSceneId))
  })
  const visibleIds = new Set(visibleNodes.map((node) => node.id))
  const edges = snapshot.graph.edges
    .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .map((edge) => ({ ...edge, data: { ...edge.data } }))
  const nodes = layoutOverview(visibleNodes, edges, snapshot.selectedNodeId)
  return { nodes, edges }
}

/** Script map and trace share one coordinate system; selection controls focus. */
export function traceAnchorFor(nodeId: string): string {
  return nodeId
}

export function overviewAnchorFor(nodeId: string): string {
  return nodeId
}
