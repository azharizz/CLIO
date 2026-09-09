"""GitHub-backed screenplay loading for the Script Git workflow.

The app deliberately treats GitHub as a read-side source of screenplay
revisions.  A loaded file is parsed into the same small graph contract used by
the local demo (revision -> scene -> beat); applying it is still a separate
human action handled by the repository and an append-only workflow event.

No GitHub SDK is required.  The REST calls use the standard library so the
local backend stays easy to run in a clean Python environment and can later be
swapped for an authenticated GitHub App.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID, uuid5

from filmgraph.models import GraphEdge, GraphNode, GraphNodeKind, Provenance, utcnow


SCRIPT_NAMESPACE = UUID("7b7b7b7b-1111-4222-8333-aaaaaaaaaaaa")
MAX_SCRIPT_BYTES = 750_000
DEFAULT_HISTORY_LIMIT = 12
DEMO_OWNER = "owner"
DEMO_REPO = "repository"
DEMO_PATH = "script.fountain"
DEMO_MAIN_SHA = "clio-demo-main-0001"
DEMO_BEFORE_SHA = "clio-demo-before-0001"

# The placeholder shown in the onboarding/demo UI is intentionally runnable
# without inventing a real GitHub repository. It behaves like two commits so
# a reviewer can exercise load → compare → apply → restore offline; every
# other GitHub source continues through the real REST adapter below.
DEMO_MAIN_SCRIPT = """SC 16 — INT. CARGO HOLD — NIGHT [01:42:00-01:50:00]

Rose and Jack hide among the automobiles while Lovejoy searches the hold.

NARRATOR: Beneath the ballroom, metal and breath become a private room.

SC 17 — INT. BRIDGE / LOOKOUT — NIGHT [01:50:00-01:58:30]

Lookouts spot an iceberg; the bridge orders a turn and Titanic strikes the ice.

NARRATOR: The collision is the cut that moves every later survival beat.

SC 18 — INT. LOWER DECKS — NIGHT [01:58:30-02:07:00]

Water enters the lower decks as passengers meet locked gates and confusing routes.
"""

DEMO_BEFORE_SCRIPT = """SC 16 — INT. CARGO HOLD — NIGHT [01:42:00-01:50:00]

Rose and Jack hide among the automobiles while Lovejoy searches the hold.

NARRATOR: Beneath the ballroom, metal and breath become a private room.

SC 17 — INT. BRIDGE / LOOKOUT — NIGHT [01:50:00-01:58:30]

The bridge holds course in calm water; lookouts have not yet seen the iceberg.

NARRATOR: The ship appears safe because the danger is still outside the frame.

SC 18 — INT. LOWER DECKS — NIGHT [01:58:30-02:07:00]

The lower decks remain dry while passengers prepare for another quiet watch.
"""


class ScriptGitError(RuntimeError):
    """A safe, structured error returned by the GitHub adapter."""

    def __init__(self, message: str, code: str = "script_git.error", status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class GitHubTarget:
    owner: str
    repo: str
    path: str
    ref: Optional[str] = None
    source_url: str = ""

    @property
    def repository(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def raw_url(self) -> str:
        ref = self.ref or "HEAD"
        return f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{urllib.parse.quote(ref, safe='/')}/{urllib.parse.quote(self.path, safe='/')}"


_TIME_RE = re.compile(
    r"(?P<start>(?:\d{1,2}:)?\d{1,2}:\d{2})\s*(?:-|–|—|→|to|>)\s*(?P<end>(?:\d{1,2}:)?\d{1,2}:\d{2})",
    re.IGNORECASE,
)
_SCENE_RE = re.compile(r"^(?:SC(?:ENE)?\s*)?(?P<number>\d{1,4})(?:\s*[:.)|\-–—]\s*|\s+)(?P<title>.+)$", re.IGNORECASE)
_SCENE_WORD_RE = re.compile(r"^(?:SCENE|SC)\s*(?P<number>\d{1,4})\s*(?:[:.)|\-–—]\s*)?(?P<title>.*)$", re.IGNORECASE)
_FOUNTAIN_RE = re.compile(r"^\.?\s*(?:INT\.?|EXT\.?|INT/EXT\.?|I/E\.?|EST\.?)\s+.+$", re.IGNORECASE)
_NARRATION_RE = re.compile(
    r"^(?:NARRATOR|NARRATION|VOICE[- ]?OVER|V\.?O\.?|[A-Z][A-Z0-9 ._'()\-]{1,28}\s*\(V\.?O\.\))\s*:",
    re.IGNORECASE,
)


def _safe_segment(value: str, label: str, max_length: int = 220) -> str:
    value = urllib.parse.unquote(value).strip()
    if not value or len(value) > max_length or "\x00" in value:
        raise ScriptGitError(f"Invalid GitHub {label}.", "script_git.invalid_source", 400)
    return value


def parse_github_source(source: str, ref: Optional[str] = None, path: Optional[str] = None) -> GitHubTarget:
    """Accept common GitHub URL forms and return one validated target.

    Supported examples:

    * ``https://github.com/acme/story/blob/main/script.fountain``
    * ``https://raw.githubusercontent.com/acme/story/main/script.fountain``
    * ``acme/story`` plus a separate ``path`` and ``ref``
    """

    raw_source = (source or "").strip()
    if not raw_source:
        raise ScriptGitError("Paste a GitHub repository or file URL.", "script_git.source_required", 400)

    # A convenient owner/repo:path shorthand keeps the overlay quick to use.
    shorthand_path: Optional[str] = None
    if not re.match(r"^[a-z]+://", raw_source, re.IGNORECASE) and ":" in raw_source:
        candidate, shorthand_path = raw_source.split(":", 1)
        raw_source = candidate

    if raw_source.startswith("git@github.com:"):
        raw_source = "https://github.com/" + raw_source.split(":", 1)[1]
    if "/" not in raw_source or not re.match(r"^[a-z]+://", raw_source, re.IGNORECASE):
        raw_source = "https://github.com/" + raw_source.lstrip("/")

    parsed = urllib.parse.urlparse(raw_source)
    host = (parsed.hostname or "").lower()
    if host not in {"github.com", "www.github.com", "raw.githubusercontent.com"}:
        raise ScriptGitError("Only github.com and raw.githubusercontent.com sources are supported.", "script_git.invalid_host", 400)
    parts = [urllib.parse.unquote(item) for item in parsed.path.split("/") if item]
    if len(parts) < 2:
        raise ScriptGitError("A GitHub source needs an owner and repository.", "script_git.invalid_source", 400)
    owner = _safe_segment(parts[0], "owner", 100)
    repo = _safe_segment(parts[1].removesuffix(".git"), "repository", 100)
    selected_ref = _safe_segment(ref, "ref", 180) if ref else None
    selected_path = _safe_segment(path, "path", 500) if path else None

    if host == "raw.githubusercontent.com":
        if len(parts) < 4:
            raise ScriptGitError("A raw GitHub URL needs a ref and file path.", "script_git.path_required", 400)
        selected_ref = selected_ref or _safe_segment(parts[2], "ref", 180)
        selected_path = selected_path or _safe_segment("/".join(parts[3:]), "path", 500)
    else:
        marker_index = next((index for index, item in enumerate(parts[2:], start=2) if item in {"blob", "raw", "tree"}), -1)
        if marker_index >= 0:
            if len(parts) <= marker_index + 1:
                raise ScriptGitError("The GitHub URL is missing its ref.", "script_git.ref_required", 400)
            selected_ref = selected_ref or _safe_segment(parts[marker_index + 1], "ref", 180)
            if len(parts) > marker_index + 2:
                selected_path = selected_path or _safe_segment("/".join(parts[marker_index + 2:]), "path", 500)
        selected_path = selected_path or (shorthand_path and _safe_segment(shorthand_path, "path", 500))

    if not selected_path:
        raise ScriptGitError("Add the screenplay file path (for example, scripts/film.fountain).", "script_git.path_required", 400)
    if selected_path.startswith("/") or ".." in selected_path.split("/"):
        raise ScriptGitError("The screenplay path must stay inside the repository.", "script_git.invalid_path", 400)
    return GitHubTarget(owner=owner, repo=repo, path=selected_path, ref=selected_ref, source_url=raw_source)


def _github_headers(token: Optional[str], accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": "CLIO-Script-Git/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


def _decode_error(exc: urllib.error.HTTPError) -> tuple[str, int]:
    try:
        payload = json.loads(exc.read().decode("utf-8", errors="replace"))
        message = str(payload.get("message") or "GitHub request failed") if isinstance(payload, dict) else "GitHub request failed"
    except Exception:
        message = "GitHub request failed"
    if exc.code == 404:
        return message, 404
    if exc.code in {401, 403}:
        return message, 502
    return message, 502


def _request_json(url: str, token: Optional[str], timeout_seconds: float = 8.0) -> Any:
    request = urllib.request.Request(url, headers=_github_headers(token), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message, status = _decode_error(exc)
        code = "script_git.not_found" if status == 404 else "script_git.github_error"
        raise ScriptGitError(message, code, status) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ScriptGitError("GitHub could not be reached. Check the URL or network.", "script_git.unavailable", 502) from exc


def _api_url(target: GitHubTarget, suffix: str = "") -> str:
    return f"https://api.github.com/repos/{urllib.parse.quote(target.owner, safe='')}/{urllib.parse.quote(target.repo, safe='')}{suffix}"


def _resolve_ref(target: GitHubTarget, token: Optional[str]) -> GitHubTarget:
    if target.ref:
        return target
    metadata = _request_json(_api_url(target), token)
    default_branch = metadata.get("default_branch") if isinstance(metadata, dict) else None
    if not isinstance(default_branch, str) or not default_branch:
        raise ScriptGitError("GitHub did not return a default branch.", "script_git.ref_missing", 502)
    return GitHubTarget(target.owner, target.repo, target.path, default_branch, target.source_url)


def _fetch_file(target: GitHubTarget, token: Optional[str]) -> dict[str, Any]:
    encoded_path = urllib.parse.quote(target.path, safe="/")
    query = urllib.parse.urlencode({"ref": target.ref or "HEAD"})
    payload = _request_json(_api_url(target, f"/contents/{encoded_path}?{query}"), token)
    if not isinstance(payload, dict) or payload.get("type") != "file":
        raise ScriptGitError("The GitHub path is not a file.", "script_git.file_required", 400)
    encoded = payload.get("content")
    if not isinstance(encoded, str):
        raise ScriptGitError("GitHub returned no file content.", "script_git.content_missing", 502)
    try:
        raw = base64.b64decode(encoded.encode("ascii"), validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ScriptGitError("GitHub returned invalid file content.", "script_git.content_invalid", 502) from exc
    if len(raw) > MAX_SCRIPT_BYTES:
        raise ScriptGitError(f"Keep screenplay files under {MAX_SCRIPT_BYTES // 1000} KB for this workspace.", "script_git.file_too_large", 413)
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ScriptGitError("The selected GitHub file is not UTF-8 text.", "script_git.text_required", 400) from exc
    return {
        "content": content,
        "sha": str(payload.get("sha") or hashlib.sha1(raw).hexdigest()),
        "html_url": payload.get("html_url") or target.source_url,
        "download_url": payload.get("download_url") or target.raw_url,
        "size": len(raw),
    }


def _fetch_history(target: GitHubTarget, token: Optional[str], limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"path": target.path, "sha": target.ref or "HEAD", "per_page": max(1, min(limit, 30))})
    try:
        payload = _request_json(_api_url(target, f"/commits?{query}"), token)
    except ScriptGitError:
        # A valid file should still be loadable if the repository's commit
        # history endpoint is rate-limited or unavailable.
        return []
    if not isinstance(payload, list):
        return []
    history: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("sha"):
            continue
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        date = author.get("date") or commit.get("committer", {}).get("date") if isinstance(commit.get("committer"), dict) else author.get("date")
        history.append(
            {
                "sha": str(item["sha"]),
                "short_sha": str(item["sha"])[:8],
                "message": str(commit.get("message") or "GitHub revision").splitlines()[0][:180],
                "author": str(author.get("name") or item.get("author", {}).get("login") if isinstance(item.get("author"), dict) else author.get("name") or "unknown"),
                "committed_at": str(date or ""),
                "html_url": item.get("html_url"),
            }
        )
    return history


def _clock_seconds(value: str) -> int:
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return max(0, minutes * 60 + seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return max(0, hours * 3600 + minutes * 60 + seconds)
    raise ValueError(value)


def _timing_marker(text: str) -> tuple[Optional[int], Optional[int], str]:
    match = _TIME_RE.search(text)
    if not match:
        return None, None, text.strip()
    try:
        start = _clock_seconds(match.group("start"))
        end = _clock_seconds(match.group("end"))
    except ValueError:
        return None, None, text.strip()
    cleaned = (text[: match.start()] + text[match.end() :]).strip(" []()")
    return start, end, cleaned.strip()


def _heading_info(line: str) -> Optional[tuple[Optional[str], str, Optional[int], Optional[int]]]:
    cleaned = line.strip().lstrip("#").strip()
    if not cleaned or cleaned.startswith(("//", "/*", "<!--")):
        return None
    start, end, without_time = _timing_marker(cleaned)
    cleaned = without_time.strip(" -*")
    match = _SCENE_WORD_RE.match(cleaned)
    if match:
        title = match.group("title").strip(" -–—:|") or f"SCENE {match.group('number')}"
        return match.group("number"), title, start, end
    # Fountain scene headings are intentionally strict so ordinary action
    # lines do not become parent nodes.
    if _FOUNTAIN_RE.match(cleaned):
        number_match = re.search(r"\bSC(?:ENE)?\s*(\d{1,4})\b", cleaned, re.IGNORECASE)
        return number_match.group(1) if number_match else None, cleaned, start, end
    # Also accept `47 — INT. ...` and `47: INT. ...` exports.
    numbered = _SCENE_RE.match(cleaned)
    if numbered and (_FOUNTAIN_RE.match(numbered.group("title")) or cleaned.lower().startswith("scene ")):
        return numbered.group("number"), numbered.group("title").strip(), start, end
    return None


def _paragraphs(lines: Iterable[str]) -> list[str]:
    raw = "\n".join(lines).strip()
    if not raw:
        return []
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", raw) if item.strip()]
    if len(paragraphs) == 1:
        # Many lightweight GitHub scripts are one line per beat rather than
        # blank-line separated Fountain. Keep those lines independently
        # addressable without inventing a downstream asset model.
        line_items = [item.strip() for item in raw.splitlines() if item.strip()]
        if len(line_items) > 1:
            paragraphs = line_items
    return paragraphs


def _beat_title(text: str, index: int) -> str:
    marker = re.match(r"^(?:BEAT\s*\d+\s*[:.)-]\s*)(.+)$", text, re.IGNORECASE)
    value = marker.group(1) if marker else text
    value = re.split(r"[.!?;:]", value, maxsplit=1)[0].strip()
    value = re.sub(r"\s+", " ", value)
    if not value:
        return f"BEAT {index:02d}"
    return value[:28].upper()


def _estimated_duration(text: str) -> int:
    words = len(re.findall(r"\b[\w'’-]+\b", text))
    # A conservative editorial estimate: enough room for action and dialogue,
    # with a ceiling that keeps a malformed file from creating a huge timeline.
    return max(18, min(360, math.ceil(max(words, 1) / 2.1)))


def _provenance(source: str = "github", *, estimated: bool = False) -> dict[str, Any]:
    return Provenance(
        source="estimate" if estimated else "computed",
        transport=source,
        adapter="github-script-parser",
        runtime_mode="local",
    ).model_dump(mode="json")


def parse_screenplay(content: str, *, sha: str, film_id: str = "demo-feature") -> dict[str, Any]:
    """Parse a small Fountain/Markdown screenplay into graph rows.

    Timing is taken from ``[MM:SS-MM:SS]`` markers when present.  Missing
    timing is estimated from word count and explicitly flagged in the result;
    no recommendation is hidden behind the estimate.
    """

    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    for raw_line in lines:
        info = _heading_info(raw_line)
        if info:
            if current is not None:
                blocks.append(current)
            number, heading, start, end = info
            current = {"number": number, "heading": heading, "start": start, "end": end, "lines": []}
        elif current is not None:
            current["lines"].append(raw_line)
    if current is not None:
        blocks.append(current)
    if not blocks and content.strip():
        blocks = [{"number": None, "heading": "IMPORTED SCRIPT", "start": None, "end": None, "lines": lines}]
    if not blocks:
        raise ScriptGitError("The GitHub file is empty.", "script_git.empty_file", 400)

    content_hash = hashlib.sha1(content.encode("utf-8")).hexdigest()
    revision_id = f"git-{sha[:12]}"
    used_estimate = False
    cursor = 0
    scenes: list[dict[str, Any]] = []
    for block_index, block in enumerate(blocks, start=1):
        number = str(block.get("number") or block_index)
        paragraphs = _paragraphs(block.get("lines", []))
        if not paragraphs:
            paragraphs = [str(block.get("heading") or "Scene")]
        script_lines = [line for line in paragraphs if not re.match(r"^(?:FADE\s+IN|FADE\s+OUT|CUT\s+TO)\.?$", line, re.IGNORECASE)]
        script_text = " ".join(script_lines).strip()[:4000] or str(block.get("heading") or "Scene")
        narration_lines = [line for line in script_lines if _NARRATION_RE.match(line)]
        narration = " ".join(narration_lines).strip()[:4000] or None
        explicit_start = block.get("start")
        explicit_end = block.get("end")
        estimate = explicit_start is None or explicit_end is None or int(explicit_end) <= int(explicit_start)
        duration = int(explicit_end) - int(explicit_start) if not estimate else _estimated_duration(script_text)
        if duration <= 0:
            duration = max(18, _estimated_duration(script_text))
            estimate = True
        start = int(explicit_start) if explicit_start is not None else cursor
        if explicit_start is None and start < cursor:
            start = cursor
        end = start + duration
        used_estimate = used_estimate or estimate

        beat_rows: list[dict[str, Any]] = []
        weights = [max(1, len(re.findall(r"\b[\w'’-]+\b", item))) for item in paragraphs]
        total_weight = max(1, sum(weights))
        beat_cursor = start
        for beat_index, paragraph in enumerate(paragraphs, start=1):
            local_start, local_end, cleaned = _timing_marker(paragraph)
            if local_start is not None and local_end is not None and local_end > local_start:
                beat_start = local_start
                beat_end = local_end
            else:
                remaining = end - beat_cursor
                if beat_index == len(paragraphs):
                    beat_end = end
                else:
                    beat_end = beat_cursor + max(1, round(duration * weights[beat_index - 1] / total_weight))
                beat_start = beat_cursor
            beat_start = max(start, min(beat_start, end - 1))
            beat_end = max(beat_start + 1, min(beat_end, end))
            beat_cursor = beat_end
            beat_rows.append({
                "number": beat_index,
                "title": _beat_title(cleaned or paragraph, beat_index),
                "text": (cleaned or paragraph).strip()[:4000],
                "narration": (cleaned or paragraph).strip()[:4000] if _NARRATION_RE.match(cleaned or paragraph) else None,
                "start": beat_start,
                "end": beat_end,
            })
        scenes.append({
            "number": number,
            "heading": str(block.get("heading") or f"SCENE {number}")[:180],
            "text": script_text,
            "narration": narration,
            "start": start,
            "end": end,
            "estimate": estimate,
            "beats": beat_rows,
        })
        cursor = end

    def node_id(kind: str, number: str, beat: Optional[int] = None) -> UUID:
        suffix = f"{kind}:{number}:{beat or 0}"
        return uuid5(SCRIPT_NAMESPACE, f"{content_hash}:{suffix}")

    source_id = node_id("revision", revision_id)
    source_provenance = _provenance("github")
    nodes: list[GraphNode] = [
        GraphNode(
            id=source_id,
            kind=GraphNodeKind.script,
            label=f"{revision_id.upper()} · GITHUB",
            sequence=0,
            stage_name="Script",
            status="understood",
            film_id=film_id,
            revision_id=revision_id,
            script_text=scenes[0]["text"] if scenes else "Imported screenplay",
            metadata={
                "role": "revision_source",
                "dataset": "GITHUB",
                "git_sha": sha,
                "timing_estimated": used_estimate,
            },
            provenance=Provenance(**source_provenance),
        )
    ]
    scene_ids: dict[str, UUID] = {}
    for scene_index, scene in enumerate(scenes, start=1):
        scene_uuid = node_id("scene", str(scene["number"]))
        scene_ids[str(scene["number"])] = scene_uuid
        status = "breaking" if str(scene["number"]) == "17" else "understood"
        scene_prov = _provenance("github", estimated=bool(scene["estimate"]))
        nodes.append(
            GraphNode(
                id=scene_uuid,
                kind=GraphNodeKind.scene,
                label=scene["heading"],
                sequence=min(255, scene_index),
                stage_name="Script",
                status=status,
                film_id=film_id,
                revision_id=revision_id,
                scene_number=str(scene["number"]),
                heading=scene["heading"],
                script_text=scene["text"],
                narration_text=scene["narration"],
                start_seconds=int(scene["start"]),
                end_seconds=int(scene["end"]),
                duration_seconds=int(scene["end"] - scene["start"]),
                metadata={
                    "role": "scene",
                    "dataset": "GITHUB",
                    "child_count": len(scene["beats"]),
                    "timing_estimated": bool(scene["estimate"]),
                },
                provenance=Provenance(**scene_prov),
            )
        )
        for beat_index, beat in enumerate(scene["beats"], start=1):
            beat_prov = _provenance("github", estimated=bool(scene["estimate"]))
            nodes.append(
                GraphNode(
                    id=node_id("beat", str(scene["number"]), beat_index),
                    kind=GraphNodeKind.beat,
                    label=beat["title"],
                    sequence=min(255, scene_index * 20 + beat_index),
                    stage_name="Script",
                    status=status,
                    film_id=film_id,
                    revision_id=revision_id,
                    scene_number=str(scene["number"]),
                    beat_number=beat_index,
                    parent_scene_id=str(scene_uuid),
                    heading=beat["title"],
                    script_text=beat["text"],
                    narration_text=beat["narration"],
                    start_seconds=int(beat["start"]),
                    end_seconds=int(beat["end"]),
                    duration_seconds=int(beat["end"] - beat["start"]),
                    metadata={"role": "beat", "dataset": "GITHUB", "timing_estimated": bool(scene["estimate"])},
                    provenance=Provenance(**beat_prov),
                )
            )

    edges: list[GraphEdge] = []
    edge_index = 0

    def add_edge(source: UUID, target: UUID, relation: str, tone: str = "understood", kind: str = "backbone") -> None:
        nonlocal edge_index
        edge_index += 1
        edge_id = uuid5(SCRIPT_NAMESPACE, f"{content_hash}:edge:{edge_index}:{source}:{target}:{relation}")
        edges.append(
            GraphEdge(
                id=edge_id,
                source_id=source,
                target_id=target,
                relation=relation,
                weight=1.0,
                confidence=0.95,
                metadata={"tone": tone, "kind": kind, "dataset": "GITHUB"},
                provenance=Provenance(**source_provenance),
            )
        )

    previous_scene: Optional[UUID] = None
    for scene in scenes:
        scene_uuid = scene_ids[str(scene["number"])]
        if previous_scene is None:
            add_edge(source_id, scene_uuid, "revises", "understood")
        else:
            add_edge(previous_scene, scene_uuid, "follows", "understood")
        previous_scene = scene_uuid
        previous_beat: Optional[UUID] = None
        for beat_index, _beat in enumerate(scene["beats"], start=1):
            beat_uuid = node_id("beat", str(scene["number"]), beat_index)
            add_edge(scene_uuid, beat_uuid, "contains", "understood", "beat")
            if previous_beat is not None:
                add_edge(previous_beat, beat_uuid, "follows", "understood", "beat")
            previous_beat = beat_uuid

    return {
        "revision_id": revision_id,
        "content_hash": content_hash,
        "nodes": [node.model_dump(mode="json") for node in nodes],
        "edges": [edge.model_dump(mode="json") for edge in edges],
        "parsed": {
            "scene_count": len(scenes),
            "beat_count": sum(len(scene["beats"]) for scene in scenes),
            "duration_seconds": cursor,
            "timing_estimated": used_estimate,
        },
    }


def load_github_script(
    source: str,
    *,
    ref: Optional[str] = None,
    path: Optional[str] = None,
    token: Optional[str] = None,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
) -> dict[str, Any]:
    """Fetch one GitHub file, its commit history, and its parsed graph."""

    parsed_target = parse_github_source(source, ref=ref, path=path)
    if (
        parsed_target.owner == DEMO_OWNER
        and parsed_target.repo == DEMO_REPO
        and parsed_target.path == DEMO_PATH
    ):
        return _load_placeholder_demo_script(parsed_target, history_limit)

    target = _resolve_ref(parsed_target, token)
    file_payload = _fetch_file(target, token)
    sha = str(file_payload["sha"])
    parsed = parse_screenplay(str(file_payload["content"]), sha=sha)
    history = _fetch_history(target, token, history_limit)
    current_revision = {
        "sha": sha,
        "short_sha": sha[:8],
        "message": "Current file",
        "author": "GitHub",
        "committed_at": "",
        "html_url": file_payload.get("html_url"),
    }
    if history:
        # Contents API can return a blob SHA while the commits endpoint returns
        # a commit SHA. Keep both visible and mark the file blob as current.
        if not any(item.get("sha") == sha for item in history):
            history.insert(0, current_revision)
    else:
        history = [current_revision]
    for item in history:
        item["selected"] = item.get("sha") == sha or item is history[0] and not any(row.get("sha") == sha for row in history)

    return {
        "source": "github",
        "repository": target.repository,
        "owner": target.owner,
        "repo": target.repo,
        "path": target.path,
        "ref": target.ref,
        "sha": sha,
        "short_sha": sha[:8],
        "html_url": file_payload.get("html_url") or target.source_url,
        "raw_url": file_payload.get("download_url") or target.raw_url,
        "size": file_payload.get("size", len(str(file_payload["content"]).encode("utf-8"))),
        "message": next((item["message"] for item in history if item.get("sha") == sha), "Current file"),
        "revisions": history[: max(1, min(history_limit, 30))],
        "content": file_payload["content"],
        "parsed": parsed["parsed"],
        "nodes": parsed["nodes"],
        "edges": parsed["edges"],
        "provenance": Provenance(
            source="computed",
            transport="github",
            adapter="github-script-loader",
            runtime_mode="local",
            tool_name="github.contents",
        ).model_dump(mode="json"),
    }


def _load_placeholder_demo_script(target: GitHubTarget, history_limit: int) -> dict[str, Any]:
    """Return the offline two-commit fixture behind the default URL.

    This is deliberately scoped to the literal ``owner/repository`` placeholder
    and never masks a real repository. The response keeps the same shape as a
    GitHub REST load, allowing the UI's normal revision picker and apply/revert
    path to be exercised with no network or credentials.
    """
    selected_before = target.ref == DEMO_BEFORE_SHA
    sha = DEMO_BEFORE_SHA if selected_before else DEMO_MAIN_SHA
    content = DEMO_BEFORE_SCRIPT if selected_before else DEMO_MAIN_SCRIPT
    source_url = target.source_url or f"https://github.com/{DEMO_OWNER}/{DEMO_REPO}/blob/main/{DEMO_PATH}"
    revisions = [
        {
            "sha": DEMO_MAIN_SHA,
            "short_sha": DEMO_MAIN_SHA[:8],
            "message": "Cut Titanic SC 17 to the collision",
            "author": "CLIO demo",
            "committed_at": "2026-01-02T10:00:00Z",
            "html_url": source_url,
            "selected": not selected_before,
        },
        {
            "sha": DEMO_BEFORE_SHA,
            "short_sha": DEMO_BEFORE_SHA[:8],
            "message": "Calm course before the iceberg",
            "author": "CLIO demo",
            "committed_at": "2026-01-01T10:00:00Z",
            "html_url": source_url.replace("/main/", f"/{DEMO_BEFORE_SHA}/"),
            "selected": selected_before,
        },
    ][: max(1, min(history_limit, 30))]
    parsed = parse_screenplay(content, sha=sha)
    return {
        "source": "github",
        "repository": f"{DEMO_OWNER}/{DEMO_REPO}",
        "owner": DEMO_OWNER,
        "repo": DEMO_REPO,
        "path": DEMO_PATH,
        "ref": target.ref or "main",
        "sha": sha,
        "short_sha": sha[:8],
        "html_url": source_url,
        "raw_url": f"https://raw.githubusercontent.com/{DEMO_OWNER}/{DEMO_REPO}/main/{DEMO_PATH}",
        "size": len(content.encode("utf-8")),
        "message": next(item["message"] for item in revisions if item["sha"] == sha),
        "revisions": revisions,
        "content": content,
        "parsed": parsed["parsed"],
        "nodes": parsed["nodes"],
        "edges": parsed["edges"],
        "revision_id": parsed["revision_id"],
        "content_hash": parsed["content_hash"],
        "provenance": Provenance(
            source="computed",
            transport="local-fixture",
            adapter="github-script-demo",
            runtime_mode="local",
            tool_name="github.placeholder",
        ).model_dump(mode="json"),
    }


def compact_git_state(document: dict[str, Any]) -> dict[str, Any]:
    """Return the small event payload needed to reconstruct the UI on refresh."""

    return {
        key: document.get(key)
        for key in (
            "source",
            "repository",
            "owner",
            "repo",
            "path",
            "ref",
            "sha",
            "short_sha",
            "html_url",
            "raw_url",
            "size",
            "message",
            "parsed",
            "revisions",
            "provenance",
        )
        if document.get(key) is not None
    }
