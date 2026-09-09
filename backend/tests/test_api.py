from __future__ import annotations

from fastapi.testclient import TestClient

from filmgraph.api import create_app
from tests.conftest import reset_singletons


def test_workspace_is_script_first_and_timed():
    reset_singletons()
    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "environment": "local",
        "storage_mode": "memory",
        "runtime_mode": "simulation",
    }

    response = client.get("/api/v1/workspace", params={"filmId": "demo-feature", "revisionId": "rev-05"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace"] == {
        "pipeline_name": "CLIO script graph",
        "stage_count": 1,
        "node_count": 151,
        "edge_count": 253,
        "workflow_count": 1,
        "run_count": 0,
        "delivery_count": 0,
        "approval_count": 0,
    }
    assert [stage["name"] for stage in payload["pipeline_stages"]] == ["Script"]
    scenes = [node for node in payload["graph_nodes"] if node["kind"] == "scene"]
    beats = [node for node in payload["graph_nodes"] if node["kind"] == "beat"]
    assert len(scenes) == 25
    assert len(beats) == 125
    scene_17 = next(scene for scene in scenes if scene["scene_number"] == "17")
    assert scene_17["start_seconds"] == 6600
    assert scene_17["end_seconds"] == 7110
    assert scene_17["duration_seconds"] == 510
    assert "revision" in scene_17["narration_text"].lower()
    scene_17_beats = [node for node in beats if node["scene_number"] == "17"]
    assert len(scene_17_beats) == 5
    assert all(node["parent_scene_id"] == scene_17["id"] for node in scene_17_beats)
    for previous, current in zip(scenes, scenes[1:]):
        assert previous["end_seconds"] - previous["start_seconds"] == previous["duration_seconds"]
        assert current["start_seconds"] == previous["end_seconds"]
    assert all(node["kind"] in {"script", "scene", "beat"} for node in payload["graph_nodes"])
    assert payload["runtime_proposals"] == []
    assert payload["delivery_variants"] == []
    assert payload["delivery_conflicts"] == []
    assert payload["delivery"] == {"ready": [], "delivered": []}
    assert payload["graph_contract"]["stage_names"] == ["Script"]


def test_node_impact_and_agent_stream_use_scene_context():
    reset_singletons()
    client = TestClient(create_app())
    workspace = client.get("/api/v1/workspace").json()
    scene_17 = next(node for node in workspace["graph_nodes"] if node.get("scene_number") == "17")

    impact = client.get(f"/api/v1/nodes/{scene_17['id']}/impact")
    assert impact.status_code == 200
    assert any(node.get("scene_number") == "17" for node in impact.json()["impact_nodes"])
    assert any(node.get("kind") == "script" for node in impact.json()["lineage"])

    workflow_id = workspace["workflows"][0]["id"]
    run = client.post(
        "/api/v1/agent-runs",
        json={
            "workflow_id": workflow_id,
            "prompt": "Which scenes are affected?",
            "stage_name": "Script",
            "runtime_mode": "simulation",
            "action": "edit",
            "focus_node": scene_17["id"],
        },
    )
    assert run.status_code == 201
    run_id = run.json()["id"]
    assert run.json()["provenance"]["source"] == "agent_simulation"

    stream = client.get(f"/api/v1/agent-runs/{run_id}/stream")
    assert stream.status_code == 200
    assert "phase:narrative" in stream.text
    assert "phase:graph" in stream.text
    assert "AFFECTED" in stream.text
    assert "phase:analytics" in stream.text
    assert "phase:revision" in stream.text
    assert "phase:critic" in stream.text
    assert "phase:delivery" not in stream.text

    persisted = client.get(f"/api/v1/agent-runs/{run_id}/events").json()
    assert [item["kind"] for item in persisted] == ["started", "progress", "tool_call", "message", "tool_result", "completed"]


def test_agent_read_tools_are_resolved_from_the_live_graph_and_stay_read_only():
    reset_singletons()
    client = TestClient(create_app())

    impact = client.get("/api/v1/agent-tools/nodes/scene-17/impact")
    assert impact.status_code == 200
    payload = impact.json()
    assert payload["focus_node"]["scene_number"] == "17"
    assert payload["query_provenance"]["source"] in {"computed", "direct_clickhouse", "clickhouse_mcp"}

    lineage = client.get("/api/v1/agent-tools/nodes/17/lineage")
    assert lineage.status_code == 200
    assert any(item["kind"] == "script" for item in lineage.json()["lineage"])

    timing = client.get("/api/v1/agent-tools/nodes/scene-17/timing")
    assert timing.status_code == 200
    assert timing.json()["focus_node"]["duration_seconds"] == 510
    assert timing.json()["film_duration_seconds"] == 11700

    search = client.get("/api/v1/agent-tools/script/search", params={"query": "iceberg"})
    assert search.status_code == 200
    assert search.json()["match_count"] >= 1


def test_agent_run_keeps_a_bounded_memory_scope_for_agent_runtime():
    reset_singletons()
    client = TestClient(create_app())
    workflow_id = client.get("/api/v1/workspace").json()["workflows"][0]["id"]
    response = client.post(
        "/api/v1/agent-runs",
        json={
            "workflow_id": workflow_id,
            "prompt": "Explain the scene.",
            "runtime_mode": "simulation",
            "memory_user_id": "browser-editor-123",
        },
    )
    assert response.status_code == 201
    assert response.json()["memory_user_id"] == "browser-editor-123"
    started = client.get(f"/api/v1/agent-runs/{response.json()['id']}/events").json()[0]
    assert started["payload"]["memory"]["scope"] == "user_id"


def test_invalid_workflow_transition_stays_a_409():
    reset_singletons()
    client = TestClient(create_app())
    workflow = client.get("/api/v1/workspace").json()["workflows"][0]["id"]
    duplicate_start = client.post(
        f"/api/v1/workflows/{workflow}/events",
        json={"kind": "workflow.started", "actor": "editorial", "payload": {"stage": "Script"}, "runtime_mode": "simulation"},
    )
    assert duplicate_start.status_code == 409
    assert duplicate_start.json()["detail"]["error_code"] == "workflow.already_started"


def test_script_node_crud_persists_events_and_cascades_children():
    """Scenes and timed beats are the only mutable graph units in this slice."""
    reset_singletons()
    client = TestClient(create_app())

    initial = client.get("/api/v1/workspace").json()
    assert len(initial["graph_nodes"]) == 151
    assert len(initial["graph_edges"]) == 253

    scene_response = client.post(
        "/api/v1/graph/nodes",
        json={
            "kind": "scene",
            "scene_number": "50",
            "heading": "INT. TEST ROOM — NIGHT",
            "script_text": "A new scene enters the cut.",
            "narration_text": "NARRATOR: A new line joins the map.",
            "start_seconds": 11700,
            "end_seconds": 11760,
            "actor": "EDITORIAL",
        },
    )
    assert scene_response.status_code == 201
    scene = scene_response.json()
    assert scene["duration_seconds"] == 60
    assert scene["provenance"]["transport"] == "repository"

    # `scene-50` is the stable browser slug; the API resolves it to the UUID
    # used by the repository before writing the containment edge.
    beat_response = client.post(
        "/api/v1/graph/nodes",
        json={
            "kind": "beat",
            "parent_scene_id": "scene-50",
            "heading": "TURN",
            "script_text": "The new scene turns toward the horizon.",
            "narration_text": "NARRATOR: The room gives way to motion.",
            "start_seconds": 11720,
            "end_seconds": 11760,
        },
    )
    assert beat_response.status_code == 201
    beat = beat_response.json()
    assert beat["parent_scene_id"] == scene["id"]
    assert beat["beat_number"] == 1
    with_beat = client.get("/api/v1/workspace").json()
    created_parent = next(node for node in with_beat["graph_nodes"] if node["id"] == scene["id"])
    assert created_parent["metadata"]["child_count"] == 1

    edited = client.patch(
        f"/api/v1/graph/nodes/{beat['id']}",
        json={
            "script_text": "The new scene turns toward the open sea.",
            "narration_text": "NARRATOR: The turn is now part of the record.",
            "start_seconds": 11730,
            "end_seconds": 11760,
        },
    )
    assert edited.status_code == 200
    assert edited.json()["duration_seconds"] == 30
    assert edited.json()["script_text"].endswith("open sea.")

    invalid = client.patch(
        f"/api/v1/graph/nodes/{beat['id']}",
        json={"start_seconds": 840, "end_seconds": 810},
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["error_code"] == "node.invalid_timing"

    deleted = client.delete(f"/api/v1/graph/nodes/{scene['id']}")
    assert deleted.status_code == 200
    assert beat["id"] in deleted.json()["deleted_ids"]
    final = client.get("/api/v1/workspace").json()
    assert len(final["graph_nodes"]) == 151
    assert len(final["graph_edges"]) == 253
    assert [event["kind"] for event in final["workflow_events"][-4:]] == [
        "graph.node.created",
        "graph.node.created",
        "graph.node.updated",
        "graph.node.deleted",
    ]
