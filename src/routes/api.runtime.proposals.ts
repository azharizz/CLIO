import { createFileRoute } from '@tanstack/react-router'
import { backendConflictResponse, backendFetch } from '../lib/api'
import { readWorkspaceSnapshot, selectProposal, setWorkspaceSnapshot } from '../lib/workspace'

export const Route = createFileRoute('/api/runtime/proposals')({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const body = (await request.json().catch(() => ({}))) as { proposalId?: string }
        const proposalId = body.proposalId ?? 'cut-sc17'
        let remoteSource = 'local-simulation'
        try {
          const workspace = await backendFetch<{ workflows?: Array<{ id?: string }> }>('/workspace?filmId=demo-feature&revisionId=rev-05')
          const workflowId = workspace.workflows?.[0]?.id
          if (workflowId) {
            await backendFetch('/runtime/proposals', { method: 'POST', body: JSON.stringify({ workflow_id: workflowId, proposal_id: proposalId, actor: 'EDITORIAL', runtime_mode: 'simulation' }) })
            remoteSource = 'fastapi'
          }
        } catch (error) {
          const conflict = backendConflictResponse(error)
          if (conflict) return conflict
          // Local append-only mirror is the documented no-provider path.
        }
        const snapshot = setWorkspaceSnapshot(selectProposal(readWorkspaceSnapshot(), proposalId))
        return Response.json({ proposalId, proposals: snapshot.runtimeProposals, provenance: { source: remoteSource === 'fastapi' ? 'computed' : 'agent_simulation', label: remoteSource === 'fastapi' ? 'FASTAPI REPOSITORY' : 'LOCAL SIMULATION' }, source: remoteSource })
      },
    },
  },
})
