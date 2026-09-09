from __future__ import annotations

"""Application dependencies and the intentionally small local script seed.

The first CLIO slice is a timed screenplay graph. A scene is the parent
unit of meaning: heading, action text, narration, start, end, and duration.
Longer scenes are split into child beats so the graph can answer precise edit,
remove, and add questions without inventing production assets.
"""

from functools import lru_cache
from typing import Any, List
from uuid import UUID

from filmgraph.integrations.mcp import McpFirstFilmGraphService, build_mcp_client
from filmgraph.models import (
    GraphEdge,
    GraphNode,
    GraphNodeKind,
    PipelineStageDefinition,
    Provenance,
    Workflow,
    WorkflowEvent,
    utcnow,
)
from filmgraph.repositories.clickhouse import ClickHouseFilmGraphRepository
from filmgraph.repositories.memory import MemoryFilmGraphRepository
from filmgraph.settings import AppSettings, load_settings


FILM_ID = "demo-feature"
REVISION_ID = "rev-05"
WORKFLOW_ID = UUID("aaaaaaaa-0000-0000-0000-000000000001")


@lru_cache()
def get_settings() -> AppSettings:
    return load_settings()


@lru_cache()
def get_repository():
    settings = get_settings()
    if settings.clickhouse and not settings.use_memory_store:
        try:
            repository = ClickHouseFilmGraphRepository(settings.clickhouse)
            repository.bootstrap()
            return repository
        except Exception:
            # The local graph remains usable while Docker is stopped. The
            # service exposes this distinction as computed/LOCAL FALLBACK.
            pass

    stages = _seed_pipeline_stages()
    nodes = _seed_graph_nodes()
    edges = _seed_graph_edges(nodes)
    repository = MemoryFilmGraphRepository(
        pipeline_stages=stages,
        graph_nodes=nodes,
        graph_edges=edges,
        # Deliberately empty in the script-first slice.
        runtime_proposals=[],
        delivery_variants=[],
        delivery_conflicts=[],
    )
    _seed_demo_workflow(repository, stages)
    return repository


@lru_cache()
def get_service() -> McpFirstFilmGraphService:
    settings = get_settings()
    return McpFirstFilmGraphService(
        get_repository(),
        mcp_client=build_mcp_client(settings.mcp_endpoint, settings.mcp_command),
        runtime_mode=settings.agent_runtime_mode,
        graph_query_mode=settings.graph_query_mode,
    )


def reset_runtime_state() -> None:
    """Reset local singleton state for tests and repeatable captures."""
    get_service.cache_clear()
    get_repository.cache_clear()
    get_settings.cache_clear()


def _seed_pipeline_stages() -> List[PipelineStageDefinition]:
    return [
        PipelineStageDefinition(
            id=UUID("30101010-1010-1010-1010-101010101001"),
            sequence=1,
            name="Script",
            description="Timed screenplay scenes and revision text.",
            provenance=Provenance(source="computed", transport="memory", adapter="script-seed", runtime_mode="simulation"),
        )
    ]


_SCENES: tuple[dict[str, Any], ...] = (
    {
        "number": "42", "heading": "INT. KITCHEN — NIGHT",
        "text": "Mara hides the brass key beneath a tea tin and checks the dark window.",
        "narration": "NARRATOR: The key is hidden, but the night is listening.",
        "start": 0, "end": 78, "status": "understood",
        "beats": [
            {"number": 1, "title": "SEARCH", "text": "Mara enters and checks the latch.", "narration": "NARRATOR: Every lock sounds louder after midnight.", "start": 0, "end": 34},
            {"number": 2, "title": "HIDE", "text": "She slips the brass key beneath a tea tin.", "narration": "MARA (V.O.): Keep it close. Keep it quiet.", "start": 34, "end": 78},
        ],
    },
    {
        "number": "43", "heading": "EXT. ALLEY — NIGHT",
        "text": "A phone vibrates. Mara follows the blue light into the rain.",
        "narration": "NARRATOR: A blue pulse draws her toward the unanswered call.",
        "start": 78, "end": 156, "status": "understood",
        "beats": [
            {"number": 1, "title": "FOLLOW", "text": "The phone vibrates in the puddle; Mara follows.", "narration": "NARRATOR: The signal moves before she does.", "start": 78, "end": 156},
        ],
    },
    {
        "number": "44", "heading": "INT. DINER — NIGHT",
        "text": "Jon slides a photograph across the table: the key belongs to his sister.",
        "narration": "JON: Your sister left this for you.",
        "start": 156, "end": 270, "status": "understood",
        "beats": [
            {"number": 1, "title": "ARRIVAL", "text": "Jon waits in the last booth, photograph face down.", "narration": "NARRATOR: The diner keeps one table for secrets.", "start": 156, "end": 190},
            {"number": 2, "title": "REVEAL", "text": "He turns the photograph toward Mara.", "narration": "JON: Look at the corner. That is her hand.", "start": 190, "end": 230},
            {"number": 3, "title": "CLAIM", "text": "The key is named as his sister’s message.", "narration": "MARA: Then why bring it to me?", "start": 230, "end": 270},
        ],
    },
    {
        "number": "45", "heading": "EXT. STREET — NIGHT",
        "text": "They leave before the bell rings. A pair of headlights turns the corner.",
        "narration": "NARRATOR: The bell never rings; the headlights do.",
        "start": 270, "end": 348, "status": "understood",
        "beats": [
            {"number": 1, "title": "EXIT", "text": "They leave the diner as headlights turn toward them.", "narration": "NARRATOR: Someone else has been waiting.", "start": 270, "end": 348},
        ],
    },
    {
        "number": "46", "heading": "INT. RESTAURANT — NIGHT",
        "text": "Mara stops Jon at the service door and demands the truth about the photograph.",
        "narration": "MARA: Tell me what the photograph proves.",
        "start": 348, "end": 456, "status": "understood",
        "beats": [
            {"number": 1, "title": "BLOCK", "text": "Mara catches Jon at the service door.", "narration": "NARRATOR: There is no quiet way out now.", "start": 348, "end": 400},
            {"number": 2, "title": "DEMAND", "text": "She demands the truth about the photograph.", "narration": "MARA: Say it before we move.", "start": 400, "end": 456},
        ],
    },
    {
        "number": "47", "heading": "MOVING CAR — NIGHT",
        "text": "Mara and Jon argue as city lights cut across the windshield; the key changes hands.",
        "narration": "NARRATOR: In motion, the truth has nowhere to sit.",
        "start": 456, "end": 588, "status": "breaking",
        "beats": [
            {"number": 1, "title": "PULL AWAY", "text": "Jon pulls into traffic before Mara can leave.", "narration": "NARRATOR: The road takes the choice from them.", "start": 456, "end": 488},
            {"number": 2, "title": "ARGUE", "text": "City lights strobe across the windshield as they argue.", "narration": "MARA: You changed the scene, not the truth.", "start": 488, "end": 524},
            {"number": 3, "title": "HANDOFF", "text": "Jon places the brass key in Mara’s palm.", "narration": "JON: Then carry it yourself.", "start": 524, "end": 560},
            {"number": 4, "title": "DECIDE", "text": "Mara closes her hand while the car keeps moving.", "narration": "NARRATOR: The handoff is small; the consequence is not.", "start": 560, "end": 588},
        ],
    },
    {
        "number": "48", "heading": "EXT. BRIDGE — DAWN",
        "text": "The car stops. Jon opens the key and reveals a tiny strip of film inside.",
        "narration": "JON: It was film all along.",
        "start": 588, "end": 690, "status": "pending",
        "beats": [
            {"number": 1, "title": "STOP", "text": "The car stops at the bridge as dawn arrives.", "narration": "NARRATOR: Stillness makes the secret visible.", "start": 588, "end": 638},
            {"number": 2, "title": "OPEN", "text": "Jon opens the key and reveals a strip of film.", "narration": "JON: This is what she wanted found.", "start": 638, "end": 690},
        ],
    },
    {
        "number": "49", "heading": "EXT. ROOFTOP — DAWN",
        "text": "Mara watches the city wake, finally choosing what to do with the evidence.",
        "narration": "NARRATOR: Dawn gives Mara one last clean choice.",
        "start": 690, "end": 780, "status": "pending",
        "beats": [
            {"number": 1, "title": "CHOICE", "text": "Mara watches the city wake and chooses the evidence.", "narration": "MARA (V.O.): I know where this belongs.", "start": 690, "end": 780},
        ],
    },
)


def _scene_uuid(number: str) -> UUID:
    return UUID(f"40101010-1010-1010-1010-1010101010{int(number):02d}")


def _beat_uuid(scene_number: str, beat_number: int) -> UUID:
    """Stable UUIDs keep child beats addressable across refreshes."""
    return UUID(f"41101010-1010-1010-1010-{int(scene_number):04d}{beat_number:08d}")


def _seed_graph_nodes() -> List[GraphNode]:
    source = GraphNode(
        id=UUID("40101010-1010-1010-1010-101010101001"),
        kind=GraphNodeKind.script,
        label="V5 · SC 47",
        sequence=0,
        stage_name="Script",
        status="breaking",
        film_id=FILM_ID,
        revision_id=REVISION_ID,
        script_text="Mara and Jon argue in a moving car; the key changes hands.",
        metadata={"role": "revision_source", "before_text": "Mara and Jon argue inside the restaurant; the key changes hands."},
        provenance=Provenance(source="computed", transport="memory", adapter="script-seed", runtime_mode="simulation"),
    )
    nodes = [source]
    for index, scene in enumerate(_SCENES, start=1):
        start = int(scene["start"])
        end = int(scene["end"])
        nodes.append(
            GraphNode(
                id=_scene_uuid(str(scene["number"])),
                kind=GraphNodeKind.scene,
                label=str(scene["heading"]),
                sequence=index,
                stage_name="Script",
                status=str(scene["status"]),
                film_id=FILM_ID,
                revision_id=REVISION_ID,
                scene_number=str(scene["number"]),
                heading=str(scene["heading"]),
                script_text=str(scene["text"]),
                narration_text=str(scene["narration"]),
                start_seconds=start,
                end_seconds=end,
                duration_seconds=end - start,
                metadata={"role": "scene", "dataset": "LOCAL DEMO", "child_count": len(scene.get("beats", []))},
                provenance=Provenance(source="computed", transport="memory", adapter="script-seed", runtime_mode="simulation"),
            )
        )
        parent_id = nodes[-1].id
        for beat in scene.get("beats", []):
            beat_number = int(beat["number"])
            beat_start = int(beat["start"])
            beat_end = int(beat["end"])
            nodes.append(
                GraphNode(
                    id=_beat_uuid(str(scene["number"]), beat_number),
                    kind=GraphNodeKind.beat,
                    label=str(beat["title"]),
                    # ClickHouse stores sequence as UInt8; keep room for up to
                    # nineteen child beats per scene while staying <= 255.
                    sequence=index * 20 + beat_number,
                    stage_name="Script",
                    status=str(scene["status"]),
                    film_id=FILM_ID,
                    revision_id=REVISION_ID,
                    scene_number=str(scene["number"]),
                    beat_number=beat_number,
                    parent_scene_id=str(parent_id),
                    heading=str(beat["title"]),
                    script_text=str(beat["text"]),
                    narration_text=str(beat["narration"]),
                    start_seconds=beat_start,
                    end_seconds=beat_end,
                    duration_seconds=beat_end - beat_start,
                    metadata={"role": "beat", "dataset": "LOCAL DEMO", "parent_scene": str(scene["number"])},
                    provenance=Provenance(source="computed", transport="memory", adapter="script-seed", runtime_mode="simulation"),
                )
            )
    return nodes


def _seed_graph_edges(nodes: List[GraphNode]) -> List[GraphEdge]:
    # Beats also carry a scene number; keep the parent scene map explicit so
    # backbone edges never accidentally point at the last child beat.
    by_number = {node.scene_number: node for node in nodes if node.scene_number and node.kind == GraphNodeKind.scene}
    source = nodes[0]
    edges: List[GraphEdge] = []

    def add_edge(index: int, source_id: UUID, target_id: UUID, relation: str, tone: str = "understood", kind: str = "backbone") -> None:
        edges.append(
            GraphEdge(
                id=UUID(f"50101010-1010-1010-1010-1010101010{index:02d}"),
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                weight=1.0,
                confidence=0.98,
                metadata={"tone": tone, "kind": kind, "dataset": "LOCAL DEMO"},
                provenance=Provenance(source="computed", transport="memory", adapter="script-seed", runtime_mode="simulation"),
            )
        )

    add_edge(1, source.id, by_number["47"].id, "revises", "breaking")
    for index, left in enumerate(_SCENES[:-1], start=2):
        right = _SCENES[index - 1]
        add_edge(index, by_number[str(left["number"])].id, by_number[str(right["number"])].id, "follows", str(right["status"]))
    add_edge(10, by_number["42"].id, by_number["47"].id, "sets_up")
    add_edge(11, by_number["44"].id, by_number["47"].id, "motivates")
    add_edge(12, by_number["47"].id, by_number["48"].id, "pays_off", "breaking")
    next_index = 13
    for scene in _SCENES:
        parent = by_number[str(scene["number"])]
        previous: UUID | None = None
        for beat in scene.get("beats", []):
            child = next((node for node in nodes if node.kind == GraphNodeKind.beat and node.scene_number == str(scene["number"]) and node.beat_number == int(beat["number"])), None)
            if child is None:
                continue
            add_edge(next_index, parent.id, child.id, "contains", str(scene["status"]), "beat")
            next_index += 1
            if previous is not None:
                add_edge(next_index, previous, child.id, "follows", str(scene["status"]), "beat")
                next_index += 1
            previous = child.id
    return edges


def _seed_demo_workflow(repository: MemoryFilmGraphRepository, stages: List[PipelineStageDefinition]) -> None:
    workflow = repository.create_workflow(
        Workflow(
            id=WORKFLOW_ID,
            name=FILM_ID,
            stage_sequence=[stage.name for stage in stages],
            status="running",
            active_stage="Script",
            approval_status="not_required",
            delivery_status="queued",
            provenance=Provenance(source="computed", transport="memory", adapter="workflow", runtime_mode="simulation", requested_by="editorial"),
        )
    )
    repository.append_workflow_event(
        WorkflowEvent(
            workflow_id=workflow.id,
            sequence=1,
            kind="workflow.started",
            actor="editorial",
            payload={"stage": "Script", "revision": REVISION_ID, "dataset": "LOCAL DEMO"},
            provenance=Provenance(source="computed", transport="memory", adapter="workflow-event", runtime_mode="simulation", requested_by="editorial", tool_name="workflow.started"),
            occurred_at=utcnow(),
        )
    )
