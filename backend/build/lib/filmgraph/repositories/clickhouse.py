from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
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
from filmgraph.graph_queries import recursive_impact_query, recursive_lineage_query


DEMO_FILM_ID = "demo-feature"
DEMO_STORYBOARD_VERSION = "titanic-v1"
DEMO_SCENE_COUNT = 25
DEMO_BEAT_COUNT = 125


class ClickHouseFilmGraphRepository:
    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._client = None

    def _client_or_raise(self):
        if self._client is None:
            self._client = self._create_client(self._settings.database)
        return self._client

    def bootstrap(self) -> None:
        # Connect against the default database while creating the configured
        # application database. Passing a not-yet-created database to the
        # HTTP client can make the first CREATE DATABASE command fail.
        client = self._client or self._create_client("__default__")
        self._client = client
        init_dir = Path(__file__).resolve().parents[3] / "infra" / "clickhouse" / "init"
        database = _quote_identifier(self._settings.database)
        if bool(getattr(self._settings, "create_database", True)):
            try:
                client.command(f"CREATE DATABASE IF NOT EXISTS {database}", use_database=False)
            except Exception as exc:
                mode = str(getattr(self._settings, "database_mode", "local"))
                raise RuntimeError(
                    f"Unable to create ClickHouse {mode} database '{self._settings.database}'. "
                    "Create it in ClickHouse or grant CREATE DATABASE to the configured user."
                ) from exc

        if not bool(getattr(self._settings, "bootstrap_schema", True)):
            # A pre-provisioned database can opt out of DDL at startup.
            client.database = self._settings.database
            return

        # The checked-in init files are also used by Docker and intentionally
        # say ``filmgraph``. Rewrite only their database directives here so the
        # same schema/seed can initialize a Cloud database named ``clio``.
        self._execute_sql_file(
            client,
            init_dir / "001_schema.sql",
            self._settings.database,
            create_database=bool(getattr(self._settings, "create_database", True)),
        )
        client.database = self._settings.database
        # A previous local build may have seeded a production-shaped graph.
        # Upgrade that demo database in place so the visible workspace cannot
        # retain out-of-scope rows after switching to script-first data.
        self._migrate_script_columns(client)
        counts = self._query_rows("SELECT count() AS count FROM pipeline_stages")
        stale = False
        try:
            stale_rows = self._query_rows(
                "SELECT count() AS count FROM graph_nodes WHERE kind IN ('master', 'localization', 'delivery', 'edit', 'take', 'shot', 'shoot', 'story_beat')"
            )
            stale = bool(stale_rows and int(stale_rows[0]["count"]) > 0)
        except Exception:
            stale = False
        try:
            beat_rows = self._query_rows(
                "SELECT count() AS count FROM graph_nodes WHERE kind = 'beat' AND film_id = %(film_id)s",
                {"film_id": DEMO_FILM_ID},
            )
            scene_rows = self._query_rows(
                "SELECT count() AS count FROM graph_nodes WHERE kind = 'scene' AND film_id = %(film_id)s",
                {"film_id": DEMO_FILM_ID},
            )
            version_rows = self._query_rows(
                "SELECT count() AS count FROM graph_nodes WHERE film_id = %(film_id)s AND metadata LIKE %(version)s",
                {"film_id": DEMO_FILM_ID, "version": f"%{DEMO_STORYBOARD_VERSION}%"},
            )
            if (
                not beat_rows
                or int(beat_rows[0]["count"]) != DEMO_BEAT_COUNT
                or not scene_rows
                or int(scene_rows[0]["count"]) != DEMO_SCENE_COUNT
                or not version_rows
                or int(version_rows[0]["count"]) < DEMO_SCENE_COUNT
            ):
                stale = True
        except Exception:
            stale = True
        graph_rows = self._query_rows("SELECT count() AS count FROM graph_nodes")
        pipeline_count = int(counts[0]["count"]) if counts else 0
        graph_count = int(graph_rows[0]["count"]) if graph_rows else 0
        needs_seed = pipeline_count != 1 or graph_count == 0 or stale
        if bool(getattr(self._settings, "seed_demo", True)) and needs_seed:
            # Seed an empty database on first run. A stale Cloud database is
            # migrated only when every graph row belongs to the synthetic
            # demo scope; unrelated Cloud projects are never truncated.
            if pipeline_count == 0 and graph_count == 0:
                self._execute_sql_file(
                    client,
                    init_dir / "002_seed.sql",
                    self._settings.database,
                    create_database=bool(getattr(self._settings, "create_database", True)),
                )
            elif self._can_reset_demo:
                self._clear_local_demo_tables(client)
                self._execute_sql_file(
                    client,
                    init_dir / "002_seed.sql",
                    self._settings.database,
                    create_database=bool(getattr(self._settings, "create_database", True)),
                )
            elif self._demo_scope_is_only_local_fixture():
                self._clear_cloud_demo_scope()
                self._execute_sql_file(
                    client,
                    init_dir / "002_seed.sql",
                    self._settings.database,
                    create_database=bool(getattr(self._settings, "create_database", True)),
                )
        client.database = self._settings.database

    def _migrate_script_columns(self, client: Any) -> None:
        """Add the timed-script columns when an older local table exists."""
        statements = (
            "ALTER TABLE revisions ADD COLUMN IF NOT EXISTS before_text String DEFAULT ''",
            "ALTER TABLE revisions ADD COLUMN IF NOT EXISTS after_text String DEFAULT ''",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS film_id String DEFAULT ''",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS revision_id String DEFAULT ''",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS scene_number Nullable(String)",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS beat_number Nullable(UInt16)",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS parent_scene_id Nullable(String)",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS heading Nullable(String)",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS script_text Nullable(String)",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS narration_text Nullable(String)",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS start_seconds Nullable(Int32)",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS end_seconds Nullable(Int32)",
            "ALTER TABLE graph_nodes ADD COLUMN IF NOT EXISTS duration_seconds Nullable(Int32)",
            "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS memory_user_id String DEFAULT 'anonymous'",
        )
        for statement in statements:
            try:
                client.command(statement)
            except Exception:
                # Fresh schemas already contain the columns; older ClickHouse
                # versions may not support IF NOT EXISTS for ALTER. The seed
                # path below still remains usable on a clean database.
                pass

    def _clear_local_demo_tables(self, client: Any) -> None:
        if not self._can_reset_demo:
            return
        for table in (
            "films",
            "revisions",
            "pipeline_stages",
            "graph_nodes",
            "graph_edges",
            "impact_assessments",
            "runtime_surgery_proposals",
            "delivery_variants",
            "delivery_conflicts",
            "workflows",
            "workflow_events",
            "agent_runs",
            "agent_events",
            "delivery_records",
        ):
            try:
                client.command(f"TRUNCATE TABLE {table}")
            except Exception:
                pass

    def _demo_scope_is_only_local_fixture(self) -> bool:
        """Allow the requested Titanic upgrade only for the synthetic demo.

        Cloud is treated as shared by default. We migrate automatically only
        when every existing graph row belongs to the explicitly synthetic
        ``demo-feature`` film. User-authored rows created inside this demo
        still belong to that bounded scope; any other film ID blocks reset.
        """
        try:
            rows = self._query_rows(
                "SELECT count() AS total, "
                "countIf(film_id = %(film_id)s) AS demo "
                "FROM graph_nodes",
                {"film_id": DEMO_FILM_ID},
            )
            if not rows:
                return False
            total = int(rows[0].get("total", 0))
            demo = int(rows[0].get("demo", 0))
            return total > 0 and total == demo
        except Exception:
            return False

    def _clear_cloud_demo_scope(self) -> None:
        """Remove only rows belonging to the synthetic demo before reseeding."""
        client = self._client_or_raise()

        def quoted(values: List[Any]) -> str:
            return ", ".join("'" + str(value).replace("'", "") + "'" for value in values)

        node_rows = self._query_rows(
            "SELECT toString(id) AS id FROM graph_nodes WHERE film_id = %(film_id)s",
            {"film_id": DEMO_FILM_ID},
        )
        node_ids = [row["id"] for row in node_rows if row.get("id")]
        workflow_rows = self._query_rows(
            "SELECT toString(id) AS id FROM workflows WHERE name = %(name)s",
            {"name": DEMO_FILM_ID},
        )
        workflow_ids = [row["id"] for row in workflow_rows if row.get("id")]
        run_ids: List[str] = []
        if workflow_ids:
            run_rows = self._query_rows(
                f"SELECT toString(id) AS id FROM agent_runs WHERE workflow_id IN ({quoted(workflow_ids)})"
            )
            run_ids = [row["id"] for row in run_rows if row.get("id")]
        variant_rows = self._query_rows(
            "SELECT toString(id) AS id FROM delivery_variants WHERE film_id = %(film_id)s",
            {"film_id": DEMO_FILM_ID},
        )
        variant_ids = [row["id"] for row in variant_rows if row.get("id")]

        statements: List[str] = []
        if node_ids:
            values = quoted(node_ids)
            statements.extend([
                f"ALTER TABLE graph_edges DELETE WHERE source_id IN ({values}) OR target_id IN ({values}) SETTINGS mutations_sync = 1",
                f"ALTER TABLE graph_nodes DELETE WHERE id IN ({values}) SETTINGS mutations_sync = 1",
            ])
        if workflow_ids:
            values = quoted(workflow_ids)
            statements.extend([
                f"ALTER TABLE workflow_events DELETE WHERE workflow_id IN ({values}) SETTINGS mutations_sync = 1",
                f"ALTER TABLE delivery_records DELETE WHERE workflow_id IN ({values}) SETTINGS mutations_sync = 1",
                f"ALTER TABLE workflows DELETE WHERE id IN ({values}) SETTINGS mutations_sync = 1",
            ])
        if run_ids:
            values = quoted(run_ids)
            statements.append(f"ALTER TABLE agent_events DELETE WHERE run_id IN ({values}) SETTINGS mutations_sync = 1")
            statements.append(f"ALTER TABLE agent_runs DELETE WHERE id IN ({values}) SETTINGS mutations_sync = 1")
        if variant_ids:
            values = quoted(variant_ids)
            statements.append(f"ALTER TABLE delivery_conflicts DELETE WHERE variant_id IN ({values}) SETTINGS mutations_sync = 1")
        for table, where in (
            ("films", "id = 'demo-feature'"),
            ("revisions", "film_id = 'demo-feature'"),
            ("pipeline_stages", "name = 'Script'"),
            ("impact_assessments", "film_id = 'demo-feature'"),
            ("runtime_surgery_proposals", "film_id = 'demo-feature'"),
            ("delivery_variants", "film_id = 'demo-feature'"),
        ):
            statements.append(f"ALTER TABLE {table} DELETE WHERE {where} SETTINGS mutations_sync = 1")
        failures: List[str] = []
        for statement in statements:
            try:
                client.command(statement)
            except Exception as exc:
                failures.append(f"{statement}: {exc}")
        if failures:
            # Never seed on top of a partially deleted scope: duplicate rows
            # would make the append-only snapshot ambiguous. Surface the
            # first provider error so startup falls back with a useful cause.
            raise RuntimeError("Cloud demo migration failed: " + failures[0])

    @property
    def _can_reset_demo(self) -> bool:
        """Destructive demo resets are local-only and opt-in."""
        return (
            str(getattr(self._settings, "database_mode", "local")).lower() == "local"
            and bool(getattr(self._settings, "allow_demo_reset", False))
        )

    def _create_client(self, database: str):
        try:
            import clickhouse_connect
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("clickhouse-connect is required for the ClickHouse repository") from exc
        return clickhouse_connect.get_client(
            host=self._settings.host,
            port=self._settings.port,
            username=self._settings.username,
            password=self._settings.password,
            database=database,
            secure=self._settings.secure,
            # The FastAPI repository is shared by worker threads. No query in
            # this adapter relies on temporary/session state, so avoid a
            # single auto-generated HTTP session rejecting concurrent reads.
            autogenerate_session_id=False,
        )

    def list_pipeline_stages(self) -> List[PipelineStageDefinition]:
        rows = self._query_rows("SELECT * FROM pipeline_stages ORDER BY sequence, id")
        return [PipelineStageDefinition(**row) for row in rows]

    def list_graph_nodes(self) -> List[GraphNode]:
        rows = self._query_rows("SELECT * FROM graph_nodes ORDER BY sequence, label")
        return [GraphNode(**row) for row in rows]

    def list_graph_edges(self) -> List[GraphEdge]:
        rows = self._query_rows("SELECT * FROM graph_edges ORDER BY created_at, id")
        return [GraphEdge(**row) for row in rows]

    def create_graph_node(self, node: GraphNode, edges: Optional[List[GraphEdge]] = None) -> GraphNode:
        """Persist a human-authored scene/beat and its explicit lineage edges."""
        client = self._client_or_raise()
        client.insert(
            "graph_nodes",
            [[
                str(node.id),
                node.kind.value,
                node.label,
                node.sequence,
                node.stage_name,
                node.status,
                node.film_id or "",
                node.revision_id or "",
                node.scene_number,
                node.beat_number,
                node.parent_scene_id,
                node.heading,
                node.script_text,
                node.narration_text,
                node.start_seconds,
                node.end_seconds,
                node.duration_seconds,
                json.dumps(node.metadata),
                json.dumps(node.provenance.model_dump()),
                node.created_at,
            ]],
            column_names=[
                "id", "kind", "label", "sequence", "stage_name", "status", "film_id", "revision_id",
                "scene_number", "beat_number", "parent_scene_id", "heading", "script_text", "narration_text",
                "start_seconds", "end_seconds", "duration_seconds", "metadata", "provenance", "created_at",
            ],
        )
        for edge in edges or []:
            self._insert_graph_edge(edge)
        if node.kind.value == "beat" and node.parent_scene_id:
            # `child_count` is a denormalized read hint on the parent scene.
            # Recompute it from persisted beat rows after the insert so a
            # refresh never shows an obsolete Bnn badge.
            try:
                parent_id = UUID(str(node.parent_scene_id))
                count_rows = self._query_rows(
                    "SELECT count() AS count FROM graph_nodes WHERE kind = 'beat' AND parent_scene_id = %(parent_id)s",
                    {"parent_id": str(parent_id)},
                )
                count = int(count_rows[0]["count"]) if count_rows else 0
                parent_rows = self._query_rows("SELECT metadata FROM graph_nodes WHERE id = %(parent_id)s LIMIT 1", {"parent_id": str(parent_id)})
                raw_metadata = parent_rows[0].get("metadata") if parent_rows else None
                metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
                metadata["child_count"] = count
                client.command(
                    "ALTER TABLE graph_nodes UPDATE metadata = %(metadata)s WHERE id = %(parent_id)s SETTINGS mutations_sync = 1",
                    {"parent_id": str(parent_id), "metadata": json.dumps(metadata)},
                )
            except Exception:
                # The node and lineage write is still valid if an older
                # ClickHouse build cannot mutate the optional display hint.
                pass
        return node

    def update_graph_node(self, node: GraphNode) -> GraphNode:
        """Update only the mutable script payload; identity/parentage remain stable."""
        self._client_or_raise().command(
            "ALTER TABLE graph_nodes UPDATE "
            "label = %(label)s, status = %(status)s, heading = %(heading)s, script_text = %(script_text)s, "
            "narration_text = %(narration_text)s, start_seconds = %(start_seconds)s, end_seconds = %(end_seconds)s, "
            "duration_seconds = %(duration_seconds)s, metadata = %(metadata)s, provenance = %(provenance)s "
            "WHERE id = %(node_id)s SETTINGS mutations_sync = 1",
            {
                "node_id": str(node.id),
                "label": node.label,
                "status": node.status,
                "heading": node.heading,
                "script_text": node.script_text,
                "narration_text": node.narration_text,
                "start_seconds": node.start_seconds,
                "end_seconds": node.end_seconds,
                "duration_seconds": node.duration_seconds,
                "metadata": json.dumps(node.metadata),
                "provenance": json.dumps(node.provenance.model_dump()),
            },
        )
        return node

    def delete_graph_node(self, node_id: UUID) -> List[UUID]:
        """Delete a node and any child beats, then remove their graph edges."""
        nodes = {node.id: node for node in self.list_graph_nodes()}
        if node_id not in nodes:
            return []
        deleted: set[UUID] = {node_id}
        parent_ids: set[UUID] = set()
        changed = True
        while changed:
            changed = False
            deleted_strings = {str(item) for item in deleted}
            for candidate in nodes.values():
                if candidate.id not in deleted and candidate.parent_scene_id in deleted_strings:
                    deleted.add(candidate.id)
                    changed = True
        for item in deleted:
            candidate = nodes.get(item)
            if candidate is None or candidate.kind.value != "beat" or not candidate.parent_scene_id:
                continue
            try:
                parent_ids.add(UUID(candidate.parent_scene_id))
            except ValueError:
                continue
        ids = ", ".join("'" + str(item) + "'" for item in deleted)
        client = self._client_or_raise()
        client.command(f"ALTER TABLE graph_edges DELETE WHERE source_id IN ({ids}) OR target_id IN ({ids}) SETTINGS mutations_sync = 1")
        client.command(f"ALTER TABLE graph_nodes DELETE WHERE id IN ({ids}) SETTINGS mutations_sync = 1")
        for parent_id in parent_ids:
            try:
                count_rows = self._query_rows(
                    "SELECT count() AS count FROM graph_nodes WHERE kind = 'beat' AND parent_scene_id = %(parent_id)s",
                    {"parent_id": str(parent_id)},
                )
                count = int(count_rows[0]["count"]) if count_rows else 0
                parent_rows = self._query_rows("SELECT metadata FROM graph_nodes WHERE id = %(parent_id)s LIMIT 1", {"parent_id": str(parent_id)})
                if not parent_rows:
                    continue
                raw_metadata = parent_rows[0].get("metadata")
                metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
                metadata["child_count"] = count
                client.command(
                    "ALTER TABLE graph_nodes UPDATE metadata = %(metadata)s WHERE id = %(parent_id)s SETTINGS mutations_sync = 1",
                    {"parent_id": str(parent_id), "metadata": json.dumps(metadata)},
                )
            except Exception:
                pass
        return list(deleted)

    def replace_script_graph(self, nodes: List[GraphNode], edges: List[GraphEdge]) -> None:
        """Replace screenplay rows while retaining workflows and event history.

        The local schema has no foreign keys, so the operation is a small,
        synchronous delete/insert of only ``script``, ``scene``, and ``beat``
        rows. Existing production-shaped rows (if any) remain untouched.
        """
        client = self._client_or_raise()
        current = [
            node
            for node in self.list_graph_nodes()
            if node.kind.value in {"script", "scene", "beat", "story_beat"}
        ]
        ids = [str(node.id) for node in current]
        if ids:
            quoted = ", ".join("'" + item.replace("'", "") + "'" for item in ids)
            client.command(
                f"ALTER TABLE graph_edges DELETE WHERE source_id IN ({quoted}) OR target_id IN ({quoted}) SETTINGS mutations_sync = 1"
            )
            client.command(f"ALTER TABLE graph_nodes DELETE WHERE id IN ({quoted}) SETTINGS mutations_sync = 1")
        for node in nodes:
            client.insert(
                "graph_nodes",
                [[
                    str(node.id), node.kind.value, node.label, min(255, int(node.sequence)), node.stage_name,
                    node.status, node.film_id or "", node.revision_id or "", node.scene_number, node.beat_number,
                    node.parent_scene_id, node.heading, node.script_text, node.narration_text,
                    node.start_seconds, node.end_seconds, node.duration_seconds, json.dumps(node.metadata),
                    json.dumps(node.provenance.model_dump()), node.created_at,
                ]],
                column_names=[
                    "id", "kind", "label", "sequence", "stage_name", "status", "film_id", "revision_id",
                    "scene_number", "beat_number", "parent_scene_id", "heading", "script_text", "narration_text",
                    "start_seconds", "end_seconds", "duration_seconds", "metadata", "provenance", "created_at",
                ],
            )
        for edge in edges:
            self._insert_graph_edge(edge)

    def _insert_graph_edge(self, edge: GraphEdge) -> None:
        self._client_or_raise().insert(
            "graph_edges",
            [[
                str(edge.id), str(edge.source_id), str(edge.target_id), edge.relation, edge.weight,
                edge.confidence, json.dumps(edge.metadata), json.dumps(edge.provenance.model_dump()), edge.created_at,
            ]],
            column_names=["id", "source_id", "target_id", "relation", "weight", "confidence", "metadata", "provenance", "created_at"],
        )

    def get_node_impact(self, node_id: UUID) -> List[GraphNode]:
        """Return the connected neighborhood with a cycle-safe CTE.

        Older ClickHouse builds, or a mocked client that does not implement
        recursive CTEs, still get the original Python traversal as a local
        compatibility fallback.
        """
        try:
            rows = self._query_rows(recursive_impact_query(), {"node_id": str(node_id)})
            return [GraphNode(**row) for row in rows]
        except Exception:
            return self._python_node_impact(node_id)

    def _python_node_impact(self, node_id: UUID) -> List[GraphNode]:
        """Compatibility traversal used only when recursive SQL is unavailable."""
        nodes = {node.id: node for node in self.list_graph_nodes()}
        edges = self.list_graph_edges()
        adjacency: Dict[UUID, List[UUID]] = {}
        for edge in edges:
            adjacency.setdefault(edge.source_id, []).append(edge.target_id)
            adjacency.setdefault(edge.target_id, []).append(edge.source_id)
        seen: set[UUID] = set()
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            queue.extend(adjacency.get(current, []))
        return sorted((nodes[item] for item in seen if item in nodes), key=lambda node: (node.sequence, str(node.id)))

    def get_lineage(self, node_id: UUID) -> List[GraphNode]:
        """Return the node and all upstream parents with a recursive CTE."""
        try:
            rows = self._query_rows(recursive_lineage_query(), {"node_id": str(node_id)})
            return [GraphNode(**row) for row in rows]
        except Exception:
            return self._python_lineage(node_id)

    def _python_lineage(self, node_id: UUID) -> List[GraphNode]:
        """Compatibility traversal used only when recursive SQL is unavailable."""
        nodes = {node.id: node for node in self.list_graph_nodes()}
        parents: Dict[UUID, List[UUID]] = {}
        for edge in self.list_graph_edges():
            parents.setdefault(edge.target_id, []).append(edge.source_id)
        seen: set[UUID] = set()
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            queue.extend(parents.get(current, []))
        return sorted((nodes[item] for item in seen if item in nodes), key=lambda node: (node.sequence, str(node.id)))

    def get_workspace_snapshot(self, film_id: str, revision_id: str) -> Dict[str, Any]:
        return {
            "film_id": film_id,
            "revision_id": revision_id,
            "pipeline_stages": self.list_pipeline_stages(),
            "graph_nodes": self.list_graph_nodes(),
            "graph_edges": self.list_graph_edges(),
            "workflows": self.list_workflows(),
        }

    def list_workflows(self) -> List[Workflow]:
        rows = self._query_rows("SELECT * FROM workflows ORDER BY created_at DESC")
        return [Workflow(**row) for row in rows]

    def get_workflow(self, workflow_id: UUID) -> Optional[Workflow]:
        rows = self._query_rows("SELECT * FROM workflows WHERE id = %(workflow_id)s LIMIT 1", {"workflow_id": str(workflow_id)})
        return Workflow(**rows[0]) if rows else None

    def create_workflow(self, workflow: Workflow) -> Workflow:
        self._client_or_raise().insert(
            "workflows",
            [[
                str(workflow.id),
                workflow.name,
                json.dumps(workflow.stage_sequence),
                workflow.status.value,
                workflow.active_stage,
                workflow.approval_status.value,
                workflow.delivery_status.value,
                json.dumps(workflow.provenance.model_dump()),
                workflow.created_at,
                workflow.updated_at,
            ]],
            column_names=[
                "id",
                "name",
                "stage_sequence",
                "status",
                "active_stage",
                "approval_status",
                "delivery_status",
                "provenance",
                "created_at",
                "updated_at",
            ],
        )
        return workflow

    def append_workflow_event(self, event: WorkflowEvent) -> WorkflowEvent:
        event.sequence = self._next_sequence("workflow_events", "workflow_id", event.workflow_id)
        self._client_or_raise().insert(
            "workflow_events",
            [[
                str(event.id),
                str(event.workflow_id),
                event.sequence,
                event.kind,
                event.actor,
                json.dumps(event.payload),
                json.dumps(event.provenance.model_dump()),
                event.occurred_at,
            ]],
            column_names=["id", "workflow_id", "sequence", "kind", "actor", "payload", "provenance", "occurred_at"],
        )
        self._sync_workflow_status(event.workflow_id, event.kind, event.payload, event.occurred_at)
        return event

    def list_workflow_events(self, workflow_id: UUID) -> List[WorkflowEvent]:
        rows = self._query_rows(
            "SELECT * FROM workflow_events WHERE workflow_id = %(workflow_id)s ORDER BY sequence",
            {"workflow_id": str(workflow_id)},
        )
        return [WorkflowEvent(**row) for row in rows]

    def list_agent_runs(self) -> List[AgentRun]:
        rows = self._query_rows("SELECT * FROM agent_runs ORDER BY created_at DESC")
        return [AgentRun(**row) for row in rows]

    def get_agent_run(self, run_id: UUID) -> Optional[AgentRun]:
        rows = self._query_rows("SELECT * FROM agent_runs WHERE id = %(run_id)s LIMIT 1", {"run_id": str(run_id)})
        return AgentRun(**rows[0]) if rows else None

    def create_agent_run(self, run: AgentRun) -> AgentRun:
        self._client_or_raise().insert(
            "agent_runs",
            [[
                str(run.id),
                str(run.workflow_id),
                run.stage_name,
                run.model_name,
                run.runtime_mode,
                run.memory_user_id,
                run.status.value,
                run.prompt,
                run.summary,
                json.dumps(run.provenance.model_dump()),
                run.created_at,
                run.updated_at,
            ]],
            column_names=[
                "id",
                "workflow_id",
                "stage_name",
                "model_name",
                "runtime_mode",
                "memory_user_id",
                "status",
                "prompt",
                "summary",
                "provenance",
                "created_at",
                "updated_at",
            ],
        )
        return run

    def append_agent_event(self, event: AgentEvent) -> AgentEvent:
        event.sequence = self._next_sequence("agent_events", "run_id", event.run_id)
        self._client_or_raise().insert(
            "agent_events",
            [[
                str(event.id),
                str(event.run_id),
                event.sequence,
                event.kind.value,
                event.message,
                json.dumps(event.payload),
                json.dumps(event.provenance.model_dump()),
                event.occurred_at,
            ]],
            column_names=["id", "run_id", "sequence", "kind", "message", "payload", "provenance", "occurred_at"],
        )
        self._sync_agent_status(event.run_id, event.kind, event.occurred_at)
        return event

    def list_agent_events(self, run_id: UUID) -> List[AgentEvent]:
        rows = self._query_rows(
            "SELECT * FROM agent_events WHERE run_id = %(run_id)s ORDER BY sequence",
            {"run_id": str(run_id)},
        )
        return [AgentEvent(**row) for row in rows]

    def list_delivery_records(self) -> List[DeliveryRecord]:
        rows = self._query_rows("SELECT * FROM delivery_records ORDER BY delivered_at DESC")
        return [DeliveryRecord(**row) for row in rows]

    def list_runtime_proposals(self) -> List[Dict[str, Any]]:
        rows = self._query_rows(
            "SELECT * FROM runtime_surgery_proposals ORDER BY created_at, id"
        )
        return [self._catalog_row(row) for row in rows]

    def list_delivery_variants(self) -> List[Dict[str, Any]]:
        rows = self._query_rows(
            "SELECT * FROM delivery_variants ORDER BY created_at, id"
        )
        return [self._catalog_row(row) for row in rows]

    def list_delivery_conflicts(self) -> List[Dict[str, Any]]:
        rows = self._query_rows(
            "SELECT * FROM delivery_conflicts ORDER BY created_at, id"
        )
        return [self._catalog_row(row) for row in rows]

    def create_delivery_record(self, record: DeliveryRecord) -> DeliveryRecord:
        self._client_or_raise().insert(
            "delivery_records",
            [[
                str(record.id),
                str(record.workflow_id),
                record.stage_name,
                record.destination,
                record.status.value,
                record.artifact_uri,
                json.dumps(record.provenance.model_dump()),
                record.delivered_at,
            ]],
            column_names=["id", "workflow_id", "stage_name", "destination", "status", "artifact_uri", "provenance", "delivered_at"],
        )
        self._sync_delivery_status(record.workflow_id, record.status, record.delivered_at)
        return record

    def list_provenance(self) -> List[ProvenanceItem]:
        items: List[ProvenanceItem] = []
        for row in self._query_rows("SELECT id, provenance FROM pipeline_stages ORDER BY sequence"):
            items.append(ProvenanceItem(entity_type="pipeline_stage", entity_id=row["id"], provenance=self._parse_provenance(row["provenance"])))
        for row in self._query_rows("SELECT id, provenance FROM graph_nodes ORDER BY sequence, label"):
            items.append(ProvenanceItem(entity_type="graph_node", entity_id=row["id"], provenance=self._parse_provenance(row["provenance"])))
        for row in self._query_rows("SELECT id, provenance FROM graph_edges ORDER BY created_at, id"):
            items.append(ProvenanceItem(entity_type="graph_edge", entity_id=row["id"], provenance=self._parse_provenance(row["provenance"])))
        for row in self._query_rows("SELECT id, provenance FROM workflows ORDER BY created_at DESC"):
            items.append(ProvenanceItem(entity_type="workflow", entity_id=row["id"], provenance=self._parse_provenance(row["provenance"])))
        for row in self._query_rows("SELECT id, provenance FROM agent_runs ORDER BY created_at DESC"):
            items.append(ProvenanceItem(entity_type="agent_run", entity_id=row["id"], provenance=self._parse_provenance(row["provenance"])))
        for row in self._query_rows("SELECT id, provenance FROM delivery_records ORDER BY delivered_at DESC"):
            items.append(ProvenanceItem(entity_type="delivery_record", entity_id=row["id"], provenance=self._parse_provenance(row["provenance"])))
        for table, entity_type in (
            ("runtime_surgery_proposals", "runtime_proposal"),
            ("delivery_variants", "delivery_variant"),
            ("delivery_conflicts", "delivery_conflict"),
        ):
            for row in self._query_rows(f"SELECT id, provenance FROM {table} ORDER BY created_at, id"):
                items.append(ProvenanceItem(entity_type=entity_type, entity_id=row["id"], provenance=self._parse_provenance(row["provenance"])))
        return items

    def graph_contract(self) -> GraphContractSummary:
        stages = self.list_pipeline_stages()
        nodes = self.list_graph_nodes()
        edges = self.list_graph_edges()
        return GraphContractSummary(
            node_kinds=[node.kind for node in nodes],
            edge_relations=sorted({edge.relation for edge in edges}),
            stage_names=[stage.name for stage in stages],
        )

    def _query_rows(self, sql: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        result = self._client_or_raise().query(sql, parameters=parameters or {})
        rows = list(result.named_results())
        for row in rows:
            self._decode_row(row)
        return rows

    def _decode_row(self, row: Dict[str, Any]) -> None:
        for key in ("payload", "metadata", "provenance", "stage_sequence"):
            if key in row and isinstance(row[key], str):
                try:
                    row[key] = json.loads(row[key])
                except Exception:
                    row[key] = {} if key != "stage_sequence" else []

    def _parse_provenance(self, value: Any) -> Provenance:
        if isinstance(value, Provenance):
            return value
        if isinstance(value, str):
            try:
                return Provenance(**json.loads(value))
            except Exception:
                return Provenance()
        if isinstance(value, dict):
            return Provenance(**value)
        return Provenance()

    def _catalog_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Make ClickHouse catalog rows JSON-safe at the API boundary."""
        normalized = dict(row)
        for key in ("id", "film_id", "revision_id", "node_id", "variant_id"):
            value = normalized.get(key)
            if value is not None and not isinstance(value, str):
                normalized[key] = str(value)
        created_at = normalized.get("created_at")
        if isinstance(created_at, datetime):
            normalized["created_at"] = created_at.isoformat()
        if "provenance" in normalized:
            normalized["provenance"] = self._parse_provenance(normalized["provenance"]).model_dump()
        return normalized

    def _next_sequence(self, table: str, key_field: str, value: UUID) -> int:
        rows = self._query_rows(
            "SELECT coalesce(max(sequence), 0) AS sequence FROM {table} WHERE {key_field} = %(value)s".format(
                table=table,
                key_field=key_field,
            ),
            {"value": str(value)},
        )
        return int(rows[0]["sequence"]) + 1 if rows else 1

    def _sync_workflow_status(self, workflow_id: UUID, kind: str, payload: Dict[str, Any], occurred_at: datetime) -> None:
        status = None
        active_stage = None
        approval_status = None
        delivery_status = None
        if kind == "workflow.started":
            status = WorkflowStatus.running.value
            active_stage = payload.get("stage")
        elif kind == "workflow.completed":
            status = WorkflowStatus.complete.value
        elif kind == "workflow.failed":
            status = WorkflowStatus.failed.value
        elif kind == "workflow.approval_requested":
            approval_status = ApprovalStatus.pending.value
        elif kind == "workflow.approved":
            approval_status = ApprovalStatus.approved.value
        elif kind == "workflow.rejected":
            approval_status = ApprovalStatus.rejected.value
        elif kind == "workflow.delivery_ready":
            delivery_status = DeliveryStatus.ready.value
        elif kind == "workflow.delivered":
            delivery_status = DeliveryStatus.delivered.value
            status = WorkflowStatus.complete.value
        if status is not None or active_stage is not None or approval_status is not None or delivery_status is not None:
            updates = []
            params: Dict[str, Any] = {"workflow_id": str(workflow_id), "updated_at": occurred_at}
            if status is not None:
                updates.append("status = %(status)s")
                params["status"] = status
            if active_stage is not None:
                updates.append("active_stage = %(active_stage)s")
                params["active_stage"] = active_stage
            if approval_status is not None:
                updates.append("approval_status = %(approval_status)s")
                params["approval_status"] = approval_status
            if delivery_status is not None:
                updates.append("delivery_status = %(delivery_status)s")
                params["delivery_status"] = delivery_status
            updates.append("updated_at = %(updated_at)s")
            self._client_or_raise().command(
                "ALTER TABLE workflows UPDATE {updates} WHERE id = %(workflow_id)s".format(updates=", ".join(updates)),
                params,
            )

    def _sync_agent_status(self, run_id: UUID, kind: AgentEventKind, occurred_at: datetime) -> None:
        status = None
        summary = None
        if kind == AgentEventKind.started:
            status = WorkflowStatus.running.value
        elif kind == AgentEventKind.completed:
            status = WorkflowStatus.complete.value
            summary = "agent run complete"
        elif kind == AgentEventKind.failed:
            status = WorkflowStatus.failed.value
        if status is not None:
            params: Dict[str, Any] = {"run_id": str(run_id), "updated_at": occurred_at, "status": status}
            updates = ["status = %(status)s", "updated_at = %(updated_at)s"]
            if summary is not None:
                updates.append("summary = %(summary)s")
                params["summary"] = summary
            self._client_or_raise().command(
                "ALTER TABLE agent_runs UPDATE {updates} WHERE id = %(run_id)s".format(updates=", ".join(updates)),
                params,
            )

    def _sync_delivery_status(self, workflow_id: UUID, status: DeliveryStatus, delivered_at: datetime) -> None:
        params: Dict[str, Any] = {
            "delivery_status": status.value,
            "updated_at": delivered_at,
            "workflow_id": str(workflow_id),
        }
        updates = ["delivery_status = %(delivery_status)s", "updated_at = %(updated_at)s"]
        if status == DeliveryStatus.delivered:
            updates.insert(0, "status = %(status)s")
            params["status"] = WorkflowStatus.complete.value
        self._client_or_raise().command(
            "ALTER TABLE workflows UPDATE {updates} WHERE id = %(workflow_id)s".format(updates=", ".join(updates)),
            params,
        )

    def _execute_sql_file(
        self,
        client: Any,
        path: Path,
        database_override: Optional[str] = None,
        create_database: bool = True,
    ) -> None:
        if not path.exists():
            return
        buffer: List[str] = []
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue
            buffer.append(line)
            if stripped.endswith(";"):
                sql = "\n".join(buffer).strip().rstrip(";")
                if sql:
                    sql = _override_database_directives(sql, database_override, create_database=create_database)
                    if sql.strip():
                        self._execute_sql_statement(client, sql, database_override)
                buffer = []
        if buffer:
            sql = "\n".join(buffer).strip().rstrip(";")
            if sql:
                sql = _override_database_directives(sql, database_override, create_database=create_database)
                if sql.strip():
                    self._execute_sql_statement(client, sql, database_override)

    @staticmethod
    def _execute_sql_statement(client: Any, sql: str, database_override: Optional[str]) -> None:
        """Execute one init statement against the requested database.

        ``clickhouse-connect`` sends the database as an HTTP query parameter;
        a standalone ``USE`` statement is not a reliable session switch when
        session IDs are disabled. Keep CREATE DATABASE/USE on the default
        connection, then set the client's database before every DDL/INSERT so
        Cloud bootstrap cannot silently seed the default database.
        """
        first_word = sql.lstrip().split(None, 2)[:2]
        is_database_directive = bool(first_word and first_word[0].upper() == "CREATE" and len(first_word) > 1 and first_word[1].upper() == "DATABASE") or (first_word and first_word[0].upper() == "USE")
        if database_override and not is_database_directive:
            client.database = database_override
        client.command(sql, use_database=not is_database_directive)
        if database_override and first_word and first_word[0].upper() == "USE":
            client.database = database_override


_DATABASE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_identifier(value: str) -> str:
    """Quote a configured ClickHouse database after strict validation."""
    if not _DATABASE_IDENTIFIER.fullmatch(value):
        raise ValueError("ClickHouse database must contain only letters, numbers, and underscores")
    return f"`{value}`"


def _override_database_directives(
    sql: str,
    database_override: Optional[str],
    *,
    create_database: bool = True,
) -> str:
    if not database_override:
        return sql
    quoted = _quote_identifier(database_override)
    # Only replace the two standalone directives at the beginning of the
    # checked-in init files.  This avoids changing data such as local://filmgraph
    # artifact URIs in INSERT statements.
    create_pattern = r"CREATE\s+DATABASE\s+IF\s+NOT\s+EXISTS\s+filmgraph\s*;?"
    sql = re.sub(
        create_pattern,
        f"CREATE DATABASE IF NOT EXISTS {quoted}" if create_database else "",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
    sql = re.sub(r"\bUSE\s+filmgraph\b", f"USE {quoted}", sql, count=1, flags=re.IGNORECASE)
    return sql
