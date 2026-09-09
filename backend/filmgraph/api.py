from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from filmgraph.dependencies import get_repository, get_service, get_settings, reset_runtime_state
from filmgraph.models import (
    AgentEvent,
    AgentEventKind,
    AgentRun,
    AgentRunCreateRequest,
    ApprovalStatus,
    DeliveryCreateRequest,
    DeliveryItem,
    DeliveryRecord,
    DeliveryStatus,
    DeliverySummary,
    DeliveryVariantApprovalRequest,
    DeliveryVariantResolveRequest,
    EditorialItem,
    EditorialSummary,
    GraphContractSummary,
    GraphEdge,
    GraphNode,
    GraphNodeCreateRequest,
    GraphNodeUpdateRequest,
    GraphNodeKind,
    HealthResponse,
    ImpactSummary,
    PipelineStageDefinition,
    PlanSummary,
    Provenance,
    ProvenanceItem,
    ProvenanceSummary,
    RuntimeProposal,
    RuntimeProposalSelectRequest,
    RuntimeSummary,
    EditorialDecisionRequest,
    WorkspaceRequest,
    WorkspaceSnapshot,
    Workflow,
    WorkflowApprovalRequest,
    WorkflowCreateRequest,
    WorkflowEvent,
    WorkflowEventCreateRequest,
    WorkspaceSummary,
    ScriptGitApplyRequest,
    ScriptGitLoadRequest,
)
from filmgraph.integrations.mcp import McpFirstFilmGraphService
from filmgraph.integrations.agents import provider_for
from filmgraph.integrations.script_git import (
    ScriptGitError,
    compact_git_state,
    load_github_script,
)
from filmgraph.models import WorkflowStatus


router = APIRouter(prefix="/api/v1")


def _service() -> McpFirstFilmGraphService:
    return get_service()


@router.get("/health", response_model=HealthResponse)
def api_v1_health() -> HealthResponse:
    settings = get_settings()
    storage_mode = _storage_mode()
    return HealthResponse(status="ok", environment=settings.environment, storage_mode=storage_mode, runtime_mode=settings.agent_runtime_mode)


@router.post("/test/reset")
def reset_demo_state():
    """Reset only local in-process state; never used by the product UI."""
    reset_runtime_state()
    return {"status": "reset", "scope": "local-demo"}


def _repo():
    return get_repository()


def _storage_mode() -> str:
    return "clickhouse" if _repo().__class__.__name__ == "ClickHouseFilmGraphRepository" else "memory"


def _conflict(error_code: str, message: str, **details):
    payload = {"error_code": error_code, "message": message}
    if details:
        payload["details"] = details
    raise HTTPException(status_code=409, detail=payload)


def _latest_script_git_state(workflows: List[Workflow], service: McpFirstFilmGraphService) -> Optional[Dict[str, Any]]:
    """Reconstruct the current GitHub source from append-only workflow events."""
    events: List[WorkflowEvent] = []
    for workflow in workflows:
        events.extend(service.list_workflow_events(workflow.id))
    for event in sorted(events, key=lambda item: (item.occurred_at, item.sequence), reverse=True):
        if event.kind not in {"script.git.applied", "script.git.loaded"}:
            continue
        state = event.payload.get("script_git") if isinstance(event.payload, dict) else None
        if isinstance(state, dict):
            return state
        # Older local events may have stored the metadata at the top level.
        if isinstance(event.payload, dict) and event.payload.get("repository"):
            return dict(event.payload)
    return None


def _require_workflow(workflow_id: UUID) -> Workflow:
    workflow = _service().get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return workflow


def _validate_workflow_append(workflow: Workflow, kind: str, payload: dict) -> None:
    existing = _service().list_workflow_events(workflow.id)
    if kind == "workflow.started":
        _conflict("workflow.already_started", "workflow already started", workflow_id=str(workflow.id))
    if kind == "workflow.approval_requested":
        if not existing or existing[-1].kind != "workflow.started":
            _conflict("workflow.approval_not_ready", "approval request must follow workflow start", workflow_id=str(workflow.id))
    if kind in {"workflow.approved", "workflow.rejected"} and workflow.approval_status != ApprovalStatus.pending:
        _conflict("workflow.approval_missing", "workflow approval is not pending", workflow_id=str(workflow.id))
    if kind == "workflow.stage_advanced":
        stage = payload.get("stage")
        if not stage or stage not in workflow.stage_sequence:
            _conflict("workflow.invalid_stage", "stage is not in the workflow sequence", workflow_id=str(workflow.id), stage=stage)
    if kind == "workflow.delivered" and workflow.delivery_status not in {DeliveryStatus.ready, DeliveryStatus.delivered}:
        _conflict("workflow.delivery_not_ready", "delivery must be compiled before approval", workflow_id=str(workflow.id))


def _validate_delivery_request(workflow: Workflow, status: DeliveryStatus) -> None:
    if status == DeliveryStatus.delivered and workflow.approval_status != ApprovalStatus.approved:
        _conflict("delivery.not_approved", "delivery approval requires an approved workflow", workflow_id=str(workflow.id))


def _build_workspace_snapshot(film_id: Optional[str], revision_id: Optional[str]) -> WorkspaceSnapshot:
    repo = _repo()
    service = _service()
    pipeline_stages = service.list_pipeline_stages()
    graph_nodes = service.list_graph_nodes()
    graph_edges = service.list_graph_edges()
    workflows = service.list_workflows()
    agent_runs = service.list_agent_runs()
    # This slice is intentionally script-only.  Keep the old repository
    # methods available for future delivery work, but never surface stale
    # runtime/package rows in the active workspace.
    delivery_records = []
    workflow_events = [
        event
        for workflow in workflows
        for event in service.list_workflow_events(workflow.id)
        if not any(token in event.kind.lower() for token in ("delivery", "runtime", "master", "localization"))
    ]
    runtime_proposals: List[Dict[str, Any]] = []
    delivery_variants: List[Dict[str, Any]] = []
    delivery_conflicts: List[Dict[str, Any]] = []
    approvals = len([workflow for workflow in workflows if workflow.approval_status != ApprovalStatus.not_required])
    workspace_summary = WorkspaceSummary(
        pipeline_name="CLIO script graph",
        stage_count=len(pipeline_stages),
        node_count=len(graph_nodes),
        edge_count=len(graph_edges),
        workflow_count=len(workflows),
        run_count=len(agent_runs),
        delivery_count=len(delivery_records),
        approval_count=approvals,
    )
    return WorkspaceSnapshot(
        request=WorkspaceRequest(film_id=film_id, revision_id=revision_id),
        workspace=workspace_summary,
        impact=impact(),
        runtime=runtime(),
        editorial=editorial(),
        delivery=list_delivery(),
        graph_contract=service.graph_contract(),
        pipeline_stages=pipeline_stages,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        workflows=workflows,
        agent_runs=agent_runs,
        provenance=ProvenanceSummary(items=repo.list_provenance()),
        workflow_events=workflow_events,
        runtime_proposals=runtime_proposals,
        delivery_variants=delivery_variants,
        delivery_conflicts=delivery_conflicts,
        script_git=_latest_script_git_state(workflows, service),
        query_source=service.last_source,
        provider_error=(
            {
                "attempted_source": "clickhouse_mcp",
                "fallback_source": "direct_clickhouse" if service.last_source == "direct_clickhouse" else "computed",
                "message": service.last_error,
            }
            if service.last_error
            else None
        ),
    )


def _replay_catalog_events(
    runtime_proposals: List[Dict[str, Any]],
    delivery_variants: List[Dict[str, Any]],
    delivery_conflicts: List[Dict[str, Any]],
    events: List[WorkflowEvent],
) -> None:
    """Project append-only decisions onto read-only catalog rows.

    ClickHouse keeps catalog rows immutable for this local workflow.  The
    event log is therefore the source of truth for any future catalog
    decisions after a refresh; the active script slice has no catalog rows.
    """
    for event in sorted(events, key=lambda item: (item.occurred_at, item.sequence)):
        payload = event.payload or {}
        proposal_id = str(payload.get("proposal_id") or payload.get("proposalId") or "")
        if event.kind == "runtime.proposal.selected" and proposal_id:
            for proposal in runtime_proposals:
                proposal["selected"] = _proposal_matches(proposal, proposal_id)
        if event.kind in {"workflow.approved", "editorial.resolution.approved"}:
            selected = proposal_id or "cut-sc47"
            for proposal in runtime_proposals:
                proposal["selected"] = _proposal_matches(proposal, selected)

        variant_id = str(payload.get("variant_id") or payload.get("variantId") or "")
        if not variant_id:
            continue
        if event.kind == "delivery.conflict.resolved":
            for conflict in delivery_conflicts:
                linked_variant = next(
                    (item for item in delivery_variants if str(item.get("id", "")) == str(conflict.get("variant_id", ""))),
                    None,
                )
                if _variant_matches(conflict, variant_id) or (linked_variant is not None and _variant_matches(linked_variant, variant_id)):
                    conflict["resolved"] = 1
            for variant in delivery_variants:
                if _variant_matches(variant, variant_id):
                    variant["status"] = "ready"
        elif event.kind in {"workflow.delivered", "delivery.variant.approved"}:
            for variant in delivery_variants:
                if _variant_matches(variant, variant_id):
                    variant["status"] = "approved"


def _proposal_matches(row: Dict[str, Any], value: str) -> bool:
    normalized = value.lower().replace("_", "-").replace(" ", "-")
    row_id = str(row.get("id", "")).lower()
    label = str(row.get("label", "")).lower().replace("_", "-").replace(" ", "-")
    return normalized in {row_id, label} or (normalized == "cut-sc47" and "cut-sc-47" in label)


def _variant_matches(row: Dict[str, Any], value: str) -> bool:
    normalized = value.lower().replace("variant-", "")
    normalized = {
        "netflix-us": "stream-us",
    }.get(normalized, normalized)
    row_id = str(row.get("id", "")).lower()
    platform = str(row.get("platform", "")).lower()
    territory = str(row.get("territory", "")).lower()
    slug = f"{platform}-{territory}"
    return normalized in {row_id, slug} or row_id.endswith(normalized)


@router.get("/pipeline/stages", response_model=List[PipelineStageDefinition])
def list_pipeline_stages() -> List[PipelineStageDefinition]:
    return _service().list_pipeline_stages()


@router.get("/graph/nodes", response_model=List[GraphNode])
def list_graph_nodes() -> List[GraphNode]:
    return _service().list_graph_nodes()


@router.get("/graph/edges", response_model=List[GraphEdge])
def list_graph_edges() -> List[GraphEdge]:
    return _service().list_graph_edges()


def _find_graph_node(reference: Optional[str], nodes: List[GraphNode]) -> Optional[GraphNode]:
    if not reference:
        return None
    value = str(reference)
    # The browser's normalized memory graph uses stable slugs such as
    # `scene-47`; ClickHouse/FastAPI rows use UUIDs. Accept both forms so a
    # beat created from the inspector can keep its parent across transports.
    slug_number = value.removeprefix("scene-").removeprefix("SC ").strip()
    for node in nodes:
        if str(node.id) == value or (
            node.kind == GraphNodeKind.scene
            and node.scene_number is not None
            and node.scene_number.lower() in {value.lower(), slug_number.lower()}
        ):
            return node
    return None


def _crud_provenance(actor: str, runtime_mode: str, operation: str) -> Provenance:
    normalized = "simulation" if runtime_mode == "simulated" else runtime_mode
    return Provenance(
        source="computed",
        transport="repository",
        adapter="node-crud",
        runtime_mode=normalized,
        requested_by=actor,
        tool_name=operation,
    )


def _active_workflow_id() -> Optional[UUID]:
    workflows = _service().list_workflows()
    return workflows[0].id if workflows else None


def _append_node_event(kind: str, actor: str, payload: Dict[str, Any], runtime_mode: str) -> Optional[WorkflowEvent]:
    workflow_id = _active_workflow_id()
    if workflow_id is None:
        return None
    return _service().append_workflow_event(workflow_id, kind, actor, payload, runtime_mode, actor)


def _validate_node_timing(start: int, end: int) -> None:
    if end <= start:
        _conflict("node.invalid_timing", "end time must be greater than start time", start_seconds=start, end_seconds=end)


@router.post("/graph/nodes", response_model=GraphNode, status_code=201)
def create_graph_node(request: GraphNodeCreateRequest) -> GraphNode:
    """Create a scene or timed child beat and append a graph audit event."""
    _validate_node_timing(request.start_seconds, request.end_seconds)
    service = _service()
    existing = service.list_graph_nodes()
    kind = GraphNodeKind(request.kind)
    scene_nodes = [node for node in existing if node.kind == GraphNodeKind.scene]
    sequence = max((node.sequence for node in existing), default=0) + 1

    parent: Optional[GraphNode] = None
    if kind == GraphNodeKind.scene:
        scene_number = (request.scene_number or "").strip() or str(max((int(node.scene_number or 0) for node in scene_nodes), default=41) + 1)
        if any(node.scene_number == scene_number for node in scene_nodes):
            _conflict("node.duplicate_scene", "scene number already exists", scene_number=scene_number)
        beat_number = None
        parent_scene_id = None
        status = "pending"
    else:
        parent = _find_graph_node(request.parent_scene_id, existing)
        if parent is None or parent.kind != GraphNodeKind.scene:
            _conflict("node.parent_required", "a beat must have an existing parent scene")
        _validate_node_timing(request.start_seconds, request.end_seconds)
        if request.start_seconds < (parent.start_seconds or 0) or request.end_seconds > (parent.end_seconds or request.end_seconds):
            _conflict("node.beat_outside_scene", "beat timing must fit inside its parent scene", parent_scene=parent.scene_number)
        sibling_beats = [node for node in existing if node.kind == GraphNodeKind.beat and node.parent_scene_id == str(parent.id)]
        beat_number = request.beat_number or (max((node.beat_number or 0 for node in sibling_beats), default=0) + 1)
        if any((node.beat_number or 0) == beat_number for node in sibling_beats):
            _conflict("node.duplicate_beat", "beat number already exists in this scene", beat_number=beat_number)
        scene_number = parent.scene_number
        parent_scene_id = str(parent.id)
        status = parent.status

    source_node = next((node for node in existing if node.kind == GraphNodeKind.script), None)
    node = GraphNode(
        id=UUID(str(uuid4())),
        kind=kind,
        label=request.heading,
        sequence=sequence,
        stage_name="Script",
        status=status,
        film_id=source_node.film_id if source_node else "demo-feature",
        revision_id=source_node.revision_id if source_node else "rev-05",
        scene_number=scene_number,
        beat_number=beat_number,
        parent_scene_id=parent_scene_id,
        heading=request.heading,
        script_text=request.script_text,
        narration_text=request.narration_text or None,
        start_seconds=request.start_seconds,
        end_seconds=request.end_seconds,
        duration_seconds=request.end_seconds - request.start_seconds,
        metadata={"role": "scene" if kind == GraphNodeKind.scene else "beat", "dataset": "LOCAL DEMO", **({"child_count": 0} if kind == GraphNodeKind.scene else {"parent_scene": scene_number})},
        provenance=_crud_provenance(request.actor, request.runtime_mode, "graph.node.created"),
    )
    try:
        created = service.create_graph_node(node)
    except ValueError as exc:
        _conflict("node.create_failed", str(exc))
    _append_node_event("graph.node.created", request.actor, {"node_id": str(created.id), "kind": created.kind.value, "scene_number": created.scene_number, "beat_number": created.beat_number}, request.runtime_mode)
    return created


@router.patch("/graph/nodes/{node_id}", response_model=GraphNode)
def update_graph_node(node_id: UUID, request: GraphNodeUpdateRequest) -> GraphNode:
    """Update script text, narration, or timing while retaining node identity."""
    service = _service()
    current = next((node for node in service.list_graph_nodes() if node.id == node_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail={"error_code": "node.not_found", "message": "graph node not found"})
    if current.kind not in {GraphNodeKind.scene, GraphNodeKind.beat}:
        _conflict("node.immutable", "only scene and beat nodes can be edited")
    start = request.start_seconds if request.start_seconds is not None else current.start_seconds
    end = request.end_seconds if request.end_seconds is not None else current.end_seconds
    if start is None or end is None:
        _conflict("node.invalid_timing", "editable nodes require start and end times")
    _validate_node_timing(start, end)
    if current.kind == GraphNodeKind.beat and current.parent_scene_id:
        parent = next((node for node in service.list_graph_nodes() if str(node.id) == current.parent_scene_id), None)
        if parent and (start < (parent.start_seconds or 0) or end > (parent.end_seconds or end)):
            _conflict("node.beat_outside_scene", "beat timing must fit inside its parent scene", parent_scene=parent.scene_number)
    if current.kind == GraphNodeKind.scene:
        children = [node for node in service.list_graph_nodes() if node.kind == GraphNodeKind.beat and node.parent_scene_id == str(current.id)]
        if any((child.start_seconds or 0) < start or (child.end_seconds or 0) > end for child in children):
            _conflict("node.scene_timing_breaks_children", "scene timing must contain all child beats")
    next_narration = current.narration_text
    if request.narration_text is not None:
        next_narration = request.narration_text.strip() or None
    updated = current.model_copy(update={
        "label": request.heading if request.heading is not None else current.label,
        "heading": request.heading if request.heading is not None else current.heading,
        "script_text": request.script_text if request.script_text is not None else current.script_text,
        "narration_text": next_narration,
        "start_seconds": start,
        "end_seconds": end,
        "duration_seconds": end - start,
        "provenance": _crud_provenance(request.actor, request.runtime_mode, "graph.node.updated"),
    })
    try:
        saved = service.update_graph_node(updated)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "node.not_found", "message": str(exc)}) from exc
    _append_node_event("graph.node.updated", request.actor, {"node_id": str(saved.id), "kind": saved.kind.value}, request.runtime_mode)
    return saved


@router.delete("/graph/nodes/{node_id}")
def delete_graph_node(node_id: UUID, actor: str = "editorial", runtime_mode: str = "simulation"):
    """Delete a scene/beat and remove scene children and connected edges."""
    service = _service()
    current = next((node for node in service.list_graph_nodes() if node.id == node_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail={"error_code": "node.not_found", "message": "graph node not found"})
    if current.kind not in {GraphNodeKind.scene, GraphNodeKind.beat}:
        _conflict("node.immutable", "the revision source cannot be deleted")
    deleted_ids = service.delete_graph_node(node_id)
    _append_node_event("graph.node.deleted", actor, {"node_id": str(node_id), "deleted_ids": ",".join(str(item) for item in deleted_ids)}, runtime_mode)
    return {"deleted_ids": [str(item) for item in deleted_ids], "provenance": _crud_provenance(actor, runtime_mode, "graph.node.deleted")}


@router.get("/nodes/{node_id}/impact")
def node_impact(node_id: str):
    """Return a node's upstream lineage and connected impact neighborhood."""
    try:
        parsed_id = UUID(node_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error_code": "node.invalid_id", "message": "node_id must be a UUID"}) from exc
    service = _service()
    impact_nodes = service.get_node_impact(parsed_id)
    lineage_nodes = service.get_lineage(parsed_id)
    if not impact_nodes and not lineage_nodes:
        raise HTTPException(status_code=404, detail="graph node not found")
    return {
        "node_id": node_id,
        "impact_nodes": impact_nodes,
        "lineage": lineage_nodes,
        "provenance": {
            "source": service.last_source,
            "attempted_source": "clickhouse_mcp" if service.mcp_client is not None and service.graph_query_mode != "direct" else service.last_source,
            "fallback": service.last_source == "direct_clickhouse",
            "error": service.last_error,
        },
    }


@router.get("/graph/contracts", response_model=GraphContractSummary)
def graph_contract() -> GraphContractSummary:
    return _service().graph_contract()


@router.get("/workflows", response_model=List[Workflow])
def list_workflows() -> List[Workflow]:
    return _service().list_workflows()


@router.post("/workflows", response_model=Workflow, status_code=201)
def create_workflow(request: WorkflowCreateRequest) -> Workflow:
    pipeline_stage_names = [stage.name for stage in _service().list_pipeline_stages()]
    active_stage = request.active_stage or pipeline_stage_names[0]
    workflow = _service().create_workflow(request.name, active_stage, request.requested_by, request.runtime_mode, pipeline_stage_names)
    _service().append_workflow_event(
        workflow.id,
        "workflow.started",
        request.requested_by,
        {"stage": active_stage, "pipeline": "CLIO"},
        request.runtime_mode,
        request.requested_by,
    )
    _service().append_workflow_event(
        workflow.id,
        "workflow.approval_requested",
        "system",
        {"stage": active_stage, "status": "pending"},
        request.runtime_mode,
        request.requested_by,
    )
    return _repo().get_workflow(workflow.id) or workflow


@router.get("/workflows/{workflow_id}", response_model=Workflow)
def get_workflow(workflow_id: UUID) -> Workflow:
    workflow = _service().get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return workflow


@router.get("/workflows/{workflow_id}/events", response_model=List[WorkflowEvent])
def list_workflow_events(workflow_id: UUID) -> List[WorkflowEvent]:
    return _service().list_workflow_events(workflow_id)


@router.post("/workflows/{workflow_id}/events", response_model=WorkflowEvent, status_code=201)
def append_workflow_event(workflow_id: UUID, request: WorkflowEventCreateRequest) -> WorkflowEvent:
    workflow = _require_workflow(workflow_id)
    _validate_workflow_append(workflow, request.kind, request.payload)
    return _service().append_workflow_event(workflow_id, request.kind, request.actor, request.payload, request.runtime_mode, request.actor)


@router.post("/workflows/{workflow_id}/approval", response_model=WorkflowEvent, status_code=201)
def approve_workflow(workflow_id: UUID, request: WorkflowApprovalRequest) -> WorkflowEvent:
    workflow = _require_workflow(workflow_id)
    _validate_workflow_append(workflow, "workflow.approved" if request.approved else "workflow.rejected", {"reason": request.reason})
    event_kind = "workflow.approved" if request.approved else "workflow.rejected"
    payload = {"reason": request.reason, "decision": "approved" if request.approved else "rejected"}
    return _service().append_workflow_event(workflow_id, event_kind, request.actor, payload, request.runtime_mode, request.actor)


@router.get("/workflows/{workflow_id}/stream")
def stream_workflow_events(workflow_id: UUID) -> StreamingResponse:
    events = _service().list_workflow_events(workflow_id)

    def event_source():
        for event in events:
            yield "event: workflow.%s\n" % event.kind
            yield "data: %s\n\n" % event.model_dump_json()
        yield "event: workflow.done\n"
        yield 'data: {"type":"done"}\n\n'

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.get("/agent-runs", response_model=List[AgentRun])
def list_agent_runs() -> List[AgentRun]:
    return _service().list_agent_runs()


@router.post("/agent-runs", response_model=AgentRun, status_code=201)
def create_agent_run(request: AgentRunCreateRequest) -> AgentRun:
    if _service().get_workflow(request.workflow_id) is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    prompt = request.prompt
    if request.action:
        marker = f"[{request.action.upper()} NODE]"
        if marker not in prompt.upper():
            prompt = f"{marker} {prompt}"
    if request.focus_node:
        prompt = f"[FOCUS:{request.focus_node}] {prompt}"
    run = _service().create_agent_run(request.workflow_id, prompt, request.stage_name, request.model_name, request.runtime_mode)
    _service().append_agent_event(
        run.id,
        AgentEventKind.started,
        f"{request.runtime_mode}: agent run started",
        {"prompt": prompt, "stage": request.stage_name, "action": request.action, "focus_node": request.focus_node, "runtime_mode": request.runtime_mode},
        request.runtime_mode,
    )
    return _service().get_agent_run(run.id) or run


@router.get("/agent-runs/{run_id}", response_model=AgentRun)
def get_agent_run(run_id: UUID) -> AgentRun:
    run = _service().get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="agent run not found")
    return run


@router.get("/agent-runs/{run_id}/events", response_model=List[AgentEvent])
def list_agent_events(run_id: UUID) -> List[AgentEvent]:
    return _service().list_agent_events(run_id)


@router.get("/agent-runs/{run_id}/stream")
async def stream_agent_run(run_id: UUID) -> StreamingResponse:
    """Stream persisted events and append newly emitted provider events."""
    service = _service()
    run = service.get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="agent run not found")

    provider = provider_for(
        run.runtime_mode,
        api_key=os.getenv("GEMINI_API_KEY"),
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION"),
    )

    async def event_source():
        existing = service.list_agent_events(run_id)
        for event in existing:
            yield "event: agent.%s\n" % event.kind.value
            yield "data: %s\n\n" % event.model_dump_json()
        if len(existing) <= 1:
            try:
                context = {
                    "run_id": str(run_id),
                    "stage_name": run.stage_name,
                    "prompt": run.prompt,
                    "graph_nodes": [node.model_dump(mode="json") for node in service.list_graph_nodes()],
                    "graph_edges": [edge.model_dump(mode="json") for edge in service.list_graph_edges()],
                    "node_count": len(service.list_graph_nodes()),
                }
                async for event in provider.start_run(context):
                    persisted = service.append_agent_event(
                        event.run_id,
                        event.kind,
                        event.message,
                        event.payload,
                        event.provenance.runtime_mode,
                    )
                    yield "event: agent.%s\n" % persisted.kind.value
                    yield "data: %s\n\n" % persisted.model_dump_json()
            except Exception as exc:
                failed = service.append_agent_event(
                    run_id,
                    AgentEventKind.failed,
                    "agent provider unavailable",
                    {"error": str(exc)},
                    run.runtime_mode,
                )
                yield "event: agent.failed\n"
                yield "data: %s\n\n" % failed.model_dump_json()
        yield "event: agent.done\n"
        yield 'data: {"type":"done"}\n\n'

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/delivery", response_model=DeliveryRecord, status_code=201)
def create_delivery(request: DeliveryCreateRequest) -> DeliveryRecord:
    workflow = _require_workflow(request.workflow_id)
    _validate_delivery_request(workflow, request.status)
    stage_name = request.stage_name or workflow.active_stage or "Delivery"
    record = _service().create_delivery_record(request.workflow_id, stage_name, request.destination, request.artifact_uri, request.runtime_mode, request.status)
    if request.status == DeliveryStatus.delivered:
        _service().append_workflow_event(
            request.workflow_id,
            "workflow.delivered",
            "system",
            {"stage": stage_name, "destination": request.destination, "artifact_uri": request.artifact_uri},
            request.runtime_mode,
            "system",
        )
    else:
        _service().append_workflow_event(
            request.workflow_id,
            "workflow.delivery_ready",
            "system",
            {"stage": stage_name, "destination": request.destination},
            request.runtime_mode,
            "system",
        )
    return record


@router.post("/delivery/compile", response_model=DeliveryRecord, status_code=201)
def compile_delivery(request: DeliveryCreateRequest) -> DeliveryRecord:
    return create_delivery(request.model_copy(update={"status": DeliveryStatus.ready}))


@router.post("/delivery/approve", response_model=DeliveryRecord, status_code=201)
def approve_delivery(request: DeliveryCreateRequest) -> DeliveryRecord:
    workflow = _require_workflow(request.workflow_id)
    if workflow.approval_status != ApprovalStatus.approved:
        _conflict("delivery.not_approved", "delivery approval requires an approved workflow", workflow_id=str(workflow.id))
    return create_delivery(request.model_copy(update={"status": DeliveryStatus.delivered}))


@router.post("/delivery/{variant_id}/approve", status_code=201)
def approve_delivery_variant(variant_id: str, request: DeliveryVariantApprovalRequest):
    """Approve one compiled package and persist the delivery event.

    The variant compiler is intentionally deterministic; the final package
    decision remains a separate human-authored append-only event.
    """
    workflow = _require_workflow(request.workflow_id)
    if not request.approved:
        event = _service().append_workflow_event(
            workflow.id,
            "delivery.variant.held",
            request.actor,
            {"variant_id": variant_id, "decision": "hold"},
            request.runtime_mode,
            request.actor,
        )
        return {"variant_id": variant_id, "decision": "hold", "event": event, "provenance": event.provenance}
    if workflow.approval_status != ApprovalStatus.approved:
        _conflict("delivery.not_approved", "delivery approval requires an approved workflow", workflow_id=str(workflow.id))
    if workflow.delivery_status not in {DeliveryStatus.ready, DeliveryStatus.delivered}:
        _conflict("delivery.not_compiled", "compile the delivery matrix before approving a variant", workflow_id=str(workflow.id))
    record = _service().create_delivery_record(
        workflow.id,
        "Delivery",
        request.destination or variant_id,
        request.artifact_uri or f"local://filmgraph/{variant_id}.mov",
        request.runtime_mode,
        DeliveryStatus.delivered,
    )
    event = _service().append_workflow_event(
        workflow.id,
        "workflow.delivered",
        request.actor,
        {
            "variant_id": variant_id,
            "destination": request.destination or variant_id,
            "artifact_uri": request.artifact_uri or f"local://filmgraph/{variant_id}.mov",
        },
        request.runtime_mode,
        request.actor,
    )
    return {"variant_id": variant_id, "record": record, "event": event, "provenance": event.provenance}


@router.post("/delivery/{variant_id}/resolve", status_code=201)
def resolve_delivery_variant(variant_id: str, request: DeliveryVariantResolveRequest):
    """Record a human-owned compatibility conflict resolution."""
    workflow = _require_workflow(request.workflow_id)
    event = _service().append_workflow_event(
        workflow.id,
        "delivery.conflict.resolved",
        request.actor,
        {"variant_id": variant_id, "resolution": request.resolution},
        request.runtime_mode,
        request.actor,
    )
    return {"variant_id": variant_id, "resolution": request.resolution, "event": event, "provenance": event.provenance}


@router.get("/delivery", response_model=DeliverySummary)
def list_delivery() -> DeliverySummary:
    service = _service()
    workflows = {workflow.id: workflow for workflow in service.list_workflows()}
    ready: List[DeliveryItem] = []
    delivered: List[DeliveryItem] = []
    for record in service.list_delivery_records():
        item = DeliveryItem(
            workflow_id=record.workflow_id,
            workflow_name=workflows.get(record.workflow_id).name if workflows.get(record.workflow_id) else "unknown",
            stage_name=record.stage_name,
            status=record.status,
            destination=record.destination,
            artifact_uri=record.artifact_uri,
            provenance=record.provenance,
        )
        if record.status == DeliveryStatus.delivered:
            delivered.append(item)
        else:
            ready.append(item)
    return DeliverySummary(ready=ready, delivered=delivered)


@router.get("/workspace", response_model=WorkspaceSnapshot)
def workspace(
    film_id: Optional[str] = Query(default=None, alias="filmId"),
    revision_id: Optional[str] = Query(default=None, alias="revisionId"),
) -> WorkspaceSnapshot:
    return _build_workspace_snapshot(film_id, revision_id)


def _script_git_error(exc: ScriptGitError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"error_code": exc.code, "message": str(exc)})


@router.post("/script-git/load")
def script_git_load(request: ScriptGitLoadRequest):
    """Load a public/private GitHub screenplay and return its revision graph.

    Loading is read-only. Nothing enters the active map until the user calls
    ``script-git/apply`` explicitly.
    """
    try:
        settings = get_settings()
        return load_github_script(
            request.source,
            ref=request.ref,
            path=request.path,
            token=settings.github_token,
            history_limit=request.history_limit,
        )
    except ScriptGitError as exc:
        raise _script_git_error(exc) from exc


@router.post("/script-git/apply")
def script_git_apply(request: ScriptGitApplyRequest):
    """Apply a selected GitHub revision as the active screenplay graph."""
    workflow_id = request.workflow_id or _active_workflow_id()
    if workflow_id is None:
        raise HTTPException(status_code=404, detail={"error_code": "script_git.workflow_missing", "message": "no active script workflow"})
    try:
        settings = get_settings()
        document = load_github_script(
            request.source,
            ref=request.ref,
            path=request.path,
            token=settings.github_token,
            history_limit=12,
        )
    except ScriptGitError as exc:
        # A client-side document is only a resilience fallback for an offline
        # browser mirror. It is never used when the backend can reach GitHub.
        if not isinstance(request.document, dict) or not request.document.get("nodes"):
            raise _script_git_error(exc) from exc
        document = request.document

    try:
        nodes = [GraphNode.model_validate(item) for item in document.get("nodes", [])]
        edges = [GraphEdge.model_validate(item) for item in document.get("edges", [])]
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"error_code": "script_git.graph_invalid", "message": "GitHub screenplay could not be mapped to the script graph"}) from exc
    if not nodes or not any(node.kind == GraphNodeKind.scene for node in nodes):
        raise HTTPException(status_code=422, detail={"error_code": "script_git.no_scenes", "message": "The selected file did not contain a screenplay scene"})

    service = _service()
    service.replace_script_graph(nodes, edges)
    state = compact_git_state(document)
    event = service.append_workflow_event(
        workflow_id,
        "script.git.applied",
        request.actor,
        {
            "script_git": state,
            "revision_id": document.get("revision_id"),
            "content_hash": document.get("content_hash"),
            "scene_count": document.get("parsed", {}).get("scene_count", 0) if isinstance(document.get("parsed"), dict) else 0,
            "beat_count": document.get("parsed", {}).get("beat_count", 0) if isinstance(document.get("parsed"), dict) else 0,
        },
        request.runtime_mode,
        request.actor,
    )
    return {
        "script_git": state,
        "event": event,
        "graph_nodes": nodes,
        "graph_edges": edges,
        "provenance": event.provenance,
    }


@router.get("/runtime/proposals", response_model=List[RuntimeProposal])
def runtime_proposals() -> List[RuntimeProposal]:
    # Recommendations are read from the provider-shaped proposal catalog.  The
    # deterministic part here only projects a proposal onto the next pipeline
    # stage; it does not invent a new recommendation.
    catalog = _service().list_runtime_proposals()
    # The active local slice is script-only.  Do not synthesize a runtime
    # recommendation merely because a workflow exists; an empty catalog is a
    # truthful response until a later provider supplies one.
    if not catalog:
        return []
    proposals: List[RuntimeProposal] = []
    for workflow in _service().list_workflows():
        next_stage = workflow.active_stage or "Script"
        if workflow.stage_sequence and workflow.active_stage in workflow.stage_sequence:
            current_index = workflow.stage_sequence.index(workflow.active_stage)
            if current_index + 1 < len(workflow.stage_sequence):
                next_stage = workflow.stage_sequence[current_index + 1]
        recommended = next((item for item in catalog if bool(item.get("recommended"))), catalog[0] if catalog else {})
        rationale = str(recommended.get("rationale") or recommended.get("label") or "provider proposal")
        raw_confidence = recommended.get("confidence", 0.64)
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 0.64
        proposal_provenance = recommended.get("provenance")
        try:
            provenance = Provenance(**proposal_provenance) if isinstance(proposal_provenance, dict) else workflow.provenance
        except Exception:
            provenance = workflow.provenance
        proposals.append(
            RuntimeProposal(
                workflow_id=workflow.id,
                workflow_name=workflow.name,
                proposed_stage=next_stage,
                action="advance" if workflow.status == WorkflowStatus.running else "initiate",
                confidence=confidence,
                rationale=rationale,
                provenance=provenance,
            )
        )
    return proposals


@router.post("/runtime/proposals", status_code=201)
def select_runtime_proposal(request: RuntimeProposalSelectRequest):
    """Append a proposal-selection event; recommendation selection is not approval."""
    workflow = _require_workflow(request.workflow_id)
    event = _service().append_workflow_event(
        workflow.id,
        "runtime.proposal.selected",
        request.actor,
        {"proposal_id": request.proposal_id},
        request.runtime_mode,
        request.actor,
    )
    return {
        "workflow_id": str(workflow.id),
        "proposal_id": request.proposal_id,
        "event": event,
        "provenance": event.provenance,
    }


@router.get("/impact", response_model=ImpactSummary)
def impact() -> ImpactSummary:
    service = _service()
    workflows = service.list_workflows()
    nodes = service.list_graph_nodes()
    edges = service.list_graph_edges()
    completed_workflows = len([workflow for workflow in workflows if workflow.status == WorkflowStatus.complete])
    approved_workflows = len([workflow for workflow in workflows if workflow.approval_status == ApprovalStatus.approved])
    delivery_records = service.list_delivery_records()
    delivery_ready = len([record for record in delivery_records if record.status == DeliveryStatus.ready])
    delivery_count = len(delivery_records)
    possible_edges = max(len(nodes) * max(len(nodes) - 1, 1), 1)
    return ImpactSummary(
        stage_coverage=len(service.list_pipeline_stages()),
        completed_workflows=completed_workflows,
        approved_workflows=approved_workflows,
        delivery_ready=delivery_ready,
        delivery_count=delivery_count,
        graph_density=len(edges) / float(possible_edges),
    )


@router.get("/graph/impact", response_model=ImpactSummary)
def graph_impact() -> ImpactSummary:
    return impact()


@router.get("/runtime", response_model=RuntimeSummary)
def runtime() -> RuntimeSummary:
    settings = get_settings()
    storage_mode = _storage_mode()
    return RuntimeSummary(
        environment=settings.environment,
        storage_mode=storage_mode,
        runtime_mode=settings.agent_runtime_mode,
        mcp_enabled=settings.mcp_endpoint is not None or settings.mcp_command is not None,
        clickhouse_enabled=storage_mode == "clickhouse",
    )


@router.get("/editorial", response_model=EditorialSummary)
def editorial() -> EditorialSummary:
    service = _service()
    workflows = service.list_workflows()
    events_by_workflow = {workflow.id: service.list_workflow_events(workflow.id) for workflow in workflows}
    pending: List[EditorialItem] = []
    approved: List[EditorialItem] = []
    for workflow in workflows:
        item = EditorialItem(
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            active_stage=workflow.active_stage,
            approval_status=workflow.approval_status,
            last_event_kind=events_by_workflow.get(workflow.id, [])[-1].kind if events_by_workflow.get(workflow.id) else None,
            provenance=workflow.provenance,
        )
        if workflow.approval_status == ApprovalStatus.pending:
            pending.append(item)
        elif workflow.approval_status == ApprovalStatus.approved:
            approved.append(item)
    return EditorialSummary(pending_approvals=pending, approved_workflows=approved)


@router.post("/editorial/decision/{workflow_id}", response_model=WorkflowEvent, status_code=201)
def editorial_decision(workflow_id: UUID, request: WorkflowApprovalRequest) -> WorkflowEvent:
    return approve_workflow(workflow_id, request)


@router.post("/decisions/editorial", response_model=WorkflowEvent, status_code=201)
def editorial_decision_boundary(request: EditorialDecisionRequest) -> WorkflowEvent:
    """Typed browser-boundary alias for the append-only editorial decision."""
    workflow = _require_workflow(request.workflow_id)
    event_kind = "workflow.approved" if request.approved else "workflow.rejected"
    _validate_workflow_append(
        workflow,
        event_kind,
        {"proposal_id": request.proposal_id, "reason": request.reason},
    )
    return _service().append_workflow_event(
        workflow.id,
        event_kind,
        request.actor,
        {
            "proposal_id": request.proposal_id,
            "reason": request.reason,
            "decision": "approve" if request.approved else "hold",
        },
        request.runtime_mode,
        request.actor,
    )


@router.get("/provenance", response_model=ProvenanceSummary)
def provenance() -> ProvenanceSummary:
    return ProvenanceSummary(items=_repo().list_provenance())


@router.get("/provenance/{entity_type}/{entity_id}", response_model=ProvenanceItem)
def provenance_item(entity_type: str, entity_id: UUID) -> ProvenanceItem:
    for item in _repo().list_provenance():
        if item.entity_type == entity_type and item.entity_id == entity_id:
            return item
    raise HTTPException(status_code=404, detail="provenance item not found")


@router.get("/provenance/{delivery_id}")
def delivery_provenance(delivery_id: str):
    """Expose a compatibility provenance trace without adding graph nodes."""
    service = _service()
    records = service.list_delivery_records()
    record = next((item for item in records if str(item.id) == delivery_id or item.destination == delivery_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="delivery provenance not found")
    events = _service().list_workflow_events(record.workflow_id)
    return {
        "delivery_id": delivery_id,
        "record": record,
        "path": [
            {"step": "revision", "label": "V5 / SC 47", "source": service.last_source},
            {"step": "scene", "label": "SC 47 / SCRIPT", "source": "computed"},
            {"step": "decision", "label": "HUMAN REVIEW", "source": "computed"},
            {"step": "record", "label": delivery_id, "source": record.provenance.source},
        ],
        "workflow_events": events,
        "provenance": record.provenance,
    }


@router.get("/plan", response_model=PlanSummary)
def plan() -> PlanSummary:
    workspace_summary = _build_workspace_snapshot(None, None).workspace
    runtime_summary = runtime()
    return PlanSummary(
        pipeline_name=workspace_summary.pipeline_name,
        stage_count=workspace_summary.stage_count,
        node_count=workspace_summary.node_count,
        edge_count=workspace_summary.edge_count,
        workflow_count=workspace_summary.workflow_count,
        run_count=workspace_summary.run_count,
        delivery_count=workspace_summary.delivery_count,
        approval_count=workspace_summary.approval_count,
        runtime_mode=runtime_summary.runtime_mode,
        api_endpoints=[
            "GET /api/v1/pipeline/stages",
            "GET /api/v1/graph/nodes",
            "POST /api/v1/graph/nodes",
            "PATCH /api/v1/graph/nodes/{node_id}",
            "DELETE /api/v1/graph/nodes/{node_id}",
            "GET /api/v1/graph/edges",
            "GET /api/v1/nodes/{node_id}/impact",
            "GET /api/v1/graph/contracts",
            "GET /api/v1/workspace?filmId=demo-feature&revisionId=rev-05",
            "POST /api/v1/script-git/load",
            "POST /api/v1/script-git/apply",
            "GET /api/v1/impact",
            "GET /api/v1/graph/impact",
            "GET /api/v1/runtime",
            "GET /api/v1/runtime/proposals",
            "POST /api/v1/runtime/proposals",
            "GET /api/v1/editorial",
            "POST /api/v1/editorial/decision/{workflow_id}",
            "POST /api/v1/decisions/editorial",
            "GET /api/v1/delivery",
            "POST /api/v1/delivery/compile",
            "POST /api/v1/delivery/approve",
            "POST /api/v1/delivery/{variant_id}/approve",
            "POST /api/v1/delivery/{variant_id}/resolve",
            "GET /api/v1/provenance",
            "GET /api/v1/provenance/{entity_type}/{entity_id}",
            "GET /api/v1/provenance/{delivery_id}",
            "GET /api/v1/workflows",
            "POST /api/v1/workflows",
            "GET /api/v1/workflows/{workflow_id}",
            "GET /api/v1/workflows/{workflow_id}/events",
            "POST /api/v1/workflows/{workflow_id}/events",
            "POST /api/v1/workflows/{workflow_id}/approval",
            "GET /api/v1/workflows/{workflow_id}/stream",
            "GET /api/v1/agent-runs",
            "POST /api/v1/agent-runs",
            "GET /api/v1/agent-runs/{run_id}",
            "GET /api/v1/agent-runs/{run_id}/events",
            "GET /api/v1/agent-runs/{run_id}/stream",
            "POST /api/v1/delivery",
        ],
    )


def create_app() -> FastAPI:
    app = FastAPI(title="CLIO API", version="0.2.0")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        settings = get_settings()
        storage_mode = _storage_mode()
        return HealthResponse(status="ok", environment=settings.environment, storage_mode=storage_mode, runtime_mode=settings.agent_runtime_mode)

    @app.get("/api/health", response_model=HealthResponse)
    def api_health() -> HealthResponse:
        return health()

    app.include_router(router)
    return app


app = create_app()
