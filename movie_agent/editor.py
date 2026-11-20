"""Script editing: add, remove, move, duplicate and edit scenes.

All functions mutate and return the Script; Project.save() snapshots the previous
version so every change can be undone.
"""

from __future__ import annotations

from .models import Scene, Script
from .project import estimate_duration

EDITABLE_FIELDS = {
    "title", "summary", "narration", "dialogue", "visual_prompt",
    "camera", "music_mood", "duration_sec", "social_hook",
}


def resolve_position(script: Script, after: str | None = None, before: str | None = None) -> int:
    """0-based insert index. Default: append at the end."""
    if after and before:
        raise ValueError("Use either --after or --before, not both.")
    if after:
        return 0 if after.lower() == "start" else script.find(after) + 1
    if before:
        return script.find(before)
    return len(script.scenes)


def insert_scene(script: Script, scene: Scene, position: int) -> Script:
    if any(s.id.lower() == scene.id.lower() for s in script.scenes):
        raise ValueError(f"Scene id {scene.id} already exists.")
    script.scenes.insert(position, scene)
    return script


def add_manual_scene(
    script: Script,
    position: int,
    title: str,
    narration: str,
    visual_prompt: str,
    summary: str = "",
    duration_sec: int | None = None,
) -> Scene:
    scene = Scene(
        id=script.next_id(),
        title=title,
        summary=summary or title,
        narration=narration,
        visual_prompt=visual_prompt,
        duration_sec=duration_sec or 30,
    )
    if duration_sec is None:
        scene.duration_sec = estimate_duration(scene)
    insert_scene(script, scene, position)
    return scene


def remove_scenes(script: Script, scene_ids: list[str]) -> list[Scene]:
    idxs = sorted({script.find(i) for i in scene_ids}, reverse=True)
    removed = [script.scenes.pop(i) for i in idxs]
    return list(reversed(removed))


def move_scene(script: Script, scene_id: str, after: str | None = None, before: str | None = None) -> Script:
    scene = script.scenes.pop(script.find(scene_id))
    try:
        pos = resolve_position(script, after, before)
    except KeyError:
        script.scenes.insert(0, scene)  # keep the scene if the target is bad
        raise
    script.scenes.insert(pos, scene)
    return script


def duplicate_scene(script: Script, scene_id: str) -> Scene:
    idx = script.find(scene_id)
    copy = script.scenes[idx].model_copy(deep=True)
    copy.id = script.next_id()
    script.scenes.insert(idx + 1, copy)
    return copy


def set_field(script: Script, scene_id: str, field: str, value: str) -> Scene:
    if field not in EDITABLE_FIELDS:
        raise ValueError(f"Unknown field {field!r}. Editable: {', '.join(sorted(EDITABLE_FIELDS))}")
    scene = script.scenes[script.find(scene_id)]
    if field == "duration_sec":
        setattr(scene, field, int(value))
    elif field == "social_hook":
        setattr(scene, field, value.strip().lower() in ("1", "true", "yes", "y", "on"))
    elif field == "dialogue":
        scene.dialogue = [line.strip() for line in value.split("|") if line.strip()]
    else:
        setattr(scene, field, value)
    if field in ("narration", "dialogue"):
        scene.duration_sec = estimate_duration(scene)
    return scene


def renumber(script: Script) -> Script:
    """Rename scene ids to S01..Snn in current order (do this before rendering if you like)."""
    for i, s in enumerate(script.scenes, 1):
        s.id = f"S{i:02d}"
    return script
