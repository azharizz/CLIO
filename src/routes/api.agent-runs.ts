import { createFileRoute } from '@tanstack/react-router'
import { backendFetch } from '../lib/api'

export const Route = createFileRoute('/api/agent-runs')({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
        const normalized: Record<string, unknown> = { ...body }
        if (!normalized.workflow_id && typeof normalized.workflowId === 'string') normalized.workflow_id = normalized.workflowId
        if (!normalized.stage_name && typeof normalized.stage === 'string') normalized.stage_name = normalized.stage
        if (!normalized.focus_node && typeof normalized.focusNode === 'string') normalized.focus_node = normalized.focusNode
        const hasUuidWorkflow = typeof normalized.workflow_id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(normalized.workflow_id)
        if (!hasUuidWorkflow) {
          delete normalized.workflow_id
          try {
            const workspace = await backendFetch<{ workflows?: Array<{ id?: string }> }>('/workspace?filmId=demo-feature&revisionId=rev-05')
            const workflowId = workspace.workflows?.[0]?.id
            if (workflowId) normalized.workflow_id = workflowId
          } catch {
            // The local simulation does not require a persisted workflow UUID.
          }
        }
        normalized.prompt = normalized.prompt ?? 'Assess V5 / TITANIC / SC 17 and recommend an editorial resolution.'
        normalized.runtime_mode = normalized.runtime_mode ?? 'simulation'
        try {
          if (!normalized.workflow_id) throw new Error('no workflow available')
          const response = await backendFetch('/agent-runs', { method: 'POST', body: JSON.stringify(normalized) })
          return Response.json(response, { status: 201, headers: { 'X-CLIO-Source': 'fastapi' } })
        } catch {
          const id = `sim-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
          return Response.json({ id, status: 'queued', runtime_mode: 'simulation', provenance: { source: 'agent_simulation', label: 'LOCAL SIMULATION', detail: 'same event shape as the future Gemini/ADK provider' } }, { status: 201, headers: { 'X-CLIO-Source': 'local-simulation' } })
        }
      },
    },
  },
})
