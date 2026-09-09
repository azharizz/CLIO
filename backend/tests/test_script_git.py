from __future__ import annotations

from filmgraph import api as api_module
from filmgraph.integrations.script_git import load_github_script, parse_github_source, parse_screenplay
from fastapi.testclient import TestClient
from tests.conftest import reset_singletons


def test_github_source_forms_are_normalized():
    target = parse_github_source("acme/feature:screenplay/main.fountain", ref="feature")
    assert target.owner == "acme"
    assert target.repo == "feature"
    assert target.path == "screenplay/main.fountain"
    assert target.ref == "feature"

    raw = parse_github_source("https://raw.githubusercontent.com/acme/feature/main/script.fountain")
    assert (raw.owner, raw.repo, raw.ref, raw.path) == ("acme", "feature", "main", "script.fountain")


def test_placeholder_github_url_is_a_two_revision_offline_demo():
    current = load_github_script("https://github.com/owner/repository/blob/main/script.fountain")
    assert current["repository"] == "owner/repository"
    assert current["provenance"]["transport"] == "local-fixture"
    assert current["sha"] == "clio-demo-main-0001"
    assert current["parsed"]["scene_count"] == 3
    assert len(current["revisions"]) == 2

    before_sha = current["revisions"][1]["sha"]
    before = load_github_script(
        "https://github.com/owner/repository/blob/main/script.fountain",
        ref=before_sha,
    )
    assert before["sha"] == before_sha
    scene = next(node for node in before["nodes"] if node["kind"] == "scene" and node["scene_number"] == "17")
    assert scene["heading"] == "INT. BRIDGE / LOOKOUT — NIGHT"


def test_screenplay_parser_preserves_explicit_time_and_marks_estimates():
    document = """SC 42 — INT. KITCHEN — NIGHT [00:00-00:30]

NARRATOR: The lock sounds louder after midnight.

Mara hides the key.

SC 43 — EXT. ALLEY — NIGHT

The phone vibrates in the rain.
"""
    parsed = parse_screenplay(document, sha="abc123")
    assert parsed["parsed"] == {
        "scene_count": 2,
        "beat_count": 3,
        "duration_seconds": 48,
        "timing_estimated": True,
    }
    scenes = [row for row in parsed["nodes"] if row["kind"] == "scene"]
    beats = [row for row in parsed["nodes"] if row["kind"] == "beat"]
    assert scenes[0]["start_seconds"] == 0
    assert scenes[0]["end_seconds"] == 30
    assert scenes[0]["narration_text"].startswith("NARRATOR:")
    assert beats[0]["parent_scene_id"] == str(scenes[0]["id"])
    assert scenes[1]["start_seconds"] == 30
    assert scenes[1]["metadata"]["timing_estimated"] is True


def test_script_git_apply_replaces_only_script_rows_and_appends_event(monkeypatch):
    reset_singletons()
    parsed = parse_screenplay(
        "SC 1 — INT. ROOM — DAY [00:00-00:12]\n\nNARRATOR: Begin.\n\nShe opens the door.",
        sha="commit-1",
    )
    document = {
        "source": "github",
        "repository": "acme/feature",
        "owner": "acme",
        "repo": "feature",
        "path": "script.fountain",
        "ref": "main",
        "sha": "commit-1",
        "short_sha": "commit-1",
        "message": "Import script",
        "parsed": parsed["parsed"],
        "revisions": [],
        "provenance": {"source": "computed", "transport": "github", "adapter": "test", "runtime_mode": "local"},
        "nodes": parsed["nodes"],
        "edges": parsed["edges"],
        "revision_id": parsed["revision_id"],
        "content_hash": parsed["content_hash"],
    }
    monkeypatch.setattr(api_module, "load_github_script", lambda *args, **kwargs: document)
    client = TestClient(api_module.create_app())
    response = client.post("/api/v1/script-git/apply", json={"source": "acme/feature:script.fountain", "ref": "main"})
    assert response.status_code == 200
    workspace = client.get("/api/v1/workspace").json()
    assert len([node for node in workspace["graph_nodes"] if node["kind"] == "scene"]) == 1
    assert workspace["graph_nodes"][0]["metadata"]["dataset"] == "GITHUB"
    assert any(event["kind"] == "script.git.applied" for event in workspace["workflow_events"])


def test_script_git_revert_restores_the_captured_before_map(monkeypatch):
    reset_singletons()
    initial = TestClient(api_module.create_app()).get("/api/v1/workspace").json()
    initial_scene = next(node for node in initial["graph_nodes"] if node["kind"] == "scene")
    parsed = parse_screenplay(
        "SC 1 — INT. IMPORTED ROOM — DAY [00:00-00:18]\n\nThe imported cut replaces the local demo.",
        sha="commit-2",
    )
    document = {
        "source": "github",
        "repository": "acme/feature",
        "owner": "acme",
        "repo": "feature",
        "path": "script.fountain",
        "ref": "main",
        "sha": "commit-2",
        "short_sha": "commit-2",
        "message": "Import alternate cut",
        "parsed": parsed["parsed"],
        "revisions": [],
        "provenance": {"source": "computed", "transport": "github", "adapter": "test", "runtime_mode": "local"},
        "nodes": parsed["nodes"],
        "edges": parsed["edges"],
        "revision_id": parsed["revision_id"],
        "content_hash": parsed["content_hash"],
    }
    monkeypatch.setattr(api_module, "load_github_script", lambda *args, **kwargs: document)
    client = TestClient(api_module.create_app())

    applied = client.post("/api/v1/script-git/apply", json={"source": "acme/feature:script.fountain", "ref": "main"})
    assert applied.status_code == 200
    applied_workspace = client.get("/api/v1/workspace").json()
    assert next(node for node in applied_workspace["graph_nodes"] if node["kind"] == "scene")["heading"] == "INT. IMPORTED ROOM — DAY"

    restored = client.post("/api/v1/script-git/revert", json={"actor": "EDITORIAL"})
    assert restored.status_code == 200
    restored_workspace = client.get("/api/v1/workspace").json()
    restored_scene = next(node for node in restored_workspace["graph_nodes"] if node["kind"] == "scene")
    assert restored_scene["id"] == initial_scene["id"]
    assert restored_scene["heading"] == initial_scene["heading"]
    assert restored_workspace["script_git"] is None
    assert any(event["kind"] == "script.git.reverted" for event in restored_workspace["workflow_events"])


def test_script_git_revert_refuses_to_erase_a_later_graph_edit(monkeypatch):
    reset_singletons()
    parsed = parse_screenplay(
        "SC 1 — INT. IMPORTED ROOM — DAY [00:00-00:18]\n\nThe imported cut replaces the local demo.",
        sha="commit-3",
    )
    document = {
        "source": "github", "repository": "acme/feature", "owner": "acme", "repo": "feature",
        "path": "script.fountain", "ref": "main", "sha": "commit-3", "short_sha": "commit-3",
        "message": "Import alternate cut", "parsed": parsed["parsed"], "revisions": [],
        "provenance": {"source": "computed", "transport": "github", "adapter": "test", "runtime_mode": "local"},
        "nodes": parsed["nodes"], "edges": parsed["edges"], "revision_id": parsed["revision_id"], "content_hash": parsed["content_hash"],
    }
    monkeypatch.setattr(api_module, "load_github_script", lambda *args, **kwargs: document)
    client = TestClient(api_module.create_app())
    assert client.post("/api/v1/script-git/apply", json={"source": "acme/feature:script.fountain", "ref": "main"}).status_code == 200
    workspace = client.get("/api/v1/workspace").json()
    imported_scene = next(node for node in workspace["graph_nodes"] if node["kind"] == "scene")
    update = client.patch(
        f"/api/v1/graph/nodes/{imported_scene['id']}",
        json={"heading": "INT. EDITED AFTER IMPORT — DAY", "actor": "EDITORIAL"},
    )
    assert update.status_code == 200
    rejected = client.post("/api/v1/script-git/revert", json={"actor": "EDITORIAL"})
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["error_code"] == "script_git.revert_not_ready"
