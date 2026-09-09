import { createFileRoute } from '@tanstack/react-router'
import { BackendUnavailableError, backendConflictResponse, backendFetch } from '../lib/api'
import { createLocalGraphNode, readWorkspaceSnapshot, setWorkspaceSnapshot, type GraphNodeDraft } from '../lib/workspace'

function draftFromBody(body: Record<string, unknown>): GraphNodeDraft {
  const kind = body.kind === 'beat' ? 'beat' : 'scene'
  return {
    kind,
    ...(typeof body.sceneNumber === 'string' ? { sceneNumber: body.sceneNumber } : typeof body.scene_number === 'string' ? { sceneNumber: body.scene_number } : {}),
    ...(typeof body.beatNumber === 'number' ? { beatNumber: body.beatNumber } : typeof body.beat_number === 'number' ? { beatNumber: body.beat_number } : {}),
    ...(typeof body.parentSceneId === 'string' ? { parentSceneId: body.parentSceneId } : typeof body.parent_scene_id === 'string' ? { parentSceneId: body.parent_scene_id } : {}),
    heading: String(body.heading ?? body.title ?? ''),
    scriptText: String(body.scriptText ?? body.script_text ?? ''),
    narrationText: String(body.narrationText ?? body.narration_text ?? ''),
    startSeconds: Number(body.startSeconds ?? body.start_seconds ?? 0),
    endSeconds: Number(body.endSeconds ?? body.end_seconds ?? 1),
  }
}

function backendBody(body: Record<string, unknown>): Record<string, unknown> {
  const draft = draftFromBody(body)
  return {
    kind: draft.kind,
    scene_number: draft.sceneNumber,
    beat_number: draft.beatNumber,
    parent_scene_id: draft.parentSceneId,
    heading: draft.heading,
    script_text: draft.scriptText,
    narration_text: draft.narrationText || null,
    start_seconds: draft.startSeconds,
    end_seconds: draft.endSeconds,
    actor: String(body.actor ?? 'editorial'),
    runtime_mode: String(body.runtime_mode ?? body.runtimeMode ?? 'simulation'),
  }
}

export const Route = createFileRoute('/api/graph/nodes')({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
        try {
          const response = await backendFetch('/graph/nodes', { method: 'POST', body: JSON.stringify(backendBody(body)) })
          return Response.json(response, { status: 201, headers: { 'X-CLIO-Source': 'fastapi' } })
        } catch (error) {
          const conflict = backendConflictResponse(error)
          if (conflict) return conflict
          if (!(error instanceof BackendUnavailableError)) throw error
          try {
            const next = createLocalGraphNode(readWorkspaceSnapshot(), draftFromBody(body))
            setWorkspaceSnapshot(next)
            return Response.json({ id: next.selectedNodeId, local: true }, { status: 201, headers: { 'X-CLIO-Source': 'local-fallback' } })
          } catch (localError) {
            return Response.json({ detail: { error_code: 'node.create_failed', message: localError instanceof Error ? localError.message : 'Unable to create node' } }, { status: 409 })
          }
        }
      },
    },
  },
})
