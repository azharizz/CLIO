/** Public workflow-state seam kept separate from transport and view code. */
export {
  applyApproval,
  applyEditorialDecision,
  approveDeliveryVariant,
  compileDelivery,
  createAgentEventStream,
  createFallbackSnapshot,
  downstreamFor,
  lineageFor,
  readWorkspaceSnapshot,
  recordApproval,
  selectProposal,
  setWorkspaceSnapshot,
  stageIds,
} from './workspace'

export type {
  ApprovalDecision,
  ApprovalRecord,
  DeliveryVariant,
  RuntimeProposal,
  WorkflowEvent,
  WorkspaceSnapshot,
} from './contracts'
