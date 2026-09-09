import { createFileRoute } from '@tanstack/react-router'
import { backendConflictResponse, backendFetch } from '../lib/api'
import { readWorkspaceSnapshot, resolveDeliveryConflict, setWorkspaceSnapshot } from '../lib/workspace'
import type { DeliveryConflictResolutionRequest } from '../lib/contracts'

export const Route = createFileRoute('/api/delivery/$variantId/resolve')({
  server: {
    handlers: {
      POST: async ({ request, params }) => {
        const body = (await request.json().catch(() => ({}))) as Partial<DeliveryConflictResolutionRequest>
        const input: DeliveryConflictResolutionRequest = {
          workflowId: body.workflowId ?? readWorkspaceSnapshot().workspaceId,
          variantId: params.variantId,
          actor: body.actor ?? 'LOCALIZATION LEAD',
          ...(body.resolution ? { resolution: body.resolution } : {}),
        }
        let source = 'local-simulation'
        try {
          const workspace = await backendFetch<{ workflows?: Array<{ id?: string }> }>('/workspace?filmId=demo-feature&revisionId=rev-05')
          const workflowId = workspace.workflows?.[0]?.id
          if (workflowId) {
            await backendFetch(`/delivery/${encodeURIComponent(params.variantId)}/resolve`, {
              method: 'POST',
              body: JSON.stringify({ workflow_id: workflowId, actor: input.actor, resolution: input.resolution ?? 'refresh_asset_reference', runtime_mode: 'simulation' }),
            })
            source = 'fastapi'
          }
        } catch (error) {
          const conflict = backendConflictResponse(error)
          if (conflict) return conflict
          // The local event log remains the documented fallback.
        }
        const snapshot = setWorkspaceSnapshot(resolveDeliveryConflict(readWorkspaceSnapshot(), input))
        return Response.json({ variantId: params.variantId, variants: snapshot.deliveryVariants, provenance: snapshot.workflowEvents.at(-1)?.provenance, source }, { status: 201 })
      },
    },
  },
})
