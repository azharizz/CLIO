import { createFileRoute } from '@tanstack/react-router'
import { BackendUnavailableError, backendConflictResponse, backendFetch } from '../lib/api'
import { applyLocalScriptGit, readWorkspaceSnapshot, setWorkspaceSnapshot } from '../lib/workspace'
import type { ScriptGitDocument } from '../lib/contracts'

export const Route = createFileRoute('/api/script-git/apply')({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
        // The document is only a browser resilience mirror. The Python side
        // refetches the selected GitHub revision and remains authoritative.
        const document = body.document as ScriptGitDocument | undefined
        const { document: _ignored, ...remoteBody } = body
        try {
          const payload = await backendFetch<Record<string, unknown>>('/script-git/apply', {
            method: 'POST',
            body: JSON.stringify(remoteBody),
          }, 12_000)
          return Response.json(payload, { headers: { 'X-CLIO-Source': 'repository' } })
        } catch (error) {
          const conflict = backendConflictResponse(error)
          if (conflict) return conflict
          if (!(error instanceof BackendUnavailableError) || !document?.nodes?.length) {
            if (error instanceof BackendUnavailableError) {
              return Response.json(
                error.responseBody ?? { detail: { error_code: 'script_git.apply_failed', message: error.message } },
                { status: error.status && error.status >= 400 ? error.status : 502, headers: { 'X-CLIO-Source': 'local-error' } },
              )
            }
            throw error
          }
          try {
            const local = applyLocalScriptGit(readWorkspaceSnapshot(), document)
            setWorkspaceSnapshot(local)
            return Response.json({ local: true, script_git: local.scriptGit, graph_nodes: local.graph.nodes, graph_edges: local.graph.edges }, { headers: { 'X-CLIO-Source': 'local-fallback' } })
          } catch (localError) {
            return Response.json({ detail: { error_code: 'script_git.local_apply_failed', message: localError instanceof Error ? localError.message : 'Unable to apply the GitHub script locally' } }, { status: 422 })
          }
        }
      },
    },
  },
})
