"""A project folder holds one film: its script, edit history, rendered assets and outputs.

projects/<slug>/
  script.json        <- the source of truth (edit with `script` commands or by hand)
  script.md          <- readable screenplay, regenerated on every save
  history/           <- a snapshot before every change, for `script undo`
  assets/scenes/     <- one rendered clip per scene (S01.mp4 ...)
  output/            <- full film, subtitles, vertical clips
"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from .models import WORDS_PER_SECOND, Scene, Script

ROOT = Path("projects")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "untitled"


class Project:
    def __init__(self, path: Path):
        self.path = Path(path)

    @classmethod
    def open(cls, name: str) -> "Project":
        p = Path(name) if Path(name).exists() else ROOT / name
        if not (p / "script.json").exists():
            raise FileNotFoundError(f"No project at {p}. Run `plan` first or `list` to see projects.")
        return cls(p)

    @classmethod
    def create(cls, script: Script, name: str | None = None) -> "Project":
        base = ROOT / slugify(name or f"{script.source_movie}-{script.source_year}")
        p, n = base, 2
        while p.exists():
            p, n = Path(f"{base}-{n}"), n + 1
        p.mkdir(parents=True)
        proj = cls(p)
        proj.save(script, snapshot=False)
        return proj

    # paths --------------------------------------------------------------
    @property
    def script_file(self) -> Path:
        return self.path / "script.json"

    @property
    def scenes_dir(self) -> Path:
        return self.path / "assets" / "scenes"

    @property
    def output_dir(self) -> Path:
        return self.path / "output"

    # load / save --------------------------------------------------------
    def load(self) -> Script:
        return Script.model_validate_json(self.script_file.read_text())

    def save(self, script: Script, snapshot: bool = True) -> None:
        if snapshot and self.script_file.exists():
            hist = self.path / "history"
            hist.mkdir(exist_ok=True)
            shutil.copy(self.script_file, hist / f"script-{time.time_ns():020d}.json")
        self.script_file.write_text(script.model_dump_json(indent=2))
        (self.path / "script.md").write_text(to_markdown(script))

    def undo(self) -> Script:
        hist = sorted((self.path / "history").glob("script-*.json"))
        if not hist:
            raise RuntimeError("Nothing to undo.")
        last = hist[-1]
        script = Script.model_validate_json(last.read_text())
        self.save(script, snapshot=False)
        last.unlink()
        return script


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def to_markdown(script: Script) -> str:
    total = script.total_seconds()
    out = [
        f"# {script.title}",
        "",
        f"*{script.logline}*",
        "",
        f"- **Source:** {script.source_movie} ({script.source_year}), mode: **{script.mode}**",
        f"- **Runtime:** {fmt_time(total)} (target {script.target_minutes} min), {len(script.scenes)} scenes",
        f"- **Style:** {script.style}",
        f"- **Rights:** {script.rights_statement}",
        "",
        "---",
    ]
    t = 0
    for s in script.scenes:
        hook = "  ⚡ social hook" if s.social_hook else ""
        out += [
            "",
            f"## {s.id} · {s.title}  `{fmt_time(t)}–{fmt_time(t + s.duration_sec)}`{hook}",
            "",
            f"_{s.summary}_",
            "",
            f"**Narration:** {s.narration}",
        ]
        if s.dialogue:
            out += ["", "**Dialogue:**", *[f"> {line}  " for line in s.dialogue]]
        out += [
            "",
            f"**Visual prompt:** {s.visual_prompt}",
            f"**Camera:** {s.camera} · **Music:** {s.music_mood}",
        ]
        t += s.duration_sec
    sm = script.social
    out += [
        "",
        "---",
        "## Publishing",
        f"**YouTube title:** {sm.youtube_title}",
        "",
        f"**Description:** {sm.youtube_description}",
        "",
        f"**Tags:** {', '.join(sm.tags)}",
        "",
        f"**Short caption:** {sm.short_caption} {' '.join('#' + h.lstrip('#') for h in sm.hashtags)}",
        "",
    ]
    return "\n".join(out)


def estimate_duration(scene: Scene) -> int:
    words = len(scene.narration.split()) + sum(len(d.split()) for d in scene.dialogue)
    return max(20, round(words / WORDS_PER_SECOND) + 3)
