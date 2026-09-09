import { createFileRoute } from '@tanstack/react-router'
import { backendConflictResponse, backendFetch } from '../lib/api'
import { approveDeliveryVariant, readWorkspaceSnapshot, setWorkspaceSnapshot } from '../lib/workspace'
import type { DeliveryApprovalRequest } from '../lib/contracts'

export const Route = createFileRoute('/api/delivery/$variantId/approve')({
  server: {
    handlers: {
      POST: async ({ request, params }) => {
        const body = (await request.json().catch(() => ({}))) as Partial<DeliveryApprovalRequest>
        const input: DeliveryApprovalRequest = {
          workflowId: body.workflowId ?? readWorkspaceSnapshot().workspaceId,
          variantId: params.variantId,
          actor: body.actor ?? 'DELIVERY LEAD',
          decision: body.decision ?? 'approve',
          ...(body.note ? { note: body.note } : {}),
        }
        let source = 'local-simulation'
        try {
          const workspace = await backendFetch<{ workflows?: Array<{ id?: string }> }>('/workspace?filmId=demo-feature&revisionId=rev-05')
          const workflowId = workspace.workflows?.[0]?.id
          if (workflowId) {
            await backendFetch(`/delivery/${encodeURIComponent(params.variantId)}/approve`, {
              method: 'POST',
              body: JSON.stringify({ workflow_id: workflowId, actor: input.actor, approved: input.decision === 'approve', destination: params.variantId, artifact_uri: 'local://clio/script-demo', runtime_mode: 'simulation' }),
            })
            source = 'fastapi'
          }
        } catch (error) {
          const conflict = backendConflictResponse(error)
          if (conflict) return conflict
          // The local event log remains the no-provider fallback.
        }
        const snapshot = setWorkspaceSnapshot(approveDeliveryVariant(readWorkspaceSnapshot(), input))
        return Response.json({ variantId: params.variantId, variants: snapshot.deliveryVariants, provenance: snapshot.approvals.at(-1)?.provenance, source }, { status: 201 })
      },
    },
  },
})
