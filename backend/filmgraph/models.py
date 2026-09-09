from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStatus(str, Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    failed = "failed"


class ApprovalStatus(str, Enum):
    not_required = "not_required"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class AgentEventKind(str, Enum):
    started = "started"
    progress = "progress"
    tool_call = "tool_call"
    tool_result = "tool_result"
    message = "message"
    completed = "completed"
    failed = "failed"


class GraphNodeKind(str, Enum):
    script = "script"
    scene = "scene"
    # A timed child inside a scene.  Keep story_beat for older rows while the
    # local seed uses the shorter, browser-friendly `beat` value.
    beat = "beat"
    story_beat = "story_beat"
    shoot = "shoot"
    shot = "shot"
    take = "take"
    edit = "edit"
    master = "master"
    localization = "localization"
    delivery = "delivery"


class DeliveryStatus(str, Enum):
    queued = "queued"
    ready = "ready"
    delivered = "delivered"


class Provenance(BaseModel):
    # Keep the default inside the shared provenance vocabulary.  Simulation
    # and live-provider values are assigned explicitly by their adapters.
    source: Literal[
        "direct_clickhouse",
        "clickhouse_mcp",
        "agent_simulation",
        "gemini_adk",
        "computed",
        "estimate",
    ] = "computed"
    transport: str = "memory"
    adapter: Optional[str] = None
    runtime_mode: str = "simulation"
    requested_by: Optional[str] = None
    model_name: Optional[str] = None
    tool_name: Optional[str] = None


class PipelineStageDefinition(BaseModel):
    id: UUID
    sequence: int
    name: str
    description: str
    provenance: Provenance = Field(default_factory=Provenance)


class GraphNode(BaseModel):
    id: UUID
    kind: GraphNodeKind
    label: str
    sequence: int
    stage_name: str
    status: str = "ready"
    # Script-first graph fields.  They are optional so older catalog rows can
    # still be read during a local schema upgrade, but every seeded scene has
    # all four timing/text values populated.
    film_id: Optional[str] = None
    revision_id: Optional[str] = None
    scene_number: Optional[str] = None
    beat_number: Optional[int] = None
    parent_scene_id: Optional[str] = None
    heading: Optional[str] = None
    script_text: Optional[str] = None
    narration_text: Optional[str] = None
    start_seconds: Optional[int] = None
    end_seconds: Optional[int] = None
    duration_seconds: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)
    created_at: datetime = Field(default_factory=utcnow)


class ScriptGitRevision(BaseModel):
    """A compact commit row shown by the Script Git overlay."""

    sha: str
    short_sha: str
    message: str = "GitHub revision"
    author: str = "unknown"
    committed_at: Optional[str] = None
    html_url: Optional[str] = None
    selected: bool = False


class ScriptGitParsed(BaseModel):
    scene_count: int = 0
    beat_count: int = 0
    duration_seconds: int = 0
    timing_estimated: bool = False


class ScriptGitLoadRequest(BaseModel):
    source: str = Field(min_length=1, max_length=1000)
    ref: Optional[str] = Field(default=None, max_length=180)
    path: Optional[str] = Field(default=None, max_length=500)
    history_limit: int = Field(default=12, ge=1, le=30)


class ScriptGitApplyRequest(BaseModel):
    workflow_id: Optional[UUID] = None
    source: str = Field(min_length=1, max_length=1000)
    ref: Optional[str] = Field(default=None, max_length=180)
    path: Optional[str] = Field(default=None, max_length=500)
    sha: Optional[str] = Field(default=None, max_length=80)
    actor: str = Field(default="EDITORIAL", min_length=1, max_length=80)
    runtime_mode: str = "simulation"
    # A browser fallback may send the already-loaded document. The backend
    # re-fetches and reparses it whenever GitHub is available, so this field is
    # never treated as trusted write input.
    document: Optional[Dict[str, Any]] = None


class ScriptGitRevertRequest(BaseModel):
    """Restore the script graph captured by the latest Git apply/restore.

    The previous graph is kept inside the append-only workflow event by the
    server.  The browser never supplies a graph for this operation, which
    keeps recovery authoritative and prevents a stale client from overwriting
    the current script map.
    """

    workflow_id: Optional[UUID] = None
    actor: str = Field(default="EDITORIAL", min_length=1, max_length=80)
    runtime_mode: str = "simulation"


class GraphNodeCreateRequest(BaseModel):
    """Human-authored script node fields used by the CRUD boundary.

    The first slice deliberately limits writes to scenes and timed child
    beats.  Production assets are not silently created from this form.
    """

    kind: Literal["scene", "beat"] = "scene"
    scene_number: Optional[str] = None
    beat_number: Optional[int] = Field(default=None, ge=1)
    # Accept a UUID from the API or a stable local scene slug when the
    # browser is operating against its memory mirror.
    parent_scene_id: Optional[str] = None
    heading: str = Field(min_length=1, max_length=180)
    script_text: str = Field(min_length=1, max_length=4000)
    narration_text: Optional[str] = Field(default=None, max_length=4000)
    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(gt=0)
    actor: str = Field(default="editorial", min_length=1, max_length=80)
    runtime_mode: str = "simulation"


class GraphNodeUpdateRequest(BaseModel):
    """Editable script fields; identity and parentage stay stable."""

    heading: Optional[str] = Field(default=None, min_length=1, max_length=180)
    script_text: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    narration_text: Optional[str] = Field(default=None, max_length=4000)
    start_seconds: Optional[int] = Field(default=None, ge=0)
    end_seconds: Optional[int] = Field(default=None, gt=0)
    actor: str = Field(default="editorial", min_length=1, max_length=80)
    runtime_mode: str = "simulation"


class GraphEdge(BaseModel):
    id: UUID
    source_id: UUID
    target_id: UUID
    relation: str
    weight: float = 1.0
    confidence: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)
    created_at: datetime = Field(default_factory=utcnow)


class Workflow(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    stage_sequence: List[str] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.queued
    active_stage: Optional[str] = None
    approval_status: ApprovalStatus = ApprovalStatus.not_required
    delivery_status: DeliveryStatus = DeliveryStatus.queued
    provenance: Provenance = Field(default_factory=Provenance)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class WorkflowCreateRequest(BaseModel):
    name: str
    active_stage: Optional[str] = None
    requested_by: str = "editorial"
    runtime_mode: str = "simulation"


class WorkflowEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    sequence: int = 0
    kind: str
    actor: str = "system"
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)
    occurred_at: datetime = Field(default_factory=utcnow)


class WorkflowEventCreateRequest(BaseModel):
    kind: str
    actor: str = "system"
    payload: Dict[str, Any] = Field(default_factory=dict)
    runtime_mode: str = "simulation"


class WorkflowApprovalRequest(BaseModel):
    actor: str = "reviewer"
    approved: bool
    reason: Optional[str] = None
    runtime_mode: str = "simulation"


class AgentRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    stage_name: Optional[str] = None
    model_name: str = "gemini-simulated"
    runtime_mode: str = "simulation"
    status: WorkflowStatus = WorkflowStatus.queued
    prompt: str
    summary: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AgentRunCreateRequest(BaseModel):
    workflow_id: UUID
    prompt: str
    stage_name: Optional[str] = None
    model_name: str = "gemini-simulated"
    runtime_mode: str = "simulation"
    action: Optional[Literal["inspect", "edit", "remove", "add"]] = None
    focus_node: Optional[str] = None


class AgentEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    sequence: int = 0
    kind: AgentEventKind
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)
    occurred_at: datetime = Field(default_factory=utcnow)


class DeliveryRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    stage_name: str
    destination: str
    status: DeliveryStatus = DeliveryStatus.queued
    artifact_uri: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)
    delivered_at: datetime = Field(default_factory=utcnow)


class DeliveryCreateRequest(BaseModel):
    workflow_id: UUID
    stage_name: Optional[str] = None
    destination: str = "release"
    artifact_uri: Optional[str] = None
    status: DeliveryStatus = DeliveryStatus.ready
    runtime_mode: str = "simulation"


class RuntimeProposalSelectRequest(BaseModel):
    workflow_id: UUID
    proposal_id: str = "cut-sc17"
    actor: str = "editorial"
    runtime_mode: str = "simulation"


class EditorialDecisionRequest(BaseModel):
    workflow_id: UUID
    proposal_id: str = "cut-sc17"
    approved: bool
    actor: str = "reviewer"
    reason: Optional[str] = None
    runtime_mode: str = "simulation"


class DeliveryVariantApprovalRequest(BaseModel):
    workflow_id: UUID
    actor: str = "delivery"
    approved: bool = True
    destination: Optional[str] = None
    artifact_uri: Optional[str] = None
    runtime_mode: str = "simulation"


class DeliveryVariantResolveRequest(BaseModel):
    workflow_id: UUID
    actor: str = "localization"
    resolution: str = "refresh_asset_reference"
    runtime_mode: str = "simulation"


class WorkspaceSummary(BaseModel):
    pipeline_name: str
    stage_count: int
    node_count: int
    edge_count: int
    workflow_count: int
    run_count: int
    delivery_count: int
    approval_count: int


class WorkspaceRequest(BaseModel):
    film_id: Optional[str] = None
    revision_id: Optional[str] = None


class WorkspaceSnapshot(BaseModel):
    request: WorkspaceRequest
    workspace: WorkspaceSummary
    impact: ImpactSummary
    runtime: RuntimeSummary
    editorial: EditorialSummary
    delivery: DeliverySummary
    graph_contract: GraphContractSummary
    pipeline_stages: List[PipelineStageDefinition]
    graph_nodes: List[GraphNode]
    graph_edges: List[GraphEdge]
    workflows: List[Workflow]
    agent_runs: List[AgentRun]
    provenance: ProvenanceSummary
    workflow_events: List[WorkflowEvent] = Field(default_factory=list)
    runtime_proposals: List[Dict[str, Any]] = Field(default_factory=list)
    delivery_variants: List[Dict[str, Any]] = Field(default_factory=list)
    delivery_conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    # GitHub-backed screenplay source. The content itself is intentionally not
    # included in workspace snapshots; the Script Git overlay loads it on
    # demand while this compact state survives refresh through workflow events.
    script_git: Optional[Dict[str, Any]] = None
    # Read-side diagnostics make the MCP-first/fallback decision observable
    # without exposing transport details to the browser's graph contract.
    query_source: str = "computed"
    provider_error: Optional[Dict[str, Any]] = None


class RuntimeProposal(BaseModel):
    workflow_id: UUID
    workflow_name: str
    proposed_stage: str
    action: str
    confidence: float
    rationale: str
    provenance: Provenance = Field(default_factory=Provenance)


class ImpactSummary(BaseModel):
    stage_coverage: int
    completed_workflows: int
    approved_workflows: int
    delivery_ready: int
    delivery_count: int
    graph_density: float


class RuntimeSummary(BaseModel):
    environment: str
    storage_mode: str
    runtime_mode: str
    mcp_enabled: bool
    clickhouse_enabled: bool
    python_target: str = "3.13"


class EditorialItem(BaseModel):
    workflow_id: UUID
    workflow_name: str
    active_stage: Optional[str] = None
    approval_status: ApprovalStatus = ApprovalStatus.not_required
    last_event_kind: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)


class EditorialSummary(BaseModel):
    pending_approvals: List[EditorialItem] = Field(default_factory=list)
    approved_workflows: List[EditorialItem] = Field(default_factory=list)


class DeliveryItem(BaseModel):
    workflow_id: UUID
    workflow_name: str
    stage_name: str
    status: DeliveryStatus
    destination: str
    artifact_uri: Optional[str] = None
    provenance: Provenance = Field(default_factory=Provenance)


class DeliverySummary(BaseModel):
    ready: List[DeliveryItem] = Field(default_factory=list)
    delivered: List[DeliveryItem] = Field(default_factory=list)


class ProvenanceItem(BaseModel):
    entity_type: str
    entity_id: UUID
    provenance: Provenance


class ProvenanceSummary(BaseModel):
    items: List[ProvenanceItem] = Field(default_factory=list)


class GraphContractSummary(BaseModel):
    node_kinds: List[GraphNodeKind]
    edge_relations: List[str]
    stage_names: List[str]


class PlanSummary(BaseModel):
    pipeline_name: str
    stage_count: int
    node_count: int
    edge_count: int
    workflow_count: int
    run_count: int
    delivery_count: int
    approval_count: int
    runtime_mode: str
    api_endpoints: List[str]


class HealthResponse(BaseModel):
    status: str
    environment: str
    storage_mode: str
    runtime_mode: str
