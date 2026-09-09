"""Read-only ClickHouse MCP seam with a direct repository fallback.

The application deliberately keeps MCP out of all mutations.  MCP clients are
small synchronous adapters because FastAPI's repository methods are sync; an
MCP server can be swapped in without changing the domain contract.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence
from uuid import UUID, uuid4

from filmgraph.graph_queries import recursive_impact_query, recursive_lineage_query
from filmgraph.models import (
    AgentEvent,
    AgentEventKind,
    AgentRun,
    DeliveryRecord,
    DeliveryStatus,
    GraphContractSummary,
    GraphEdge,
    GraphNode,
    GraphNodeKind,
    PipelineStageDefinition,
    Provenance,
    Workflow,
    WorkflowEvent,
    WorkflowStatus,
)
from filmgraph.repositories.base import FilmGraphRepository


class McpTransportError(RuntimeError):
    """Raised when a configured MCP transport cannot answer a read."""


@dataclass
class FakeMcpClient:
    """Deterministic contract-test client; it never writes external state."""

    responses: Dict[str, Any]
    calls: List[Dict[str, Any]]

    def __init__(self, responses: Optional[Dict[str, Any]] = None) -> None:
        self.responses = responses or {}
        self.calls = []

    def call_tool(self, tool_name: str, payload: Dict[str, Any]) -> Any:
        self.calls.append({"tool": tool_name, "payload": payload})
        if tool_name not in self.responses:
            raise McpTransportError(tool_name)
        result = self.responses[tool_name]
        if isinstance(result, Exception):
            raise result
        return result


class HttpMcpClient:
    """Minimal JSON/JSON-RPC-compatible MCP HTTP client.

    Different local MCP hosts use either `{tool, arguments}` or JSON-RPC
    envelopes.  The normalizer accepts both, while the payload explicitly
    marks the query read-only.
    """

    def __init__(self, endpoint: str, timeout_seconds: float = 1.2) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def call_tool(self, tool_name: str, payload: Dict[str, Any]) -> Any:
        body = json.dumps({"jsonrpc": "2.0", "id": str(uuid4()), "method": "tools/call", "params": {"name": tool_name, "arguments": payload}}).encode()
        request = urllib.request.Request(self.endpoint, data=body, method="POST", headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network-dependent
            raise McpTransportError(str(exc)) from exc
        if isinstance(decoded, dict) and decoded.get("error"):
            raise McpTransportError(str(decoded["error"]))
        if isinstance(decoded, dict) and "result" in decoded:
            decoded = decoded["result"]
        if isinstance(decoded, dict) and "structuredContent" in decoded:
            decoded = decoded["structuredContent"]
        if isinstance(decoded, dict) and "content" in decoded and len(decoded["content"]) == 1:
            content = decoded["content"][0]
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                try:
                    decoded = json.loads(content["text"])
                except json.JSONDecodeError:
                    pass
        return decoded


class CommandMcpClient:
    """Line-oriented command adapter for a local MCP bridge."""

    def __init__(self, command: str, timeout_seconds: float = 1.2) -> None:
        self.command = command
        self.timeout_seconds = timeout_seconds

    def call_tool(self, tool_name: str, payload: Dict[str, Any]) -> Any:
        request = json.dumps({"tool": tool_name, "arguments": payload})
        try:
            result = subprocess.run(shlex.split(self.command), input=request, text=True, capture_output=True, timeout=self.timeout_seconds, check=True)
            return json.loads(result.stdout)
        except Exception as exc:  # pragma: no cover - process-dependent
            raise McpTransportError(str(exc)) from exc


def build_mcp_client(endpoint: Optional[str], command: Optional[str]) -> Optional[Any]:
    if endpoint:
        return HttpMcpClient(endpoint)
    if command:
        return CommandMcpClient(command)
    return None


class McpFirstFilmGraphService:
    """Graph read port implementing MCP-first, repository-fallback semantics."""

    def __init__(self, repository: FilmGraphRepository, mcp_client: Optional[Any] = None, runtime_mode: str = "simulation", graph_query_mode: str = "auto") -> None:
        self.repository = repository
        self.mcp_client = mcp_client
        self.runtime_mode = "simulation" if runtime_mode == "simulated" else runtime_mode
        self.graph_query_mode = graph_query_mode
        self.last_source = "computed"
        self.last_error: Optional[str] = None

    def list_pipeline_stages(self) -> List[PipelineStageDefinition]:
        response = self._read("pipeline_stages", "SELECT * FROM pipeline_stages ORDER BY sequence, id", "filmgraph.list_pipeline_stages")
        if response is not None:
            try:
                return [PipelineStageDefinition(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid pipeline_stages MCP response"
        return self._fallback(self.repository.list_pipeline_stages())

    def list_graph_nodes(self) -> List[GraphNode]:
        response = self._read("graph_nodes", "SELECT * FROM graph_nodes ORDER BY sequence, label", "filmgraph.list_graph_nodes")
        if response is not None:
            try:
                return [GraphNode(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid graph_nodes MCP response"
        return self._fallback(self.repository.list_graph_nodes())

    def list_graph_edges(self) -> List[GraphEdge]:
        response = self._read("graph_edges", "SELECT * FROM graph_edges ORDER BY created_at, id", "filmgraph.list_graph_edges")
        if response is not None:
            try:
                return [GraphEdge(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid graph_edges MCP response"
        return self._fallback(self.repository.list_graph_edges())

    # Graph mutations intentionally bypass MCP.  MCP is a read-only query
    # accelerator; the repository is the authoritative write boundary.
    def create_graph_node(self, node: GraphNode) -> GraphNode:
        existing = self.repository.list_graph_nodes()
        edges: List[GraphEdge] = []
        if node.kind == GraphNodeKind.scene:
            scenes = sorted((item for item in existing if item.kind == GraphNodeKind.scene), key=lambda item: (item.sequence, str(item.id)))
            if scenes:
                previous = scenes[-1]
                edges.append(self._node_edge(previous.id, node.id, "follows", node.status, "backbone"))
        elif node.kind == GraphNodeKind.beat and node.parent_scene_id:
            try:
                parent_id = UUID(str(node.parent_scene_id))
            except ValueError:
                parent_id = None
            if parent_id is not None:
                edges.append(self._node_edge(parent_id, node.id, "contains", node.status, "beat"))
                siblings = sorted(
                    (item for item in existing if item.kind == GraphNodeKind.beat and item.parent_scene_id == str(parent_id)),
                    key=lambda item: (item.beat_number or 0, item.sequence, str(item.id)),
                )
                if siblings:
                    edges.append(self._node_edge(siblings[-1].id, node.id, "follows", node.status, "beat"))
        return self.repository.create_graph_node(node, edges)

    def update_graph_node(self, node: GraphNode) -> GraphNode:
        return self.repository.update_graph_node(node)

    def delete_graph_node(self, node_id: UUID) -> List[UUID]:
        return self.repository.delete_graph_node(node_id)

    def replace_script_graph(self, nodes: List[GraphNode], edges: List[GraphEdge]) -> None:
        """Persist a human-approved GitHub screenplay snapshot.

        MCP remains read-only; the repository is the sole mutation boundary.
        """
        self.repository.replace_script_graph(nodes, edges)

    def _node_edge(self, source_id: UUID, target_id: UUID, relation: str, status: str, kind: str) -> GraphEdge:
        return GraphEdge(
            id=uuid4(),
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            weight=1.0,
            confidence=0.98,
            metadata={"tone": status, "kind": kind, "dataset": "LOCAL DEMO"},
            provenance=self._mutation_provenance("node-crud", runtime_mode=self.runtime_mode, requested_by="editorial", tool_name=f"graph.node.{relation}"),
        )

    def get_node_impact(self, node_id: UUID) -> List[GraphNode]:
        """Read the connected impact neighborhood through the graph port."""
        response = self._read(
            "node_impact",
            recursive_impact_query(),
            "filmgraph.get_node_impact",
            {"node_id": str(node_id)},
        )
        if response is not None:
            try:
                return [GraphNode(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid node_impact MCP response"
        return self._fallback(self.repository.get_node_impact(node_id))

    def get_lineage(self, node_id: UUID) -> List[GraphNode]:
        """Read upstream lineage through the same MCP-first read seam."""
        response = self._read(
            "lineage",
            recursive_lineage_query(),
            "filmgraph.get_lineage",
            {"node_id": str(node_id)},
        )
        if response is not None:
            try:
                return [GraphNode(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid lineage MCP response"
        return self._fallback(self.repository.get_lineage(node_id))

    def get_workspace_snapshot(self, film_id: str, revision_id: str) -> Dict[str, Any]:
        """Return a transport-neutral read bundle for GraphQueryPort clients.

        The API layer still shapes this bundle into its richer response model;
        keeping this method small makes it usable by a CLI or another adapter.
        """
        return {
            "film_id": film_id,
            "revision_id": revision_id,
            "pipeline_stages": self.list_pipeline_stages(),
            "graph_nodes": self.list_graph_nodes(),
            "graph_edges": self.list_graph_edges(),
            "workflows": self.list_workflows(),
            "runtime_proposals": self.list_runtime_proposals(),
            "delivery_variants": self.list_delivery_variants(),
            "delivery_conflicts": self.list_delivery_conflicts(),
        }

    # Camel-case aliases keep the documented GraphQueryPort usable from
    # integrations that share the TypeScript contract verbatim.
    def getWorkspaceSnapshot(self, film_id: str, revision_id: str) -> Dict[str, Any]:
        return self.get_workspace_snapshot(film_id, revision_id)

    def getNodeImpact(self, node_id: UUID) -> List[GraphNode]:
        return self.get_node_impact(node_id)

    def getLineage(self, node_id: UUID) -> List[GraphNode]:
        return self.get_lineage(node_id)

    def list_workflows(self) -> List[Workflow]:
        response = self._read("workflows", "SELECT * FROM workflows ORDER BY created_at DESC", "filmgraph.list_workflows")
        if response is not None:
            try:
                return [Workflow(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid workflows MCP response"
        return self._fallback(self.repository.list_workflows())

    def get_workflow(self, workflow_id: UUID) -> Optional[Workflow]:
        response = self._read("workflow", "SELECT * FROM workflows WHERE id = %(workflow_id)s LIMIT 1", "filmgraph.get_workflow", {"workflow_id": str(workflow_id)})
        if response is not None:
            try:
                items = self._normalize_sequence(response)
                return Workflow(**items[0]) if items else None
            except Exception:
                self.last_error = "invalid workflow MCP response"
        return self._fallback(self.repository.get_workflow(workflow_id))

    # All writes below intentionally bypass MCP and go straight to the repository.
    def create_workflow(self, name: str, active_stage: Optional[str], requested_by: str, runtime_mode: str, stage_sequence: List[str]) -> Workflow:
        provenance = self._mutation_provenance("workflow", requested_by=requested_by, runtime_mode=runtime_mode)
        return self.repository.create_workflow(Workflow(name=name, active_stage=active_stage, stage_sequence=stage_sequence, provenance=provenance))

    def append_workflow_event(self, workflow_id: UUID, kind: str, actor: str, payload: Dict[str, Any], runtime_mode: str, requested_by: Optional[str] = None) -> WorkflowEvent:
        provenance = self._mutation_provenance("workflow-event", requested_by=requested_by or actor, runtime_mode=runtime_mode, tool_name=kind)
        return self.repository.append_workflow_event(WorkflowEvent(workflow_id=workflow_id, kind=kind, actor=actor, payload=payload, provenance=provenance))

    def list_workflow_events(self, workflow_id: UUID) -> List[WorkflowEvent]:
        response = self._read("workflow_events", "SELECT * FROM workflow_events WHERE workflow_id = %(workflow_id)s ORDER BY sequence", "filmgraph.list_workflow_events", {"workflow_id": str(workflow_id)})
        if response is not None:
            try:
                return [WorkflowEvent(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid workflow_events MCP response"
        return self._fallback(self.repository.list_workflow_events(workflow_id))

    def create_agent_run(self, workflow_id: UUID, prompt: str, stage_name: Optional[str], model_name: str, runtime_mode: str) -> AgentRun:
        provenance = self._mutation_provenance("agent-run", runtime_mode=runtime_mode, model_name=model_name, tool_name="agent.run")
        return self.repository.create_agent_run(AgentRun(workflow_id=workflow_id, stage_name=stage_name, prompt=prompt, model_name=model_name, runtime_mode=runtime_mode, provenance=provenance))

    def append_agent_event(self, run_id: UUID, kind: AgentEventKind, message: str, payload: Dict[str, Any], runtime_mode: str) -> AgentEvent:
        provenance = self._mutation_provenance("agent-event", runtime_mode=runtime_mode, tool_name=kind.value)
        return self.repository.append_agent_event(AgentEvent(run_id=run_id, kind=kind, message=message, payload=payload, provenance=provenance))

    def list_agent_events(self, run_id: UUID) -> List[AgentEvent]:
        response = self._read("agent_events", "SELECT * FROM agent_events WHERE run_id = %(run_id)s ORDER BY sequence", "filmgraph.list_agent_events", {"run_id": str(run_id)})
        if response is not None:
            try:
                return [AgentEvent(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid agent_events MCP response"
        return self._fallback(self.repository.list_agent_events(run_id))

    def list_agent_runs(self) -> List[AgentRun]:
        response = self._read("agent_runs", "SELECT * FROM agent_runs ORDER BY created_at DESC", "filmgraph.list_agent_runs")
        if response is not None:
            try:
                return [AgentRun(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid agent_runs MCP response"
        return self._fallback(self.repository.list_agent_runs())

    def get_agent_run(self, run_id: UUID) -> Optional[AgentRun]:
        response = self._read(
            "agent_run",
            "SELECT * FROM agent_runs WHERE id = %(run_id)s LIMIT 1",
            "filmgraph.get_agent_run",
            {"run_id": str(run_id)},
        )
        if response is not None:
            try:
                items = self._normalize_sequence(response)
                return AgentRun(**items[0]) if items else None
            except Exception:
                self.last_error = "invalid agent_run MCP response"
        return self._fallback(self.repository.get_agent_run(run_id))

    def list_delivery_records(self) -> List[DeliveryRecord]:
        response = self._read("delivery_records", "SELECT * FROM delivery_records ORDER BY delivered_at DESC", "filmgraph.list_delivery_records")
        if response is not None:
            try:
                return [DeliveryRecord(**item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid delivery_records MCP response"
        return self._fallback(self.repository.list_delivery_records())

    def list_runtime_proposals(self) -> List[Dict[str, Any]]:
        response = self._read(
            "runtime_proposals",
            "SELECT * FROM runtime_surgery_proposals ORDER BY created_at, id",
            "filmgraph.list_runtime_proposals",
        )
        if response is not None:
            try:
                return [self._normalize_catalog(item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid runtime_proposals MCP response"
        method = getattr(self.repository, "list_runtime_proposals", lambda: [])
        return self._fallback(method())

    def list_delivery_variants(self) -> List[Dict[str, Any]]:
        response = self._read(
            "delivery_variants",
            "SELECT * FROM delivery_variants ORDER BY created_at, id",
            "filmgraph.list_delivery_variants",
        )
        if response is not None:
            try:
                return [self._normalize_catalog(item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid delivery_variants MCP response"
        method = getattr(self.repository, "list_delivery_variants", lambda: [])
        return self._fallback(method())

    def list_delivery_conflicts(self) -> List[Dict[str, Any]]:
        response = self._read(
            "delivery_conflicts",
            "SELECT * FROM delivery_conflicts ORDER BY created_at, id",
            "filmgraph.list_delivery_conflicts",
        )
        if response is not None:
            try:
                return [self._normalize_catalog(item) for item in self._normalize_sequence(response)]
            except Exception:
                self.last_error = "invalid delivery_conflicts MCP response"
        method = getattr(self.repository, "list_delivery_conflicts", lambda: [])
        return self._fallback(method())

    def create_delivery_record(self, workflow_id: UUID, stage_name: str, destination: str, artifact_uri: Optional[str], runtime_mode: str, status: DeliveryStatus = DeliveryStatus.ready) -> DeliveryRecord:
        provenance = self._mutation_provenance("delivery-record", runtime_mode=runtime_mode, tool_name="delivery.record")
        record = DeliveryRecord(workflow_id=workflow_id, stage_name=stage_name, destination=destination, artifact_uri=artifact_uri, status=status, provenance=provenance)
        return self.repository.create_delivery_record(record)

    def graph_contract(self) -> GraphContractSummary:
        response = self._read("graph_contract", "SELECT kind, relation, stage_name FROM graph_nodes", "filmgraph.graph_contract")
        if response is not None and isinstance(response, dict):
            try:
                return GraphContractSummary(**self._normalize_mapping(response))
            except Exception:
                self.last_error = "invalid graph_contract MCP response"
        return self._fallback(self.repository.graph_contract())

    def _read(self, operation: str, query: str, legacy_tool: str, parameters: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        if self.mcp_client is None or self.graph_query_mode == "direct":
            return None
        payload = {"query": query, "parameters": parameters or {}, "read_only": True, "operation": operation}
        try:
            response = self._client_call("clickhouse.query", payload)
            self.last_source = "clickhouse_mcp"
            self.last_error = None
            return response
        except Exception as first_error:
            self.last_error = str(first_error)
            # Preserve compatibility with the fake contract from early local builds.
            try:
                response = self._client_call(legacy_tool, parameters or {})
                self.last_source = "clickhouse_mcp"
                return response
            except Exception:
                return None

    def _fallback(self, value: Any) -> Any:
        # A ClickHouse repository is the direct fallback; memory is an explicit
        # computed local demo rather than a falsely labelled database query.
        self.last_source = "direct_clickhouse" if self.repository.__class__.__name__ == "ClickHouseFilmGraphRepository" else "computed"
        return value

    def _client_call(self, tool_name: str, payload: Dict[str, Any]) -> Any:
        if hasattr(self.mcp_client, "call_tool"):
            return self.mcp_client.call_tool(tool_name, payload)
        if hasattr(self.mcp_client, "call"):
            return self.mcp_client.call(tool_name, payload)
        raise McpTransportError("MCP client has no call method")

    def _mutation_provenance(self, adapter: str, runtime_mode: str, requested_by: Optional[str] = None, model_name: Optional[str] = None, tool_name: Optional[str] = None) -> Provenance:
        normalized = "simulation" if runtime_mode == "simulated" else runtime_mode
        return Provenance(source="gemini_adk" if normalized == "live" else "agent_simulation" if normalized == "simulation" else "computed", transport="repository", adapter=adapter, runtime_mode=normalized, requested_by=requested_by, model_name=model_name, tool_name=tool_name)

    def _normalize_sequence(self, value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, dict):
            if "items" in value:
                value = value["items"]
            elif "rows" in value:
                value = value["rows"]
            elif "data" in value:
                value = value["data"]
        if not isinstance(value, list):
            raise McpTransportError("expected sequence response")
        return [self._normalize_mapping(item) for item in value]

    def _normalize_mapping(self, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise McpTransportError("expected mapping response")
        data = dict(value)
        if "id" not in data:
            data["id"] = str(uuid4())
        return data

    def _normalize_catalog(self, value: Any) -> Dict[str, Any]:
        data = self._normalize_mapping(value)
        for key in ("id", "film_id", "revision_id", "node_id", "variant_id"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        for key in ("provenance", "metadata"):
            if isinstance(data.get(key), str):
                try:
                    data[key] = json.loads(data[key])
                except json.JSONDecodeError:
                    data[key] = {}
        return data
