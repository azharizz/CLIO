from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from filmgraph.api import create_app
from filmgraph.dependencies import get_repository
from filmgraph.integrations.agents import SimulatedAgentProvider
from filmgraph.models import GraphNodeKind
from filmgraph.repositories.clickhouse import ClickHouseFilmGraphRepository
from filmgraph.settings import ClickHouseSettings
from tests.conftest import reset_singletons


def test_schema_seed_and_allowed_provenance_are_present():
    root = Path(__file__).resolve().parents[2]
    schema = (root / "infra" / "clickhouse" / "init" / "001_schema.sql").read_text()
    seed = (root / "infra" / "clickhouse" / "init" / "002_seed.sql").read_text()

    for table in (
        "films",
        "revisions",
        "graph_nodes",
        "graph_edges",
        "impact_assessments",
        "runtime_surgery_proposals",
        "delivery_variants",
        "delivery_conflicts",
        "workflow_events",
        "agent_runs",
        "agent_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
    assert "LOCAL DEMO" in seed
    assert '"source":"seed"' not in seed
    assert '"source":"direct_clickhouse"' in seed


def test_simulated_provider_preserves_the_adk_shaped_event_order():
    async def collect():
        provider = SimulatedAgentProvider()
        return [event async for event in provider.start_run({"run_id": "aaaaaaaa-0000-0000-0000-000000000001", "stage_name": "Edit", "prompt": "Assess V5"})]

    events = asyncio.run(collect())
    assert [event.payload["phase"] for event in events] == ["narrative", "graph", "analytics", "revision", "critic"]
    assert {event.provenance.source for event in events} == {"agent_simulation"}


def test_simulated_provider_answers_node_operations():
    repository = get_repository()
    graph_nodes = [node.model_dump(mode="json") for node in repository.list_graph_nodes()]
    graph_edges = [edge.model_dump(mode="json") for edge in repository.list_graph_edges()]
    focus_node = next(node for node in graph_nodes if node.get("scene_number") == "17")

    async def collect(prompt: str):
        provider = SimulatedAgentProvider()
        return [event async for event in provider.start_run({
            "run_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "stage_name": "Scene",
            "prompt": prompt,
            "focus_node": str(focus_node["id"]),
            "graph_nodes": graph_nodes,
            "graph_edges": graph_edges,
        })]

    edit = asyncio.run(collect("[EDIT NODE] Edit SC 17. Which nodes are affected?"))
    remove = asyncio.run(collect("[REMOVE NODE] Remove SC 17. Which nodes become unnecessary?"))
    add = asyncio.run(collect("[ADD NODE] Add a pickup near SC 17. Which connections are possible?"))

    assert "AFFECTED" in edit[1].payload["notes"]
    assert edit[1].payload["notes"].count("SC 18") == 1
    assert "SC 19" in edit[1].payload["notes"]
    assert "UNNEEDED" in remove[1].payload["notes"]
    assert "POSSIBLE CONNECTIONS" in add[1].payload["notes"]
    assert "narration" in edit[0].payload["notes"].lower()


def test_direct_clickhouse_repository_queries_and_maps_rows():
    class Result:
        def __init__(self, rows):
            self.rows = rows

        def named_results(self):
            return [dict(row) for row in self.rows]

    class FakeClient:
        def __init__(self):
            self.queries = []

        def query(self, sql, parameters=None):
            self.queries.append((sql, parameters or {}))
            if "pipeline_stages" in sql:
                return Result([{"id": "30101010-1010-1010-1010-101010101001", "sequence": 1, "name": "Script", "description": "Draft."}])
            if "graph_nodes" in sql:
                return Result([{"id": "40101010-1010-1010-1010-101010101001", "kind": "script", "label": "Restaurant", "sequence": 1, "stage_name": "Script", "status": "ready", "metadata": "{}", "provenance": '{"source":"direct_clickhouse"}'}])
            if "graph_edges" in sql:
                return Result([])
            return Result([])

    repository = ClickHouseFilmGraphRepository(ClickHouseSettings("localhost", 8123, "default", "", "filmgraph", False))
    fake = FakeClient()
    repository._client = fake
    stages = repository.list_pipeline_stages()
    nodes = repository.list_graph_nodes()
    assert stages[0].name == "Script"
    assert nodes[0].kind == GraphNodeKind.script
    assert nodes[0].provenance.source == "direct_clickhouse"
    assert any("SELECT * FROM pipeline_stages" in query[0] for query in fake.queries)


def test_browser_boundary_exposes_timed_scene_impact():
    reset_singletons()
    client = TestClient(create_app())
    workspace = client.get("/api/v1/workspace?filmId=demo-feature&revisionId=rev-05")
    assert workspace.status_code == 200
    payload = workspace.json()
    node = next(item for item in payload["graph_nodes"] if item.get("scene_number") == "17")
    node_id = node["id"]

    impact = client.get(f"/api/v1/nodes/{node_id}/impact")
    assert impact.status_code == 200
    assert impact.json()["lineage"]

    assert node["script_text"].startswith("Lookouts spot an iceberg")
    assert node["narration_text"].startswith("NARRATOR:")
    assert node["start_seconds"] == 6600
    assert node["end_seconds"] == 7110
    assert node["duration_seconds"] == 510
    assert UUID(node_id)

    beats = [item for item in payload["graph_nodes"] if item["kind"] == "beat" and item.get("scene_number") == "17"]
    assert len(beats) == 5
    assert all(item["parent_scene_id"] == node_id for item in beats)
