import { createFileRoute } from '@tanstack/react-router'
import { backendConflictResponse, backendFetch } from '../lib/api'
import { compileDelivery, readWorkspaceSnapshot, setWorkspaceSnapshot } from '../lib/workspace'
import type { DeliveryCompileRequest } from '../lib/contracts'

export const Route = createFileRoute('/api/delivery/compile')({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const body = (await request.json().catch(() => ({}))) as DeliveryCompileRequest
        let source = 'local-simulation'
        try {
          const workspace = await backendFetch<{ workflows?: Array<{ id?: string }> }>('/workspace?filmId=demo-feature&revisionId=rev-05')
          const workflowId = workspace.workflows?.[0]?.id
          if (workflowId) {
            await backendFetch('/delivery/compile', {
              method: 'POST',
              body: JSON.stringify({ workflow_id: workflowId, stage_name: 'Script', destination: 'script-review', artifact_uri: 'local://clio/script-demo', runtime_mode: 'simulation' }),
            })
            source = 'fastapi'
          }
        } catch (error) {
          const conflict = backendConflictResponse(error)
          if (conflict) return conflict
          // Deterministic local QC remains available without the optional API.
        }
        const snapshot = setWorkspaceSnapshot(compileDelivery(readWorkspaceSnapshot(), body))
        return Response.json({ variants: snapshot.deliveryVariants, provenance: { source: 'computed', label: 'QC RULES' }, source }, { status: 201 })
      },
    },
  },
})
