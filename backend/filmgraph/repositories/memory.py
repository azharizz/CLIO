from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Dict, List, Optional
from uuid import UUID

from filmgraph.models import (
    AgentEvent,
    AgentEventKind,
    AgentRun,
    ApprovalStatus,
    DeliveryRecord,
    DeliveryStatus,
    GraphContractSummary,
    GraphEdge,
    GraphNode,
    PipelineStageDefinition,
    Provenance,
    ProvenanceItem,
    Workflow,
    WorkflowEvent,
    WorkflowStatus,
)


class MemoryFilmGraphRepository:
    def __init__(
        self,
        pipeline_stages: List[PipelineStageDefinition],
        graph_nodes: List[GraphNode],
        graph_edges: List[GraphEdge],
        runtime_proposals: Optional[List[Dict[str, Any]]] = None,
        delivery_variants: Optional[List[Dict[str, Any]]] = None,
        delivery_conflicts: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._pipeline_stages: List[PipelineStageDefinition] = list(pipeline_stages)
        self._graph_nodes: Dict[UUID, GraphNode] = {node.id: node for node in graph_nodes}
        self._graph_edges: List[GraphEdge] = list(graph_edges)
        self._runtime_proposals: List[Dict[str, Any]] = deepcopy(runtime_proposals or [])
        self._delivery_variants: List[Dict[str, Any]] = deepcopy(delivery_variants or [])
        self._delivery_conflicts: List[Dict[str, Any]] = deepcopy(delivery_conflicts or [])
        self._workflows: Dict[UUID, Workflow] = {}
        self._workflow_events = defaultdict(list)
        self._agent_runs: Dict[UUID, AgentRun] = {}
        self._agent_events = defaultdict(list)
        self._delivery_records: Dict[UUID, DeliveryRecord] = {}

    def bootstrap(self) -> None:
        return None

    def list_pipeline_stages(self) -> List[PipelineStageDefinition]:
        return [deepcopy(stage) for stage in self._pipeline_stages]

    def list_graph_nodes(self) -> List[GraphNode]:
        return [deepcopy(node) for node in self._graph_nodes.values()]

    def list_graph_edges(self) -> List[GraphEdge]:
        return [deepcopy(edge) for edge in self._graph_edges]

    def create_graph_node(self, node: GraphNode, edges: Optional[List[GraphEdge]] = None) -> GraphNode:
        if node.id in self._graph_nodes:
            raise ValueError("graph node already exists")
        self._graph_nodes[node.id] = deepcopy(node)
        for edge in edges or []:
            if edge.source_id in self._graph_nodes and edge.target_id in self._graph_nodes:
                self._graph_edges.append(deepcopy(edge))
        # Keep the parent scene's denormalized child count truthful after a
        # beat is added.  The count is only a display aid; the beat rows and
        # contains edges remain the source of truth.
        if node.kind.value == "beat" and node.parent_scene_id:
            try:
                parent_id = UUID(str(node.parent_scene_id))
            except ValueError:
                parent_id = None
            parent = self._graph_nodes.get(parent_id) if parent_id is not None else None
            if parent is not None:
                count = sum(
                    1
                    for item in self._graph_nodes.values()
                    if item.kind.value == "beat" and item.parent_scene_id == str(parent.id)
                )
                parent.metadata["child_count"] = count
        return deepcopy(node)

    def update_graph_node(self, node: GraphNode) -> GraphNode:
        if node.id not in self._graph_nodes:
            raise KeyError("graph node not found")
        self._graph_nodes[node.id] = deepcopy(node)
        return deepcopy(node)

    def delete_graph_node(self, node_id: UUID) -> List[UUID]:
        if node_id not in self._graph_nodes:
            return []
        deleted: set[UUID] = {node_id}
        parent_ids: set[UUID] = set()
        # Removing a parent scene also removes its timed children; orphaned
        # beats would make later impact answers misleading.
        changed = True
        while changed:
            changed = False
            for candidate in self._graph_nodes.values():
                if candidate.id in deleted:
                    continue
                if candidate.parent_scene_id and candidate.parent_scene_id in {str(item) for item in deleted}:
                    deleted.add(candidate.id)
                    changed = True
        for item in deleted:
            candidate = self._graph_nodes.get(item)
            if candidate is None or candidate.kind.value != "beat" or not candidate.parent_scene_id:
                continue
            try:
                parent_ids.add(UUID(candidate.parent_scene_id))
            except ValueError:
                continue
        for item in deleted:
            self._graph_nodes.pop(item, None)
        self._graph_edges = [edge for edge in self._graph_edges if edge.source_id not in deleted and edge.target_id not in deleted]
        for parent_id in parent_ids:
            parent = self._graph_nodes.get(parent_id)
            if parent is not None:
                parent.metadata["child_count"] = sum(
                    1
                    for item in self._graph_nodes.values()
                    if item.kind.value == "beat" and item.parent_scene_id == str(parent_id)
                )
        return list(deleted)

    def replace_script_graph(self, nodes: List[GraphNode], edges: List[GraphEdge]) -> None:
        """Replace only screenplay rows; preserve workflows and audit events."""
        script_kinds = {"script", "scene", "beat", "story_beat"}
        self._graph_nodes = {
            node_id: node
            for node_id, node in self._graph_nodes.items()
            if node.kind.value not in script_kinds
        }
        for node in nodes:
            self._graph_nodes[node.id] = deepcopy(node)
        retained_ids = set(self._graph_nodes)
        self._graph_edges = [
            edge
            for edge in self._graph_edges
            if edge.source_id in retained_ids and edge.target_id in retained_ids
        ]
        self._graph_edges.extend(
            deepcopy(edge)
            for edge in edges
            if edge.source_id in retained_ids and edge.target_id in retained_ids
        )

    def list_workflows(self) -> List[Workflow]:
        return [deepcopy(workflow) for workflow in self._workflows.values()]

    def get_workflow(self, workflow_id: UUID) -> Optional[Workflow]:
        workflow = self._workflows.get(workflow_id)
        return deepcopy(workflow) if workflow else None

    def create_workflow(self, workflow: Workflow) -> Workflow:
        self._workflows[workflow.id] = deepcopy(workflow)
        return deepcopy(workflow)

    def append_workflow_event(self, event: WorkflowEvent) -> WorkflowEvent:
        event.sequence = len(self._workflow_events[event.workflow_id]) + 1
        self._workflow_events[event.workflow_id].append(deepcopy(event))
        workflow = self._workflows.get(event.workflow_id)
        if workflow is not None:
            workflow.updated_at = event.occurred_at
            self._apply_workflow_transition(workflow, event)
        return deepcopy(event)

    def list_workflow_events(self, workflow_id: UUID) -> List[WorkflowEvent]:
        return [deepcopy(event) for event in self._workflow_events[workflow_id]]

    def list_agent_runs(self) -> List[AgentRun]:
        return [deepcopy(run) for run in self._agent_runs.values()]

    def get_agent_run(self, run_id: UUID) -> Optional[AgentRun]:
        run = self._agent_runs.get(run_id)
        return deepcopy(run) if run else None

    def create_agent_run(self, run: AgentRun) -> AgentRun:
        self._agent_runs[run.id] = deepcopy(run)
        return deepcopy(run)

    def append_agent_event(self, event: AgentEvent) -> AgentEvent:
        event.sequence = len(self._agent_events[event.run_id]) + 1
        self._agent_events[event.run_id].append(deepcopy(event))
        run = self._agent_runs.get(event.run_id)
        if run is not None:
            run.updated_at = event.occurred_at
            if event.kind == AgentEventKind.started:
                run.status = WorkflowStatus.running
            elif event.kind == AgentEventKind.completed:
                run.status = WorkflowStatus.complete
                run.summary = event.message
            elif event.kind == AgentEventKind.failed:
                run.status = WorkflowStatus.failed
        return deepcopy(event)

    def list_agent_events(self, run_id: UUID) -> List[AgentEvent]:
        return [deepcopy(event) for event in self._agent_events[run_id]]

    def list_delivery_records(self) -> List[DeliveryRecord]:
        return [deepcopy(record) for record in self._delivery_records.values()]

    def list_runtime_proposals(self) -> List[Dict[str, Any]]:
        return deepcopy(self._runtime_proposals)

    def list_delivery_variants(self) -> List[Dict[str, Any]]:
        return deepcopy(self._delivery_variants)

    def list_delivery_conflicts(self) -> List[Dict[str, Any]]:
        return deepcopy(self._delivery_conflicts)

    def create_delivery_record(self, record: DeliveryRecord) -> DeliveryRecord:
        self._delivery_records[record.id] = deepcopy(record)
        workflow = self._workflows.get(record.workflow_id)
        if workflow is not None:
            workflow.delivery_status = record.status
            workflow.updated_at = record.delivered_at
            if record.status == DeliveryStatus.delivered:
                workflow.status = WorkflowStatus.complete
        return deepcopy(record)

    def list_provenance(self) -> List[ProvenanceItem]:
        items: List[ProvenanceItem] = []
        for stage in self._pipeline_stages:
            items.append(ProvenanceItem(entity_type="pipeline_stage", entity_id=stage.id, provenance=Provenance()))
        for node in self._graph_nodes.values():
            items.append(ProvenanceItem(entity_type="graph_node", entity_id=node.id, provenance=deepcopy(node.provenance)))
        for edge in self._graph_edges:
            items.append(ProvenanceItem(entity_type="graph_edge", entity_id=edge.id, provenance=deepcopy(edge.provenance)))
        for workflow in self._workflows.values():
            items.append(ProvenanceItem(entity_type="workflow", entity_id=workflow.id, provenance=deepcopy(workflow.provenance)))
        for run in self._agent_runs.values():
            items.append(ProvenanceItem(entity_type="agent_run", entity_id=run.id, provenance=deepcopy(run.provenance)))
        for record in self._delivery_records.values():
            items.append(ProvenanceItem(entity_type="delivery_record", entity_id=record.id, provenance=deepcopy(record.provenance)))
        for entity_type, rows in (
            ("runtime_proposal", self._runtime_proposals),
            ("delivery_variant", self._delivery_variants),
            ("delivery_conflict", self._delivery_conflicts),
        ):
            for row in rows:
                try:
                    entity_id = UUID(str(row["id"]))
                except (KeyError, ValueError):
                    continue
                value = row.get("provenance")
                provenance = Provenance(**value) if isinstance(value, dict) else Provenance()
                items.append(ProvenanceItem(entity_type=entity_type, entity_id=entity_id, provenance=provenance))
        return items

    def graph_contract(self) -> GraphContractSummary:
        return GraphContractSummary(
            node_kinds=[node.kind for node in self._graph_nodes.values()],
            edge_relations=sorted({edge.relation for edge in self._graph_edges}),
            stage_names=[stage.name for stage in self._pipeline_stages],
        )

    def get_node_impact(self, node_id: UUID) -> List[GraphNode]:
        """Return the connected impact neighborhood for a graph node."""
        adjacency: Dict[UUID, List[UUID]] = defaultdict(list)
        for edge in self._graph_edges:
            adjacency[edge.source_id].append(edge.target_id)
            adjacency[edge.target_id].append(edge.source_id)
        seen: set[UUID] = set()
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            queue.extend(adjacency.get(current, []))
        return [deepcopy(self._graph_nodes[item]) for item in seen if item in self._graph_nodes]

    def get_lineage(self, node_id: UUID) -> List[GraphNode]:
        parents: Dict[UUID, List[UUID]] = defaultdict(list)
        for edge in self._graph_edges:
            parents[edge.target_id].append(edge.source_id)
        seen: set[UUID] = set()
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            queue.extend(parents.get(current, []))
        return [deepcopy(self._graph_nodes[item]) for item in seen if item in self._graph_nodes]

    def _apply_workflow_transition(self, workflow: Workflow, event: WorkflowEvent) -> None:
        kind = event.kind
        payload = event.payload
        if kind == "workflow.started":
            workflow.status = WorkflowStatus.running
            workflow.active_stage = payload.get("stage") or workflow.active_stage
        elif kind == "workflow.stage_advanced":
            workflow.active_stage = payload.get("stage") or workflow.active_stage
        elif kind == "workflow.completed":
            workflow.status = WorkflowStatus.complete
        elif kind == "workflow.failed":
            workflow.status = WorkflowStatus.failed
        elif kind == "workflow.approval_requested":
            workflow.approval_status = ApprovalStatus.pending
        elif kind == "workflow.approved":
            workflow.approval_status = ApprovalStatus.approved
        elif kind == "workflow.rejected":
            workflow.approval_status = ApprovalStatus.rejected
        elif kind == "workflow.delivery_ready":
            workflow.delivery_status = DeliveryStatus.ready
        elif kind == "workflow.delivered":
            workflow.delivery_status = DeliveryStatus.delivered
