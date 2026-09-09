"""Agent provider seam shared by the local simulator and future ADK mode."""

from __future__ import annotations

import asyncio
import json
import re
import urllib.request
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
class OpenRouterAdkAgentProvider:
    """Real tool-using provider behind the Google ADK-compatible agent seam.

    OpenRouter exposes an OpenAI-compatible chat endpoint, so the local agent
    can use DeepSeek now while retaining the same event/tool contract that a
    Vertex Gemini ADK adapter will implement later.
    """

    api_key: str
    url: str
    model: str
    runtime_mode: str = "live"

    def _request(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "HTTP-Referer": "http://127.0.0.1:3000",
                "X-Title": "CLIO local agent",
            },
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, dict) or not isinstance(decoded.get("choices"), list) or not decoded["choices"]:
            raise RuntimeError(f"provider returned no choices: {str(decoded)[:300]}")
        message = decoded["choices"][0].get("message")
        if not isinstance(message, dict):
            raise RuntimeError("provider response did not include a message")
        return message

    @staticmethod
    def _tool_result(name: str, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        nodes = [node for node in context.get("graph_nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in context.get("graph_edges", []) if isinstance(edge, dict)]
        focus = str(arguments.get("node_id") or context.get("focus_node") or "")
        if focus and not any(str(node.get("id")) == focus for node in nodes):
            scene = focus.removeprefix("scene-").removeprefix("SC ").strip()
            focus = next((str(node.get("id")) for node in nodes if str(node.get("scene_number")) == scene), focus)
        if name == "get_node_impact":
            adjacent = [edge for edge in edges if str(edge.get("source_id")) == focus or str(edge.get("target_id")) == focus]
            ids = {focus} | {str(edge.get("source_id")) for edge in adjacent} | {str(edge.get("target_id")) for edge in adjacent}
            return {"focus_node": focus, "nodes": [node for node in nodes if str(node.get("id")) in ids], "relations": adjacent}
        if name == "get_lineage":
            incoming = {str(edge.get("target_id")): str(edge.get("source_id")) for edge in edges}
            chain: list[str] = []
            current = focus
            while current and current not in chain:
                chain.append(current)
                current = incoming.get(current, "")
            return {"lineage": [node for node in nodes if str(node.get("id")) in chain]}
        if name == "get_timing":
            durations = [int(node.get("duration_seconds") or 0) for node in nodes]
            target = next((node for node in nodes if str(node.get("id")) == focus), {})
            return {"focus_duration_seconds": target.get("duration_seconds"), "film_duration_seconds": max((int(node.get("end_seconds") or 0) for node in nodes), default=0), "scene_count": sum(node.get("kind") == "scene" for node in nodes)}
        if name == "get_revision":
            return {"revision": "V5", "change": "INTERIOR RESTAURANT → MOVING CAR", "source": "LOCAL DEMO"}
        raise ValueError(f"unknown agent tool: {name}")

    async def start_run(self, context: dict[str, Any]) -> AsyncIterator[AgentEvent]:
        run_id = UUID(str(context["run_id"]))
        prompt = str(context.get("prompt") or "Inspect the active script revision.")
        provenance = Provenance(source="gemini_adk", transport="openrouter", adapter="adk-tool-agent", runtime_mode="live", model_name=self.model)
        yield AgentEvent(run_id=run_id, kind=AgentEventKind.progress, message="phase:narrative", payload={"phase": "narrative", "notes": "Real agent reading the screenplay graph and narration."}, provenance=provenance, occurred_at=utcnow())
        tools = [
            {"type": "function", "function": {"name": "get_node_impact", "description": "Read the directly connected impact neighborhood for a node.", "parameters": {"type": "object", "properties": {"node_id": {"type": "string"}}, "required": ["node_id"]}}},
            {"type": "function", "function": {"name": "get_lineage", "description": "Read upstream script lineage for a node.", "parameters": {"type": "object", "properties": {"node_id": {"type": "string"}}, "required": ["node_id"]}}},
            {"type": "function", "function": {"name": "get_timing", "description": "Read exact start/end/duration timing for the active graph.", "parameters": {"type": "object", "properties": {"node_id": {"type": "string"}}, "required": ["node_id"]}}},
            {"type": "function", "function": {"name": "get_revision", "description": "Read the active revision metadata.", "parameters": {"type": "object", "properties": {}}}},
        ]
        compact_context = {"prompt": prompt, "focus_node": context.get("focus_node"), "graph_nodes": context.get("graph_nodes", []), "graph_edges": context.get("graph_edges", [])}
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "You are CLIO, a screenplay continuity and lineage agent. Use tools before recommending. Return concise, actionable analysis with affected scenes, timing deltas, and a human approval step. Never claim to have changed data."},
            {"role": "user", "content": json.dumps(compact_context, ensure_ascii=False)},
        ]
        final_text = ""
        # Two rounds are enough for a genuine tool-using turn (plan/read, then
        # synthesize) while keeping the local SSE interaction responsive.
        for _ in range(2):
            message = await asyncio.to_thread(self._request, messages, tools)
            tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
            messages.append(message)
            if not tool_calls:
                final_text = str(message.get("content") or "No recommendation returned.")
                break
            for call in tool_calls:
                function = call.get("function") if isinstance(call, dict) else {}
                name = str(function.get("name") or "")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                yield AgentEvent(run_id=run_id, kind=AgentEventKind.tool_call, message="phase:graph", payload={"phase": "graph", "tool": name, "arguments": arguments, "notes": f"Calling read-only graph tool: {name}."}, provenance=provenance, occurred_at=utcnow())
                result = self._tool_result(name, arguments, context)
                yield AgentEvent(run_id=run_id, kind=AgentEventKind.tool_result, message="phase:analytics", payload={"phase": "analytics", "tool": name, "result": result, "notes": "Tool result returned to the agent."}, provenance=provenance, occurred_at=utcnow())
                messages.append({"role": "tool", "tool_call_id": call.get("id", name), "content": json.dumps(result, ensure_ascii=False)})
        yield AgentEvent(run_id=run_id, kind=AgentEventKind.message, message="phase:revision", payload={"phase": "revision", "notes": final_text}, provenance=provenance, occurred_at=utcnow())
        yield AgentEvent(run_id=run_id, kind=AgentEventKind.completed, message="phase:critic", payload={"phase": "critic", "assessment": "Provider recommendation is a proposal; editorial approval is still required.", "recommendation": final_text}, provenance=provenance, occurred_at=utcnow())


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
        provider_key = credentials.get("provider_key") or credentials.get("api_key")
        provider_url = credentials.get("provider_url")
        provider_model = credentials.get("model_name")
        if provider_key and provider_url and provider_model:
            return OpenRouterAdkAgentProvider(api_key=str(provider_key), url=str(provider_url), model=str(provider_model))
        return GeminiAdkAgentProvider(
            api_key=credentials.get("api_key"),
            project=credentials.get("project"),
            location=credentials.get("location"),
        )
    return SimulatedAgentProvider()
