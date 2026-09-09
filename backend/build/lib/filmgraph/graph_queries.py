"""Parameterized ClickHouse graph traversals shared by direct and MCP reads.

The graph itself stays in the append-friendly ``graph_nodes`` and
``graph_edges`` tables.  Traversal state (depth and cycle-safe path) is kept in
the recursive CTE, so no derived closure table has to be invalidated after a
human node edit.
"""

from __future__ import annotations


MAX_TRAVERSAL_DEPTH = 32


def recursive_lineage_query(max_depth: int = MAX_TRAVERSAL_DEPTH) -> str:
    """Return an upstream traversal rooted at ``%(node_id)s``.

    ``film_id`` and ``revision_id`` are carried through the CTE so an edge
    cannot accidentally cross screenplay snapshots when a database contains
    more than the local demo revision.
    """

    depth = max(1, min(int(max_depth), 255))
    return f"""
WITH RECURSIVE lineage AS
(
    SELECT
        toString(id) AS node_id,
        film_id,
        revision_id,
        toUInt32(0) AS depth,
        [toString(id)] AS path
    FROM graph_nodes
    WHERE id = toUUID(%(node_id)s)

    UNION ALL

    SELECT
        toString(parent.id) AS node_id,
        parent.film_id,
        parent.revision_id,
        lineage.depth + 1 AS depth,
        arrayConcat(lineage.path, [toString(parent.id)]) AS path
    FROM lineage
    INNER JOIN graph_edges AS edge
        ON edge.target_id = toUUID(lineage.node_id)
    INNER JOIN graph_nodes AS parent
        ON parent.id = edge.source_id
       AND parent.film_id = lineage.film_id
       AND parent.revision_id = lineage.revision_id
    WHERE lineage.depth < {depth}
      AND NOT has(lineage.path, toString(parent.id))
)
SELECT node.*
FROM
(
    SELECT node_id, max(depth) AS traversal_depth
    FROM lineage
    GROUP BY node_id
) AS walk
INNER JOIN graph_nodes AS node
    ON node.id = toUUID(walk.node_id)
ORDER BY walk.traversal_depth DESC, node.sequence, node.id
""".strip()


def recursive_impact_query(max_depth: int = MAX_TRAVERSAL_DEPTH) -> str:
    """Return the cycle-safe undirected connected neighborhood of a node."""

    depth = max(1, min(int(max_depth), 255))
    return f"""
WITH RECURSIVE
edge_directions AS
(
    SELECT source_id AS from_id, target_id AS to_id FROM graph_edges
    UNION ALL
    SELECT target_id AS from_id, source_id AS to_id FROM graph_edges
),
impact AS
(
    SELECT
        toString(id) AS node_id,
        film_id,
        revision_id,
        toUInt32(0) AS depth,
        [toString(id)] AS path
    FROM graph_nodes
    WHERE id = toUUID(%(node_id)s)

    UNION ALL

    SELECT
        toString(next_node.id) AS node_id,
        next_node.film_id,
        next_node.revision_id,
        impact.depth + 1 AS depth,
        arrayConcat(impact.path, [toString(next_node.id)]) AS path
    FROM impact
    INNER JOIN edge_directions AS direction
        ON direction.from_id = toUUID(impact.node_id)
    INNER JOIN graph_nodes AS next_node
        ON next_node.id = direction.to_id
       AND next_node.film_id = impact.film_id
       AND next_node.revision_id = impact.revision_id
    WHERE impact.depth < {depth}
      AND NOT has(impact.path, toString(next_node.id))
)
SELECT node.*
FROM
(
    SELECT node_id, min(depth) AS traversal_depth
    FROM impact
    GROUP BY node_id
) AS walk
INNER JOIN graph_nodes AS node
    ON node.id = toUUID(walk.node_id)
ORDER BY walk.traversal_depth, node.sequence, node.id
""".strip()
