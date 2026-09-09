from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol
from uuid import UUID

from filmgraph.models import (
    AgentEvent,
    AgentRun,
    DeliveryRecord,
    GraphContractSummary,
    GraphEdge,
    GraphNode,
    PipelineStageDefinition,
    ProvenanceItem,
    Workflow,
    WorkflowEvent,
)


class FilmGraphRepository(Protocol):
    def bootstrap(self) -> None:
        ...

    def list_pipeline_stages(self) -> List[PipelineStageDefinition]:
        ...

    def list_graph_nodes(self) -> List[GraphNode]:
        ...

    def list_graph_edges(self) -> List[GraphEdge]:
        ...

    def create_graph_node(self, node: GraphNode, edges: Optional[List[GraphEdge]] = None) -> GraphNode:
        ...

    def update_graph_node(self, node: GraphNode) -> GraphNode:
        ...

    def delete_graph_node(self, node_id: UUID) -> List[UUID]:
        ...

    def replace_script_graph(self, nodes: List[GraphNode], edges: List[GraphEdge]) -> None:
        """Replace the script/revision slice after a human Git apply."""
        ...

    def get_node_impact(self, node_id: UUID) -> List[GraphNode]:
        ...

    def get_lineage(self, node_id: UUID) -> List[GraphNode]:
        ...

    def get_workspace_snapshot(self, film_id: str, revision_id: str) -> Any:
        ...

    def list_workflows(self) -> List[Workflow]:
        ...

    def get_workflow(self, workflow_id: UUID) -> Optional[Workflow]:
        ...

    def create_workflow(self, workflow: Workflow) -> Workflow:
        ...

    def append_workflow_event(self, event: WorkflowEvent) -> WorkflowEvent:
        ...

    def list_workflow_events(self, workflow_id: UUID) -> List[WorkflowEvent]:
        ...

    def list_agent_runs(self) -> List[AgentRun]:
        ...

    def get_agent_run(self, run_id: UUID) -> Optional[AgentRun]:
        ...

    def create_agent_run(self, run: AgentRun) -> AgentRun:
        ...

    def append_agent_event(self, event: AgentEvent) -> AgentEvent:
        ...

    def list_agent_events(self, run_id: UUID) -> List[AgentEvent]:
        ...

    def list_delivery_records(self) -> List[DeliveryRecord]:
        ...

    # Read-side catalogs used by the unified runtime and delivery contexts.
    # They intentionally stay transport-neutral dictionaries so an MCP row and
    # a clickhouse-connect row can share the same boundary without inventing a
    # second set of browser-only models.
    def list_runtime_proposals(self) -> List[Dict[str, Any]]:
        ...

    def list_delivery_variants(self) -> List[Dict[str, Any]]:
        ...

    def list_delivery_conflicts(self) -> List[Dict[str, Any]]:
        ...

    def create_delivery_record(self, record: DeliveryRecord) -> DeliveryRecord:
        ...

    def list_provenance(self) -> List[ProvenanceItem]:
        ...

    def graph_contract(self) -> GraphContractSummary:
        ...


class GraphQueryPort(Protocol):
    """Read-side contract shared by MCP and direct ClickHouse adapters."""

    def get_workspace_snapshot(self, film_id: str, revision_id: str) -> Any:
        ...

    def get_node_impact(self, node_id: UUID) -> List[GraphNode]:
        ...

    def get_lineage(self, node_id: UUID) -> List[GraphNode]:
        ...

    # Public contract aliases mirror the browser-facing names in PRODUCT.md.
    def getWorkspaceSnapshot(self, film_id: str, revision_id: str) -> Any:
        ...

    def getNodeImpact(self, node_id: UUID) -> List[GraphNode]:
        ...

    def getLineage(self, node_id: UUID) -> List[GraphNode]:
        ...
