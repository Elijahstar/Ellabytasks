"""Claude-powered screenwriter: full scripts, new scenes and scene rewrites."""

from __future__ import annotations

import json
import os
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from .models import WORDS_PER_SECOND, GeneratedScene, GeneratedScript, Movie, Scene, Script

MODEL = os.environ.get("MOVIE_AGENT_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("MOVIE_AGENT_EFFORT", "high")
# If Claude declines a request, the API retries it on a fallback model automatically.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

T = TypeVar("T", bound=BaseModel)

SYSTEM = f"""You are the head writer of a channel that publishes long-form AI-generated
films (30-45 minutes) on YouTube, with short hooks cut for TikTok and Instagram Reels.
You turn classic cinema (1888-2000) into scripts that an AI video model and a
voice-over can render scene by scene.

Writing rules:
- Every scene must stand on its own visually: an AI video model sees only that
  scene's visual_prompt, so restate the setting, era, characters' looks,
  lighting and style in every prompt. Keep characters' descriptions consistent
  across scenes.
- Never use real actors' names or likenesses in visual prompts.
- narration is read aloud at about {WORDS_PER_SECOND} words per second; make
  duration_sec match it (narration words / {WORDS_PER_SECOND}, plus a few seconds
  of breathing room). Scenes run 20-90 seconds.
- Open with a strong hook in the first 30 seconds, build in three acts, and end
  with a satisfying close and a call to subscribe.
- Mark 5-10 of the most gripping, self-contained moments with social_hook=true.
- Scene ids are S01, S02, ... in order.

Copyright rules (mandatory):
- mode "adaptation": the source film is in the public domain. You may retell its
  plot, characters and setting in your own words. Do not reproduce intertitles
  or dialogue verbatim at length; write fresh narration.
- mode "inspired": the source is still under copyright. Write a wholly ORIGINAL
  story that shares only its era, genre, mood and broad themes. Invent new
  characters, names, plot events and dialogue. Do not reuse its title,
  character names, catchphrases, iconic scenes or twists."""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _call(prompt: str, schema: type[T], max_tokens: int = 64000) -> T:
    """Stream a structured-output request and return the validated object."""
    with _client().beta.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": EFFORT},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        raise RuntimeError(f"Claude declined this request: {getattr(details, 'explanation', '') or 'no details'}")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("The script was cut off (max_tokens). Try fewer --minutes.")
    if message.parsed_output is None:
        raise RuntimeError("Claude did not return a valid script.")
    return message.parsed_output


def write_script(
    movie: Movie,
    mode: str,
    rights_statement: str,
    minutes: int = 40,
    style: str = "",
    notes: str = "",
) -> Script:
    target = minutes * 60
    approx_scenes = max(8, round(target / 50))
    prompt = f"""Write a complete script.

Source film: {movie.title} ({movie.year})
Director: {movie.director or "unknown"}
Genre: {movie.genre or "unknown"}
What it is about: {movie.logline or "use your knowledge of the film"}
Mode: {mode}
Target length: {minutes} minutes = {target} seconds total. Aim for about
{approx_scenes} scenes whose duration_sec add up to between {target - 120} and {target + 120}.
Visual style: {style or "choose a style that honours the original film's era"}
Extra notes from the producer: {notes or "none"}

Also fill in social: a YouTube title (under 90 characters), a YouTube description
(with a short credit line naming the original film and director when mode is
"adaptation", or 'Inspired by classic {movie.genre or "cinema"}' when "inspired"),
tags, a short caption and hashtags for TikTok/Reels."""
    gen = _call(prompt, GeneratedScript)
    return Script(
        title=gen.title,
        logline=gen.logline,
        source_movie=movie.title,
        source_year=movie.year,
        mode=mode,  # type: ignore[arg-type]
        rights_statement=rights_statement,
        target_minutes=minutes,
        style=gen.style,
        scenes=gen.scenes,
        social=gen.social,
    )


def _context(script: Script, around: int | None = None) -> str:
    lines = []
    for i, s in enumerate(script.scenes):
        marker = "  <-- here" if around is not None and i == around else ""
        lines.append(f"{s.id} [{s.duration_sec}s] {s.title}: {s.summary}{marker}")
    return (
        f"Script: {script.title} ({script.mode} of {script.source_movie}, {script.source_year})\n"
        f"Style: {script.style}\nLogline: {script.logline}\n\nScene list:\n" + "\n".join(lines)
    )


def write_new_scene(script: Script, position: int, description: str, scene_id: str) -> Scene:
    """Write a brand-new scene to be inserted at `position` (0-based)."""
    before = script.scenes[position - 1].id if position > 0 else "the start"
    after = script.scenes[position].id if position < len(script.scenes) else "the end"
    prompt = f"""{_context(script)}

Write ONE new scene to insert between {before} and {after}.
The producer wants: {description}
Use id {scene_id}. Keep characters, look and tone consistent with the surrounding scenes.

Full text of the neighbouring scenes for continuity:
{json.dumps([s.model_dump() for s in script.scenes[max(0, position - 1):position + 1]], indent=1)}"""
    scene = _call(prompt, GeneratedScene, max_tokens=16000).scene
    scene.id = scene_id
    return scene


def rewrite_scene(script: Script, scene_id: str, instruction: str) -> Scene:
    idx = script.find(scene_id)
    prompt = f"""{_context(script, around=idx)}

Rewrite scene {scene_id} following this instruction from the producer:
{instruction}

Current scene:
{script.scenes[idx].model_dump_json(indent=1)}

Keep the same id. Keep continuity with the scenes before and after it."""
    scene = _call(prompt, GeneratedScene, max_tokens=16000).scene
    scene.id = script.scenes[idx].id
    return scene
