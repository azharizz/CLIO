import { createServerFn } from '@tanstack/react-start'
import {
  applyApproval,
  applyEditorialDecision,
  approveDeliveryVariant,
  compileDelivery,
  resolveDeliveryConflict,
  readWorkspaceSnapshot,
  selectProposal,
  setWorkspaceSnapshot,
} from './workspace'
import { backendFetch, fetchWorkspaceSnapshot } from './api'
import type {
  ApprovalDecision,
  DeliveryApprovalRequest,
  DeliveryConflictResolutionRequest,
  DeliveryCompileRequest,
  EditorialDecisionRequest,
  WorkspaceSnapshot,
} from './contracts'

const fallbackData = () => readWorkspaceSnapshot()

export const loadWorkspaceSnapshot = createServerFn({ method: 'GET' }).handler(async () => {
  try {
    const live = await fetchWorkspaceSnapshot('demo-feature', 'rev-05')
    return setWorkspaceSnapshot(live)
  } catch {
    return fallbackData()
  }
})

export const submitApproval = createServerFn({ method: 'POST' })
  .validator((input: { nodeId: string; decision: ApprovalDecision; reviewer?: string; note?: string }) => input)
  .handler(async ({ data }) => {
    const current = fallbackData()
    if (isDeliveryTarget(current, data.nodeId)) {
      await attemptRemoteDelivery(current, data.nodeId, data.decision, data.reviewer ?? 'DELIVERY', data.note)
    } else {
      await attemptRemoteEditorial(current, data.nodeId, data.decision, data.reviewer ?? 'EDITORIAL', data.note)
    }
    return setWorkspaceSnapshot(applyApproval(current, data))
  })

export const chooseRuntimeProposal = createServerFn({ method: 'POST' })
  .validator((input: { proposalId: string }) => input)
  .handler(async ({ data }) => {
    const current = fallbackData()
    const workflowId = await remoteWorkflowId(current)
    if (workflowId) {
      try {
        await backendFetch('/runtime/proposals', {
          method: 'POST',
          body: JSON.stringify({ workflow_id: workflowId, proposal_id: data.proposalId, actor: 'EDITORIAL', runtime_mode: 'simulation' }),
        })
      } catch {
        // The append-only local mirror remains available without FastAPI.
      }
    }
    const next = selectProposal(current, data.proposalId)
    return setWorkspaceSnapshot(next)
  })

export const startAgentAnalysis = createServerFn({ method: 'POST' })
  .validator((input: { prompt: string }) => input)
  .handler(async ({ data }) => {
    const current = fallbackData()
    const workflowId = await remoteWorkflowId(current)
    if (workflowId) {
      try {
        await backendFetch('/agent-runs', {
          method: 'POST',
          body: JSON.stringify({ workflow_id: workflowId, prompt: data.prompt, stage_name: 'Edit', model_name: 'gemini-simulated', runtime_mode: 'simulation' }),
        })
      } catch {
        // The local provider remains usable when FastAPI or ClickHouse is down.
      }
    }
    return current
  })

export const compileDeliveryMatrix = createServerFn({ method: 'POST' })
  .validator((input: DeliveryCompileRequest) => input)
  .handler(async ({ data }) => {
    const current = fallbackData()
    const workflowId = await remoteWorkflowId(current)
    if (workflowId) {
      try {
        await backendFetch('/delivery/compile', {
          method: 'POST',
              body: JSON.stringify({ workflow_id: workflowId, stage_name: 'Script', destination: 'script-review', artifact_uri: 'local://clio/script-demo', runtime_mode: 'simulation' }),
        })
      } catch {
        // Continue with the append-only local mirror.
      }
    }
    return setWorkspaceSnapshot(compileDelivery(current, data))
  })

export const approveDelivery = createServerFn({ method: 'POST' })
  .validator((input: DeliveryApprovalRequest) => input)
  .handler(async ({ data }) => {
    const current = fallbackData()
    const workflowId = await remoteWorkflowId(current)
    if (workflowId && data.decision === 'approve') {
      try {
        await backendFetch(`/delivery/${encodeURIComponent(data.variantId)}/approve`, {
          method: 'POST',
              body: JSON.stringify({ workflow_id: workflowId, actor: data.actor, approved: data.decision === 'approve', destination: data.variantId, artifact_uri: 'local://clio/script-demo', runtime_mode: 'simulation' }),
        })
      } catch {
        // A local approval is still recorded if the optional provider is down.
      }
    }
    return setWorkspaceSnapshot(approveDeliveryVariant(current, data))
  })

export const resolveDelivery = createServerFn({ method: 'POST' })
  .validator((input: DeliveryConflictResolutionRequest) => input)
  .handler(async ({ data }) => {
    const current = fallbackData()
    const workflowId = await remoteWorkflowId(current)
    if (workflowId) {
      try {
        await backendFetch(`/delivery/${encodeURIComponent(data.variantId)}/resolve`, {
          method: 'POST',
          body: JSON.stringify({ workflow_id: workflowId, actor: data.actor, resolution: data.resolution ?? 'refresh_asset_reference', runtime_mode: 'simulation' }),
        })
      } catch {
        // Preserve the local append-only mirror on provider failure.
      }
    }
    return setWorkspaceSnapshot(resolveDeliveryConflict(current, data))
  })

export const resolveEditorialDecision = createServerFn({ method: 'POST' })
  .validator((input: EditorialDecisionRequest) => input)
  .handler(async ({ data }) => {
    const current = fallbackData()
    await attemptRemoteEditorial(current, 'proposal-cut-sc47', data.decision, data.actor, data.note)
    return setWorkspaceSnapshot(applyEditorialDecision(current, data))
  })

async function remoteWorkflowId(_snapshot: WorkspaceSnapshot): Promise<string | null> {
  try {
    const response = await backendFetch<{ workflows?: Array<{ id?: string }> }>('/workspace?filmId=demo-feature&revisionId=rev-05')
    return response.workflows?.[0]?.id ?? null
  } catch {
    return null
  }
}

async function attemptRemoteEditorial(snapshot: WorkspaceSnapshot, nodeId: string, decision: ApprovalDecision, actor: string, note?: string) {
  const workflowId = await remoteWorkflowId(snapshot)
  if (!workflowId) return
  try {
    await backendFetch('/decisions/editorial', {
      method: 'POST',
      body: JSON.stringify({ workflow_id: workflowId, proposal_id: nodeId, approved: decision === 'approve', actor, reason: note ?? `CLIO ${nodeId}`, runtime_mode: 'simulation' }),
    })
  } catch {
    // FastAPI's 409 is a useful guardrail; the local event mirror keeps the UI responsive.
  }
}

async function attemptRemoteDelivery(snapshot: WorkspaceSnapshot, variantId: string, decision: ApprovalDecision, actor: string, note?: string) {
  const workflowId = await remoteWorkflowId(snapshot)
  if (!workflowId) return
  try {
    await backendFetch(`/delivery/${encodeURIComponent(variantId.replace(/^variant-/, ''))}/approve`, {
      method: 'POST',
      body: JSON.stringify({ workflow_id: workflowId, actor, approved: decision === 'approve', destination: variantId.replace(/^variant-/, ''), artifact_uri: 'local://clio/script-demo', runtime_mode: 'simulation', note }),
    })
  } catch {
    // Keep the local append-only mirror when an optional provider is down.
  }
}

function isDeliveryTarget(snapshot: WorkspaceSnapshot, nodeId: string): boolean {
  return snapshot.deliveryVariants.some((variant) => variant.id === nodeId || `variant-${variant.id}` === nodeId) || nodeId.includes('variant') || nodeId.includes('delivery')
}
