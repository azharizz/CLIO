"""Agent provider seam shared by the local simulator and future ADK mode."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from filmgraph.models import AgentEvent, AgentEventKind, Provenance, utcnow


class AgentProvider(Protocol):
    """A provider emits the same ordered event shape in every runtime."""

    async def start_run(self, context: dict[str, Any]) -> AsyncIterator[AgentEvent]:
        ...


def _label(node: dict[str, Any]) -> str:
    number = node.get("scene_number")
    beat = node.get("beat_number")
    if number and beat is not None:
        return f"SC {number} / B{int(beat):02d}"
    return f"SC {number}" if number else str(node.get("label") or node.get("id") or "NODE")


def _timed(node: dict[str, Any]) -> int:
    value = node.get("duration_seconds")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    try:
        return int(node.get("end_seconds", 0)) - int(node.get("start_seconds", 0))
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class SimulatedAgentProvider:
    """Small live-feeling stream; recommendations are proposals, never writes."""

    runtime_mode: str = "simulation"

    async def start_run(self, context: dict[str, Any]) -> AsyncIterator[AgentEvent]:
        run_id = UUID(str(context["run_id"]))
        prompt = str(context.get("prompt") or "Inspect the active script revision.")
        lower_prompt = prompt.lower()
        explicit_action = re.search(r"\[(inspect|edit|remove|add) node\]", prompt, flags=re.IGNORECASE)
        if explicit_action:
            action = explicit_action.group(1).lower()
        elif re.search(r"\b(remove|delete)\b", lower_prompt):
            action = "remove"
        elif re.search(r"\b(add|insert)\b", lower_prompt):
            action = "add"
        elif re.search(r"\b(edit|change)\b", lower_prompt):
            action = "edit"
        else:
            action = "inspect"

        nodes = [item for item in context.get("graph_nodes", []) if isinstance(item, dict)]
        edges = [item for item in context.get("graph_edges", []) if isinstance(item, dict)]
        focus_value = str(context.get("focus_node") or "")
        focus_match = re.search(r"\[FOCUS:([^\]]+)\]", prompt, flags=re.IGNORECASE)
        if not focus_value and focus_match:
            focus_value = focus_match.group(1).strip()
        focus = next((node for node in nodes if str(node.get("id")) == focus_value), None)
        if focus is None:
            wanted = focus_value.replace("SC ", "").strip().lower()
            focus = next((node for node in nodes if str(node.get("scene_number", "")).lower() == wanted), None)
        if focus is None:
            focus = next((node for node in nodes if str(node.get("scene_number", "")) == "47"), None)
        if focus is None and nodes:
            focus = nodes[0]
        focus = focus or {"id": "scene-47", "scene_number": "47", "label": "SC 47"}
        focus_id = str(focus.get("id"))

        by_id = {str(node.get("id")): node for node in nodes}

        # A scene can have more than one relationship to the same neighbor
        # (for example, SC 47 both follows and pays off into SC 48). Keep the
        # agent answer about affected scenes, not about duplicate edge rows.
        parents: dict[str, list[str]] = {}
        children: dict[str, list[str]] = {}
        for edge in edges:
            source_id = str(edge.get("source_id") or "")
            target_id = str(edge.get("target_id") or "")
            if source_id and target_id:
                children.setdefault(source_id, [])
                parents.setdefault(target_id, [])
                if target_id not in children[source_id]:
                    children[source_id].append(target_id)
                if source_id not in parents[target_id]:
                    parents[target_id].append(source_id)

        upstream_ids = parents.get(focus_id, [])
        downstream_ids = children.get(focus_id, [])

        def reachable(start_ids: list[str], adjacency: dict[str, list[str]]) -> list[str]:
            seen: set[str] = set()
            ordered: list[str] = []
            queue = list(start_ids)
            while queue:
                current = queue.pop(0)
                if current in seen or current == focus_id:
                    continue
                seen.add(current)
                ordered.append(current)
                queue.extend(adjacency.get(current, []))
            return ordered

        affected_ids = reachable(downstream_ids, children)
        upstream = " · ".join(_label(by_id[item]) for item in upstream_ids if item in by_id) or "START"
        downstream = " · ".join(_label(by_id[item]) for item in downstream_ids if item in by_id) or "END"
        affected_nodes = [by_id[item] for item in affected_ids if item in by_id]
        affected_scene_labels = []
        for item in affected_nodes:
            if item.get("kind") == "beat":
                continue
            label = _label(item)
            if label not in affected_scene_labels:
                affected_scene_labels.append(label)
        affected = " · ".join(affected_scene_labels) or downstream
        focus_is_beat = focus.get("kind") == "beat"
        if focus_is_beat:
            beat_targets = [item for item in affected_nodes if item.get("kind") == "beat"]
            beat_labels = " · ".join(_label(item) for item in beat_targets) or "NO DEPENDENT BEATS"
            parent = by_id.get(str(focus.get("parent_scene_id") or ""))
            affected = f"{_label(parent)} → BEATS {beat_labels}" if parent else f"BEATS {beat_labels}"
        child_beats = [node for node in nodes if node.get("kind") == "beat" and str(node.get("parent_scene_id")) == focus_id]
        if focus_is_beat:
            parent = by_id.get(str(focus.get("parent_scene_id") or ""))
            child_beats = [node for node in nodes if node.get("kind") == "beat" and str(node.get("parent_scene_id")) == str(focus.get("parent_scene_id") or "")]
        beat_summary = " · ".join(_label(item) for item in sorted(child_beats, key=lambda item: int(item.get("beat_number") or 0))) or "NONE"
        duration = _timed(focus)
        total = max((_timed(node) + int(node.get("start_seconds", 0) or 0) for node in nodes), default=0)
        after_remove = max(0, total - duration)

        graph_note = {
            "inspect": f"UPSTREAM: {upstream} · DOWNSTREAM: {downstream} · CHILD BEATS: {beat_summary}",
            "edit": f"AFFECTED: {('BEAT PATH ' if focus_is_beat else 'SCENES ')}{affected} · CHILD BEATS: {beat_summary}",
            "remove": f"UNNEEDED IF REMOVED: {affected} · CHILD BEATS: {beat_summary} · FILM AFTER {after_remove // 60:02d}:{after_remove % 60:02d}",
            "add": f"POSSIBLE CONNECTIONS: {upstream} → NEW → {downstream}",
        }[action]
        analytics_note = (
            f"{_label(focus)} {duration // 60:02d}:{duration % 60:02d} removed · "
            f"{total // 60:02d}:{total % 60:02d} → {after_remove // 60:02d}:{after_remove % 60:02d}"
            if action == "remove"
            else f"FOCUS {duration // 60:02d}:{duration % 60:02d} · FILM TOTAL {total // 60:02d}:{total % 60:02d}"
        )
        notes = {
            "inspect": "No write proposed; map the script path first.",
            "edit": "Proposal only; review every affected scene before changing text.",
            "remove": "Proposal only; check continuity and timing before removing a scene.",
            "add": "Proposal only; choose a human-approved connection before inserting text.",
        }[action]
        provenance = Provenance(
            source="agent_simulation",
            transport="provider",
            adapter="simulated-agent",
            runtime_mode="simulation",
            model_name="gemini-simulated",
        )
        events = [
            (AgentEventKind.progress, "phase:narrative", {"phase": "narrative", "action": action, "focus": _label(focus), "notes": f"Reading {_label(focus)} action and narration: {focus.get('narration_text') or 'no narration line'}"}),
            (AgentEventKind.tool_call, "phase:graph", {"phase": "graph", "action": action, "focus": _label(focus), "node_count": len(nodes), "notes": graph_note}),
            (AgentEventKind.message, "phase:analytics", {"phase": "analytics", "action": action, "focus": _label(focus), "notes": analytics_note, "duration_seconds": duration, "film_duration_seconds": total}),
            (AgentEventKind.tool_result, "phase:revision", {"phase": "revision", "action": action, "focus": _label(focus), "revision": "V5", "change": "INTERIOR RESTAURANT → MOVING CAR", "notes": "Revision text remains the source of truth."}),
            (AgentEventKind.completed, "phase:critic", {"phase": "critic", "action": action, "focus": _label(focus), "assessment": notes, "prompt": prompt}),
        ]
        for kind, message, payload in events:
            await asyncio.sleep(0)
            yield AgentEvent(run_id=run_id, kind=kind, message=message, payload=payload, provenance=provenance, occurred_at=utcnow())


@dataclass(frozen=True)
class GeminiAdkAgentProvider:
    """Explicit seam for the eventual live Gemini/ADK implementation."""

    api_key: str | None = None
    project: str | None = None
    location: str | None = None

    async def start_run(self, context: dict[str, Any]) -> AsyncIterator[AgentEvent]:
        raise RuntimeError(
            "Gemini/ADK live provider is a configured seam in the local build; "
            "use AGENT_MODE=simulated until the provider is wired."
        )


def provider_for(mode: str, **credentials: Any) -> AgentProvider:
    normalized = "simulation" if mode == "simulated" else mode
    if normalized == "live":
        return GeminiAdkAgentProvider(
            api_key=credentials.get("api_key"),
            project=credentials.get("project"),
            location=credentials.get("location"),
        )
    return SimulatedAgentProvider()
