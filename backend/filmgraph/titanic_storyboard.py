from __future__ import annotations

"""Canonical offline Titanic storyboard seed for CLIO.

The JSON file is the single source shared by the browser fallback, FastAPI
fallback, and generated ClickHouse seed. Timing is derived from scene
durations so every scene and beat remains contiguous.
"""

import json
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "titanic_storyboard.json"


def _load_storyboard() -> dict[str, Any]:
    with _DATA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


_RAW_STORYBOARD = _load_storyboard()
DURATIONS: tuple[int, ...] = tuple(int(value) for value in _RAW_STORYBOARD["durations"])


def _with_timing() -> tuple[dict[str, Any], ...]:
    scenes: list[dict[str, Any]] = []
    cursor = 0
    for raw, duration in zip(_RAW_STORYBOARD["scenes"], DURATIONS, strict=True):
        start, end = cursor, cursor + duration
        span = end - start
        beats = []
        for beat_index, beat in enumerate(raw["beats"]):
            beat_start = start + (span * beat_index // 5)
            beat_end = end if beat_index == 4 else start + (span * (beat_index + 1) // 5)
            beats.append({
                "number": beat_index + 1,
                "title": str(beat["title"]),
                "text": str(beat["text"]),
                "narration": str(beat["narration"]),
                "start": beat_start,
                "end": beat_end,
            })
        scenes.append({
            "number": str(raw["number"]),
            "heading": str(raw["heading"]),
            "text": str(raw["summary"]),
            "narration": str(raw["narration"]),
            "start": start,
            "end": end,
            "status": str(raw["status"]),
            "beats": tuple(beats),
        })
        cursor = end
    return tuple(scenes)


TITANIC_SCENES = _with_timing()
STORYBOARD_VERSION = str(_RAW_STORYBOARD["version"])
TOTAL_DURATION_SECONDS = sum(DURATIONS)
TOTAL_BEAT_COUNT = sum(len(scene["beats"]) for scene in TITANIC_SCENES)
TOTAL_SCENE_COUNT = len(TITANIC_SCENES)

assert TOTAL_SCENE_COUNT == 25
assert TOTAL_BEAT_COUNT == 125
assert TOTAL_DURATION_SECONDS == 11700
assert TITANIC_SCENES[0]["start"] == 0
assert TITANIC_SCENES[-1]["end"] == TOTAL_DURATION_SECONDS

