"""Data models for movies, scripts and scenes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Narration pace used to estimate how long a scene's voice-over takes.
WORDS_PER_SECOND = 2.4

Mode = Literal["adaptation", "inspired"]


class Movie(BaseModel):
    title: str
    year: int
    director: str = ""
    genre: str = ""
    logline: str = ""
    country: str = ""
    # "public_domain" = known US public domain; "verify" = believed lapsed into PD
    # (check before relying on it); "copyrighted"; "unknown".
    rights_hint: Literal["public_domain", "verify", "copyrighted", "unknown"] = "unknown"
    rights_note: str = ""
    source: str = "catalog"


class Scene(BaseModel):
    id: str = Field(description="Stable scene id like S01. Never reused.")
    title: str = Field(description="Short scene heading, e.g. 'INT. TRAIN CAR - NIGHT'.")
    summary: str = Field(description="One or two sentences on what happens.")
    narration: str = Field(description="Voice-over text read aloud for this scene.")
    dialogue: list[str] = Field(
        default_factory=list,
        description="Lines of dialogue formatted 'CHARACTER: line'. Empty if none.",
    )
    visual_prompt: str = Field(
        description="Detailed prompt for an AI video model: subject, setting, era, "
        "lighting, camera movement, style. No real actor names."
    )
    image_search: str = Field(
        default="",
        description="2-6 word search query for free archival pictures on Wikimedia Commons "
        "(photos, paintings, film stills) that fit this scene, e.g. 'Nosferatu 1922 Orlok' or "
        "'1920s steam locomotive night'.",
    )
    camera: str = Field(default="", description="Shot type and movement.")
    music_mood: str = Field(default="", description="Music / sound design mood.")
    duration_sec: int = Field(description="Target on-screen length in seconds (20-90).")
    social_hook: bool = Field(
        default=False,
        description="True if this scene works as a standalone hook for TikTok/Reels/Shorts.",
    )


class SocialMeta(BaseModel):
    youtube_title: str
    youtube_description: str
    tags: list[str]
    short_caption: str = Field(description="Caption for TikTok / Instagram Reels clips.")
    hashtags: list[str]


class Script(BaseModel):
    title: str
    logline: str
    source_movie: str
    source_year: int
    mode: Mode
    rights_statement: str
    target_minutes: int
    style: str = ""
    scenes: list[Scene]
    social: SocialMeta

    # ---- helpers -------------------------------------------------------
    def total_seconds(self) -> int:
        return sum(s.duration_sec for s in self.scenes)

    def find(self, scene_id: str) -> int:
        for i, s in enumerate(self.scenes):
            if s.id.lower() == scene_id.lower():
                return i
        raise KeyError(f"No scene with id {scene_id!r}. Use `script show` to list ids.")

    def next_id(self) -> str:
        nums = [int(s.id[1:]) for s in self.scenes if s.id[1:].isdigit()]
        return f"S{(max(nums) + 1 if nums else 1):02d}"


# Models used as Claude structured-output schemas ---------------------------

class GeneratedScript(BaseModel):
    """What Claude returns when writing a full script."""

    title: str
    logline: str
    style: str
    scenes: list[Scene]
    social: SocialMeta


class GeneratedScene(BaseModel):
    """What Claude returns when writing or rewriting a single scene."""

    scene: Scene
