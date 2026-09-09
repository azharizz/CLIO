from __future__ import annotations

import json
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
        # application database.  Passing a not-yet-created database to the
        # HTTP client can make the first CREATE DATABASE command fail.
        client = self._client or self._create_client("__default__")
        self._client = client
        init_dir = Path(__file__).resolve().parents[3] / "infra" / "clickhouse" / "init"
        self._execute_sql_file(client, init_dir / "001_schema.sql")
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
            beat_rows = self._query_rows("SELECT count() AS count FROM graph_nodes WHERE kind = 'beat'")
            # Sixteen child beats are part of the current local script seed.
            if not beat_rows or int(beat_rows[0]["count"]) != 16:
                stale = True
        except Exception:
            stale = True
        if not counts or int(counts[0]["count"]) != 1 or stale:
            self._clear_local_demo_tables(client)
            self._execute_sql_file(client, init_dir / "002_seed.sql")
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
        if self._settings.database != "filmgraph":
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
            summary = "simulation complete"
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

    def _execute_sql_file(self, client: Any, path: Path) -> None:
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
                    client.command(sql, use_database=False)
                buffer = []
        if buffer:
            sql = "\n".join(buffer).strip().rstrip(";")
            if sql:
                client.command(sql, use_database=False)
