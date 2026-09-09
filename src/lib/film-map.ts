import type { WorkspaceEdge, WorkspaceNode, WorkspaceSnapshot } from './contracts'

export interface FilmMapGraph {
  nodes: WorkspaceNode[]
  edges: WorkspaceEdge[]
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
  const nodes = visibleNodes.map((node) => ({ ...node, data: { ...node.data } }))
  const edges = snapshot.graph.edges
    .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
    .map((edge) => ({ ...edge, data: { ...edge.data } }))
  return { nodes, edges }
}

/** Script map and trace share one coordinate system; selection controls focus. */
export function traceAnchorFor(nodeId: string): string {
  return nodeId
}

export function overviewAnchorFor(nodeId: string): string {
  return nodeId
}
