import { createFileRoute } from '@tanstack/react-router'
import { backendConflictResponse, backendFetch } from '../lib/api'
import { applyEditorialDecision, readWorkspaceSnapshot, setWorkspaceSnapshot } from '../lib/workspace'
import type { EditorialDecisionRequest } from '../lib/contracts'

export const Route = createFileRoute('/api/decisions/editorial')({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const body = (await request.json()) as EditorialDecisionRequest
        if (!body?.proposalId || !body?.decision) return Response.json({ error: 'proposalId and decision are required' }, { status: 400 })
        let source = 'local-simulation'
        try {
          const workspace = await backendFetch<{ workflows?: Array<{ id?: string }> }>('/workspace?filmId=demo-feature&revisionId=rev-05')
          const workflowId = workspace.workflows?.[0]?.id
          if (workflowId) {
            await backendFetch('/decisions/editorial', {
              method: 'POST',
              body: JSON.stringify({ workflow_id: workflowId, proposal_id: body.proposalId, approved: body.decision === 'approve', actor: body.actor ?? 'EDITORIAL', reason: body.note, runtime_mode: 'simulation' }),
            })
            source = 'fastapi'
          }
        } catch (error) {
          const conflict = backendConflictResponse(error)
          if (conflict) return conflict
          // Keep the local demo path available when FastAPI is down or guards a
          // duplicate decision with 409.
        }
        const snapshot = setWorkspaceSnapshot(applyEditorialDecision(readWorkspaceSnapshot(), body))
        return Response.json({ decision: body.decision, workflowEvents: snapshot.workflowEvents, provenance: snapshot.approvals.at(-1)?.provenance, source }, { status: 201 })
      },
    },
  },
})
