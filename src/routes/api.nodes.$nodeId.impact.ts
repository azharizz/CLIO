import { createFileRoute } from '@tanstack/react-router'
import { backendFetch } from '../lib/api'
import { readWorkspaceSnapshot, lineageFor, downstreamFor } from '../lib/workspace'

export const Route = createFileRoute('/api/nodes/$nodeId/impact')({
  server: {
    handlers: {
      GET: async ({ params }) => {
        try {
          const response = await backendFetch(`/nodes/${encodeURIComponent(params.nodeId)}/impact`)
          return Response.json(response, { headers: { 'X-CLIO-Source': 'fastapi' } })
        } catch {
          // Fall through to the local graph contract when Python is absent.
        }
        const snapshot = readWorkspaceSnapshot()
        const ids = new Set([...lineageFor(snapshot, params.nodeId), ...downstreamFor(snapshot, params.nodeId)])
        const nodes = snapshot.graph.nodes.filter((node) => ids.has(node.id))
        return Response.json({ nodeId: params.nodeId, nodes, provenance: snapshot.dataSource, source: 'local-simulation' })
      },
    },
  },
})
