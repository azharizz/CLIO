/**
 * Shared browser/server contracts for the CLIO workspace.
 *
 * The browser only ever deals with these transport-neutral values.  A
 * ClickHouse row, an MCP result, or a local simulation is normalized into the
 * same shape before it reaches the graph.
 */

export const PIPELINE_STAGES = [
  'Script',
] as const

/**
 * The current product slice is script-first.  The wider production stages
 * remain accepted at the transport boundary so an older backend can still
 * answer while the graph itself stays deliberately small.
 */
export type PipelineStage =
  | (typeof PIPELINE_STAGES)[number]
  | 'Scene'
  | 'Story Beat'
  | 'Shoot'
  | 'Shot'
  | 'Take'
  | 'Edit'
  | 'Master'
  | 'Localization'
  | 'Delivery'

export type ProvenanceSource =
  | 'direct_clickhouse'
  | 'clickhouse_mcp'
  | 'agent_simulation'
  | 'gemini_adk'
  | 'computed'
  | 'estimate'

export type Tone = 'understood' | 'breaking' | 'resolved' | 'split' | 'pending'

export type WorkflowPhase =
  | 'workspace'
  | 'revision'
  | 'scene'
  | 'agent'
  | 'runtime'
  | 'impact'
  | 'editorial'
  | 'delivery'
  | 'provenance'

/** The graph has an all-film map and independently expanded parent traces. */
export type GraphViewMode = 'overview' | 'trace'

/** Human-readable role of an entity in the film graph. */
export type GraphEntityType =
  | 'film'
  | 'revision'
  | 'scene'
  | 'beat'
  | 'asset'
  | 'impact'
  | 'decision'
  | 'release'
  | 'cluster'

export type ApprovalDecision = 'approve' | 'hold'

export interface Provenance {
  source: ProvenanceSource
  label: string
  at?: string | undefined
  detail?: string | undefined
}

export interface ValueWithProvenance<T> {
  value: T
  provenance: Provenance
}

export type GraphNodeKind =
  | 'film'
  | 'revision'
  | 'scene'
  | 'beat'
  | 'stage'
  | 'impact'
  | 'proposal'
  | 'variant'
  | 'cluster'

export interface GraphNodeData {
  kind: GraphNodeKind
  stage?: PipelineStage | undefined
  stageIndex?: number | undefined
  /** Script-first node identity and timing fields. */
  sceneNumber?: string | undefined
  /** Child beat identity. Beats stay attached to their parent scene. */
  beatNumber?: number | undefined
  parentSceneId?: string | undefined
  childCount?: number | undefined
  scriptText?: string | undefined
  /** Spoken/narrated line associated with this scene or beat. */
  narrationText?: string | undefined
  previousScriptText?: string | undefined
  currentScriptText?: string | undefined
  startSeconds?: number | undefined
  endSeconds?: number | undefined
  durationSeconds?: number | undefined
  eyebrow: string
  title: string
  code?: string | undefined
  metric?: string | undefined
  secondary?: string | undefined
  status: Tone
  detail?: string | undefined
  provenance?: Provenance | undefined
  approvalRequired?: boolean | undefined
  selectedAction?: boolean | undefined
  split?: boolean | undefined
  branch?: 'editorial' | 'production' | 'delivery' | undefined
  /** The domain role shown in the node model legend. */
  entityType?: GraphEntityType | undefined
  /** `true` when a node summarizes a film-wide collection. */
  aggregate?: boolean | undefined
  /** Optional count for a summarized collection. */
  count?: number | undefined
  /** Scope keeps a film-wide summary distinct from the selected trace. */
  scope?: 'film' | 'revision' | 'focus' | 'beat' | 'decision' | 'release' | undefined
  /** A short-lived, display-only focus state from the latest agent result. */
  agentRelated?: boolean | undefined
}

export interface GraphPosition {
  x: number
  y: number
}

export interface WorkspaceNode {
  id: string
  position: GraphPosition
  data: GraphNodeData
}

/** The smallest editable unit exposed by the script graph. */
export type EditableNodeKind = 'scene' | 'beat'

export interface GraphNodeDraft {
  kind: EditableNodeKind
  sceneNumber?: string | undefined
  beatNumber?: number | undefined
  parentSceneId?: string | undefined
  heading: string
  scriptText: string
  narrationText: string
  startSeconds: number
  endSeconds: number
}

export interface GraphEdgeData {
  relation: string
  tone: Tone
  /** Legacy-friendly alias used by graph mapping tests. */
  kind?: 'backbone' | 'impact' | 'delivery' | 'beat' | undefined
  provenance?: Provenance | undefined
  branch?: 'backbone' | 'impact' | 'delivery' | undefined
}

export interface WorkspaceEdge {
  id: string
  source: string
  target: string
  data: GraphEdgeData
}

export interface ScriptGitRevision {
  sha: string
  shortSha: string
  message: string
  author: string
  committedAt?: string
  htmlUrl?: string
  selected?: boolean
}

export interface ScriptGitParsed {
  sceneCount: number
  beatCount: number
  durationSeconds: number
  timingEstimated: boolean
}

/** Compact GitHub source state retained in the workspace event trail. */
export interface ScriptGitState {
  source: 'github'
  repository: string
  owner: string
  repo: string
  path: string
  ref: string
  sha: string
  shortSha: string
  htmlUrl?: string
  rawUrl?: string
  size?: number
  message?: string
  parsed: ScriptGitParsed
  revisions: ScriptGitRevision[]
  provenance: Provenance
}

/** Full read-only document returned by the GitHub loader before apply. */
export interface ScriptGitDocument extends ScriptGitState {
  content: string
  revisionId: string
  contentHash?: string
  nodes: WorkspaceNode[]
  edges: WorkspaceEdge[]
}

export interface ApprovalRecord {
  id: string
  decision: ApprovalDecision
  target: 'runtime' | 'delivery'
  actor: string
  note: string
  createdAt: string
  provenance: Provenance
}

export interface AgentEvent {
  id: string
  phase: AgentEventPhase
  label: string
  detail: string
  tone: Tone
  createdAt: string
  provenance: Provenance
}

export type AgentEventPhase = 'narrative' | 'graph' | 'analytics' | 'revision' | 'critic'

export interface RuntimeProposal {
  id: string
  label: string
  deltaMinutes: number
  resultMinutes: number
  costDelta: string
  confidence: string
  recommendation: boolean
  provenance: Provenance
  selected?: boolean
}

export type VariantStatus = 'ready' | 'conflict' | 'approved'

export interface DeliveryVariant {
  id: string
  platform: string
  territory: string
  audio: string
  subtitle: string
  runtime: number
  status: VariantStatus
  conflict?: string
  provenance: Provenance
}

export interface WorkflowEvent {
  eventType: string
  workflowId: string
  actor: string
  payload: Record<string, string | number | boolean | null>
  provenance: Provenance
  createdAt: string
}

export interface WorkspaceSnapshot {
  workspaceId: string
  filmId: string
  revisionId: string
  revisionLabel: string
  title: string
  subtitle: string
  changedScene: string
  revisionBefore: string
  revisionAfter: string
  /** Total running time of the current script cut, in seconds. */
  totalDurationSeconds: number
  /** Number of timed scene nodes in the current script map. */
  sceneCount: number
  /** Number of child beat nodes available beneath scenes. */
  beatCount: number
  frameRate: number
  currentRuntime: ValueWithProvenance<number>
  targetRuntime: ValueWithProvenance<number>
  deliveryCount: number
  graph: { nodes: WorkspaceNode[]; edges: WorkspaceEdge[] }
  runtimeProposals: RuntimeProposal[]
  deliveryVariants: DeliveryVariant[]
  approvals: ApprovalRecord[]
  workflowEvents: WorkflowEvent[]
  agentEvents: AgentEvent[]
  scriptGit?: ScriptGitState
  dataSource: Provenance
  providerError?: {
    attemptedSource: string
    fallbackSource: string
    message: string
  }
  /** Active agent runtime selected by the local backend configuration. */
  runtimeMode?: 'simulation' | 'live'
  selectedNodeId: string
}

export interface AgentRunRequest {
  workflowId: string
  prompt: string
  stage?: PipelineStage
  action?: 'inspect' | 'edit' | 'remove' | 'add'
  focusNode?: string
}

export interface EditorialDecisionRequest {
  workflowId: string
  proposalId: string
  decision: ApprovalDecision
  actor: string
  note?: string
}

export interface DeliveryCompileRequest {
  workflowId: string
  runtimeMinutes: number
}

export interface DeliveryApprovalRequest {
  workflowId: string
  variantId: string
  actor: string
  decision: ApprovalDecision
  note?: string
}

export interface DeliveryConflictResolutionRequest {
  workflowId: string
  variantId: string
  actor: string
  resolution?: string
}

export interface GraphQueryPort {
  getWorkspaceSnapshot(filmId: string, revisionId: string): Promise<WorkspaceSnapshot>
  getNodeImpact(nodeId: string): Promise<WorkspaceNode[]>
  getLineage(nodeId: string): Promise<string[]>
}

export interface AgentProvider {
  startRun(context: AgentRunRequest): AsyncIterable<AgentEvent>
}
