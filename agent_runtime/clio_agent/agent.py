"""Google ADK definition for the managed CLIO continuity agent.

Cloud Run owns the durable run record and sends a compact, current ClickHouse
graph snapshot to this agent. The managed runtime owns the model turn,
session, and Memory Bank integration. A human approval is always required for
any graph mutation.
"""

from __future__ import annotations

import os
import json
import urllib.parse
import urllib.request
from typing import Any

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types


MODEL = os.getenv("CLIO_AGENT_MODEL", "gemini-3.8-flash")
API_BASE_URL = os.getenv("CLIO_AGENT_API_BASE_URL", "").rstrip("/")


def _read_clio(path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
    """Call CLIO's read-only evidence boundary from Agent Runtime.

    The agent never has ClickHouse credentials and cannot make a graph write.
    Cloud Run selects MCP-first or direct ClickHouse internally and returns
    provenance with each graph result.
    """
    if not API_BASE_URL:
        return {"available": False, "error": "CLIO_AGENT_API_BASE_URL is not configured"}
    suffix = f"?{urllib.parse.urlencode(query)}" if query else ""
    request = urllib.request.Request(
        f"{API_BASE_URL}/api/v1/agent-tools/{path.lstrip('/')}{suffix}",
        headers={"Accept": "application/json", "User-Agent": "clio-adk-agent/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {"available": False, "error": "invalid CLIO tool response"}
    except Exception as exc:  # Tool errors become evidence, not agent writes.
        return {"available": False, "error": f"CLIO read tool unavailable: {exc}"}


def get_node_impact(node_id: str) -> dict[str, Any]:
    """Read the selected node and its dependency-impact neighborhood."""
    return _read_clio(f"nodes/{urllib.parse.quote(node_id, safe='')}/impact")


def get_lineage(node_id: str) -> dict[str, Any]:
    """Read upstream lineage for a selected script node."""
    return _read_clio(f"nodes/{urllib.parse.quote(node_id, safe='')}/lineage")


def get_timing(node_id: str) -> dict[str, Any]:
    """Read exact persisted timing for the selected node and active film."""
    return _read_clio(f"nodes/{urllib.parse.quote(node_id, safe='')}/timing")


def search_script(query: str) -> dict[str, Any]:
    """Search narration and screenplay text for continuity evidence."""
    return _read_clio("script/search", {"query": query[:120]})


def get_revision_context() -> dict[str, Any]:
    """Read the active film/revision identity before making a proposal."""
    return _read_clio("revision")


def calculate_runtime_after_removal(
    film_duration_seconds: int,
    node_duration_seconds: int,
) -> dict[str, int]:
    """Return deterministic timing math for a proposed node removal.

    Use this only after reading the graph context. It does not alter the
    screenplay or approve a removal.
    """
    return {
        "before_seconds": max(0, film_duration_seconds),
        "removed_seconds": max(0, node_duration_seconds),
        "after_seconds": max(0, film_duration_seconds - node_duration_seconds),
    }


def critic_check(
    proposal: str,
    affected_node_ids: list[str],
) -> dict[str, Any]:
    """Perform a final deterministic safety check; this tool cannot approve."""
    lower = proposal.lower()
    forbidden_claims = [word for word in ("deleted", "changed", "approved", "applied", "removed") if f"i {word}" in lower]
    return {
        "checked": True,
        "affected_node_ids": affected_node_ids[:32],
        "evidence_attached": bool(affected_node_ids),
        "approval_required": True,
        "forbidden_mutation_claims": forbidden_claims,
        "verdict": "revise" if forbidden_claims or not affected_node_ids else "proposal_ready_for_human_review",
    }


root_agent = Agent(
    name="clio_continuity_operator",
    model=Gemini(
        model=MODEL,
        client_kwargs={
            "vertexai": True,
            "project": os.getenv("GOOGLE_CLOUD_PROJECT"),
            # Gemini 3.x is served from the global Vertex endpoint while
            # Agent Runtime itself remains in a supported regional location.
            "location": os.getenv("CLIO_AGENT_VERTEX_LOCATION", "global"),
        },
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are CLIO — Continuity & Lineage Intelligence Operator.

You are a bounded evidence-gathering agent, not a chatbot that guesses.
For every request, first identify the selected node from GRAPH_CONTEXT and
read the active revision plus at least one relevant read-only graph tool.
For edit/remove/add, call get_node_impact and get_lineage. For removal, also
call get_timing and calculate_runtime_after_removal. Search script narration
only when it will resolve a concrete continuity question. Make no more than
three evidence reads before synthesizing a proposal.

Then state affected node IDs, provenance/uncertainty, timing delta when known,
and the human decision required. Before your final answer, call critic_check
with the concise proposed recommendation and its affected node IDs. If the
critic says revise, correct the proposal. A recommendation is only a proposal:
never claim you changed, deleted, approved, applied, or delivered anything.
Managed Memory Bank may provide durable approved editorial preferences for the
current user; use it only when relevant and never treat it as screenplay truth.
""",
    tools=[
        get_revision_context,
        get_node_impact,
        get_lineage,
        get_timing,
        search_script,
        calculate_runtime_after_removal,
        critic_check,
    ],
)
