import { createFileRoute } from '@tanstack/react-router'
import { BackendUnavailableError, backendConflictResponse, backendFetch } from '../lib/api'
import { deleteLocalGraphNode, readWorkspaceSnapshot, setWorkspaceSnapshot, updateLocalGraphNode, type GraphNodeDraft } from '../lib/workspace'

function stringValue(body: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) if (typeof body[key] === 'string') return body[key] as string
  return undefined
}

function patchBody(body: Record<string, unknown>) {
  return {
    ...(stringValue(body, 'heading', 'title') !== undefined ? { heading: stringValue(body, 'heading', 'title') } : {}),
    ...(stringValue(body, 'scriptText', 'script_text') !== undefined ? { script_text: stringValue(body, 'scriptText', 'script_text') } : {}),
    ...(stringValue(body, 'narrationText', 'narration_text') !== undefined ? { narration_text: stringValue(body, 'narrationText', 'narration_text') } : {}),
    ...(body.startSeconds !== undefined || body.start_seconds !== undefined ? { start_seconds: Number(body.startSeconds ?? body.start_seconds) } : {}),
    ...(body.endSeconds !== undefined || body.end_seconds !== undefined ? { end_seconds: Number(body.endSeconds ?? body.end_seconds) } : {}),
    actor: String(body.actor ?? 'editorial'),
    runtime_mode: String(body.runtime_mode ?? body.runtimeMode ?? 'simulation'),
  }
}

function localPatch(snapshot: ReturnType<typeof readWorkspaceSnapshot>, nodeId: string, body: Record<string, unknown>) {
  const current = snapshot.graph.nodes.find((node) => node.id === nodeId)
  if (!current || (current.data.kind !== 'scene' && current.data.kind !== 'beat')) throw new Error('Graph node not found.')
  const draft: GraphNodeDraft = {
    kind: current.data.kind,
    sceneNumber: current.data.sceneNumber,
    beatNumber: current.data.beatNumber,
    parentSceneId: current.data.parentSceneId,
    heading: stringValue(body, 'heading', 'title') ?? current.data.title,
    scriptText: stringValue(body, 'scriptText', 'script_text') ?? current.data.scriptText ?? current.data.detail ?? '',
    narrationText: stringValue(body, 'narrationText', 'narration_text') ?? current.data.narrationText ?? '',
    startSeconds: Number(body.startSeconds ?? body.start_seconds ?? current.data.startSeconds ?? 0),
    endSeconds: Number(body.endSeconds ?? body.end_seconds ?? current.data.endSeconds ?? 1),
  }
  return updateLocalGraphNode(snapshot, nodeId, draft)
}

export const Route = createFileRoute('/api/graph/nodes/$nodeId')({
  server: {
    handlers: {
      PATCH: async ({ request, params }) => {
        const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
        try {
          const response = await backendFetch(`/graph/nodes/${encodeURIComponent(params.nodeId)}`, { method: 'PATCH', body: JSON.stringify(patchBody(body)) })
          return Response.json(response, { headers: { 'X-CLIO-Source': 'fastapi' } })
        } catch (error) {
          const conflict = backendConflictResponse(error)
          if (conflict) return conflict
          if (!(error instanceof BackendUnavailableError)) throw error
          try {
            const next = localPatch(readWorkspaceSnapshot(), params.nodeId, body)
            setWorkspaceSnapshot(next)
            return Response.json({ id: params.nodeId, local: true }, { headers: { 'X-CLIO-Source': 'local-fallback' } })
          } catch (localError) {
            return Response.json({ detail: { error_code: 'node.update_failed', message: localError instanceof Error ? localError.message : 'Unable to update node' } }, { status: 409 })
          }
        }
      },
      DELETE: async ({ request, params }) => {
        const url = new URL(request.url)
        const actor = url.searchParams.get('actor') ?? 'editorial'
        const runtimeMode = url.searchParams.get('runtimeMode') ?? 'simulation'
        try {
          const response = await backendFetch(`/graph/nodes/${encodeURIComponent(params.nodeId)}?actor=${encodeURIComponent(actor)}&runtime_mode=${encodeURIComponent(runtimeMode)}`, { method: 'DELETE' })
          return Response.json(response, { headers: { 'X-CLIO-Source': 'fastapi' } })
        } catch (error) {
          const conflict = backendConflictResponse(error)
          if (conflict) return conflict
          if (!(error instanceof BackendUnavailableError)) throw error
          try {
            const next = deleteLocalGraphNode(readWorkspaceSnapshot(), params.nodeId)
            setWorkspaceSnapshot(next)
            return Response.json({ deleted_ids: [params.nodeId], local: true }, { headers: { 'X-CLIO-Source': 'local-fallback' } })
          } catch (localError) {
            return Response.json({ detail: { error_code: 'node.delete_failed', message: localError instanceof Error ? localError.message : 'Unable to delete node' } }, { status: 409 })
          }
        }
      },
    },
  },
})
