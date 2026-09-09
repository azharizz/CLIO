from __future__ import annotations

from uuid import UUID

from filmgraph.graph_queries import recursive_impact_query, recursive_lineage_query
from filmgraph.models import GraphNodeKind
from filmgraph.repositories.clickhouse import ClickHouseFilmGraphRepository
from filmgraph.settings import ClickHouseSettings


class Result:
    def __init__(self, rows):
        self.rows = rows

    def named_results(self):
        return [dict(row) for row in self.rows]


class RecursiveClient:
    def __init__(self):
        self.queries = []

    def query(self, sql, parameters=None):
        self.queries.append((sql, parameters or {}))
        return Result([
            {
                "id": "40101010-1010-1010-1010-101010101047",
                "kind": "scene",
                "label": "MOVING CAR — NIGHT",
                "sequence": 6,
                "stage_name": "Script",
                "status": "breaking",
                "film_id": "demo-feature",
                "revision_id": "rev-05",
                "scene_number": "47",
                "metadata": "{}",
                "provenance": '{"source":"direct_clickhouse"}',
            }
        ])


def test_recursive_queries_track_paths_and_bound_depth():
    lineage = recursive_lineage_query()
    impact = recursive_impact_query()

    for query in (lineage, impact):
        assert "WITH RECURSIVE" in query
        assert "arrayConcat" in query
        assert "NOT has" in query
        assert "depth < 32" in query
        assert "%(node_id)s" in query

    assert "edge_directions" in impact
    assert "edge.target_id" in lineage


def test_clickhouse_repository_uses_recursive_queries_before_python_fallback():
    repository = ClickHouseFilmGraphRepository(ClickHouseSettings("localhost", 8123, "default", "", "filmgraph", False))
    client = RecursiveClient()
    repository._client = client
    node_id = UUID("40101010-1010-1010-1010-101010101047")

    impact = repository.get_node_impact(node_id)
    lineage = repository.get_lineage(node_id)

    assert impact[0].kind == GraphNodeKind.scene
    assert lineage[0].scene_number == "47"
    assert len(client.queries) == 2
    assert "WITH RECURSIVE" in client.queries[0][0]
    assert "WITH RECURSIVE" in client.queries[1][0]
    assert all(query[1] == {"node_id": str(node_id)} for query in client.queries)
