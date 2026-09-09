from __future__ import annotations

from uuid import UUID

from filmgraph.dependencies import get_repository
from filmgraph.integrations.mcp import FakeMcpClient, McpFirstFilmGraphService
from filmgraph.models import AgentEventKind, DeliveryStatus


def test_fake_mcp_contract_and_fallback():
    repo = get_repository()
    client = FakeMcpClient(
        responses={
            "filmgraph.list_pipeline_stages": [
                {
                    "id": "30101010-1010-1010-1010-101010101001",
                    "sequence": 1,
                    "name": "Script",
                    "description": "Draft and lock the screenplay spine.",
                }
            ],
            "filmgraph.list_graph_nodes": [
                {
                    "id": "40101010-1010-1010-1010-101010101001",
                    "kind": "script",
                    "label": "Restaurant Exterior",
                    "sequence": 1,
                    "stage_name": "Script",
                    "status": "ready",
                    "metadata": {},
                }
            ],
            "filmgraph.graph_contract": {
                "node_kinds": ["script"],
                "edge_relations": [],
                "stage_names": ["Script"],
            },
            "filmgraph.create_workflow": {
                "id": "bbbbbbbb-1111-2222-3333-444444444444",
                "name": "Contract Workflow",
                "stage_sequence": ["Script"],
                "status": "queued",
                "active_stage": "Script",
                "approval_status": "not_required",
                "delivery_status": "queued",
            },
            "filmgraph.append_workflow_event": {
                "id": "cccccccc-1111-2222-3333-444444444444",
                "workflow_id": "bbbbbbbb-1111-2222-3333-444444444444",
                "sequence": 1,
                "kind": "workflow.started",
                "actor": "system",
                "payload": {"stage": "Script"},
                "occurred_at": "2026-09-08T00:00:00Z",
            },
            "filmgraph.create_agent_run": {
                "id": "dddddddd-1111-2222-3333-444444444444",
                "workflow_id": "bbbbbbbb-1111-2222-3333-444444444444",
                "stage_name": "Script",
                "model_name": "gemini-simulated",
                "runtime_mode": "simulation",
                "status": "queued",
                "prompt": "hello",
            },
            "filmgraph.append_agent_event": {
                "id": "eeeeeeee-1111-2222-3333-444444444444",
                "run_id": "dddddddd-1111-2222-3333-444444444444",
                "sequence": 1,
                "kind": AgentEventKind.started.value,
                "message": "simulation: agent run started",
                "payload": {},
                "occurred_at": "2026-09-08T00:00:00Z",
            },
            "filmgraph.list_agent_events": [
                {
                    "id": "eeeeeeee-1111-2222-3333-444444444444",
                    "run_id": "dddddddd-1111-2222-3333-444444444444",
                    "sequence": 1,
                    "kind": AgentEventKind.started.value,
                    "message": "simulation: agent run started",
                    "payload": {},
                    "occurred_at": "2026-09-08T00:00:00Z",
                }
            ],
            "filmgraph.create_delivery_record": {
                "id": "ffffffff-1111-2222-3333-444444444444",
                "workflow_id": "bbbbbbbb-1111-2222-3333-444444444444",
                "stage_name": "Delivery",
                "destination": "release",
                "status": "delivered",
                "artifact_uri": "local://filmgraph/script-demo",
            },
        }
    )
    service = McpFirstFilmGraphService(repo, mcp_client=client, runtime_mode="simulation")

    assert service.list_pipeline_stages()[0].name == "Script"
    assert service.list_graph_nodes()[0].label == "Restaurant Exterior"
    assert service.graph_contract().stage_names == ["Script"]

    workflow = service.create_workflow("Contract Workflow", "Script", "editorial", "simulation", ["Script"])
    assert workflow.name == "Contract Workflow"
    # MCP is read-only by contract; mutations are persisted by the repository.
    assert workflow.provenance.transport == "repository"

    event = service.append_workflow_event(workflow.id, "workflow.started", "system", {"stage": "Script"}, "simulation")
    assert event.sequence == 1

    run = service.create_agent_run(workflow.id, "hello", "Script", "gemini-simulated", "simulation")
    assert run.stage_name == "Script"

    agent_event = service.append_agent_event(run.id, AgentEventKind.started, "simulation: agent run started", {}, "simulation")
    assert agent_event.kind == AgentEventKind.started

    streamed = service.list_agent_events(run.id)
    assert streamed[0].kind == AgentEventKind.started

    delivery = service.create_delivery_record(workflow.id, "Script", "script-review", "local://filmgraph/script-demo", "simulation", DeliveryStatus.delivered)
    assert delivery.status == DeliveryStatus.delivered

    fallback_workflows = service.list_workflows()
    assert fallback_workflows == repo.list_workflows()

    assert any(call["tool"] == "filmgraph.list_pipeline_stages" for call in client.calls)
    assert client.calls[0]["tool"] == "clickhouse.query"
    assert any(call["tool"] == "filmgraph.list_pipeline_stages" for call in client.calls)
    assert not any(call["tool"].startswith("filmgraph.create_") for call in client.calls)


def test_simulation_provenance_without_mcp():
    repo = get_repository()
    service = McpFirstFilmGraphService(repo, mcp_client=None, runtime_mode="simulation")

    workflow = service.create_workflow("Local Workflow", "Script", "editorial", "simulation", ["Script"])
    assert workflow.provenance.source == "agent_simulation"
    assert workflow.provenance.transport == "repository"
    assert workflow.provenance.adapter == "workflow"

    run = service.create_agent_run(workflow.id, "prompt", "Script", "gemini-simulated", "simulation")
    assert run.provenance.adapter == "agent-run"
    assert run.provenance.transport == "repository"

    delivery = service.create_delivery_record(workflow.id, "Delivery", "release", None, "simulation")
    assert delivery.provenance.adapter == "delivery-record"
    assert delivery.provenance.transport == "repository"


def test_mcp_timeout_marks_direct_clickhouse_fallback():
    class ClickHouseFilmGraphRepository:
        def list_pipeline_stages(self):
            return []

        def list_graph_nodes(self):
            return []

        def list_graph_edges(self):
            return []

        def list_workflows(self):
            return []

        def list_agent_runs(self):
            return []

        def list_delivery_records(self):
            return []

    class DownMcp:
        def call_tool(self, *_args, **_kwargs):
            raise TimeoutError("MCP timeout")

    service = McpFirstFilmGraphService(ClickHouseFilmGraphRepository(), DownMcp(), runtime_mode="simulation")
    assert service.list_pipeline_stages() == []
    assert service.last_source == "direct_clickhouse"
    assert service.last_error == "MCP timeout"


def test_mcp_traversal_uses_recursive_read_only_queries():
    row = {
        "id": "40101010-1010-1010-1010-101010101047",
        "kind": "scene",
        "label": "MOVING CAR — NIGHT",
        "sequence": 6,
        "stage_name": "Script",
        "status": "breaking",
        "film_id": "demo-feature",
        "revision_id": "rev-05",
        "scene_number": "47",
        "metadata": {},
    }
    client = FakeMcpClient({"clickhouse.query": [row]})
    service = McpFirstFilmGraphService(get_repository(), mcp_client=client, runtime_mode="simulation")
    node_id = UUID("40101010-1010-1010-1010-101010101047")

    assert service.get_node_impact(node_id)[0].scene_number == "47"
    assert service.get_lineage(node_id)[0].scene_number == "47"
    assert service.last_source == "clickhouse_mcp"
    traversal_calls = [call for call in client.calls if call["tool"] == "clickhouse.query"]
    assert [call["payload"]["operation"] for call in traversal_calls] == ["node_impact", "lineage"]
    assert all("WITH RECURSIVE" in call["payload"]["query"] for call in traversal_calls)
    assert all(call["payload"]["read_only"] is True for call in traversal_calls)
