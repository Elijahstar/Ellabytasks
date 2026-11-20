"""Render each scene to a video clip, then assemble the full film, subtitles and
vertical social clips with ffmpeg.

Video and voice generation are pluggable:

  video provider "preview"  - offline title-card clips (free, instant; for timing
                              and editing checks before you spend money)
  video provider "command"  - runs MOVIE_AGENT_VIDEO_CMD for each scene, so you can
                              call any AI video service (Runway, Luma, Kling, Veo,
                              Pika, a local model...) through your own script
  voice provider "silent"   - no narration audio
  voice provider "espeak"   - offline robotic TTS (needs espeak-ng installed)
  voice provider "command"  - runs MOVIE_AGENT_TTS_CMD (e.g. an ElevenLabs script)

Command templates get these placeholders:
  {prompt_file} {text_file} {out} {duration} {width} {height} {scene_id}
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

from .models import Scene, Script
from .project import Project, fmt_time

W, H, FPS = 1920, 1080, 30
FONT = next(
    (f for f in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ) if Path(f).exists()),
    "",
)


def _ffmpeg(*args: str) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed. Install it from https://ffmpeg.org/download.html")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {res.stderr.strip()[-2000:]}")


def _probe_duration(path: Path) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def _font_opt() -> str:
    return f"fontfile='{FONT}':" if FONT else ""


def _run_template(template: str, **values: object) -> None:
    quoted = {k: shlex.quote(str(v)) for k, v in values.items()}
    cmd = template.format(**quoted)
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed ({cmd}):\n{res.stderr.strip()[-2000:]}")


# ---------------------------------------------------------------- voice ----

def make_voice(scene: Scene, out: Path, provider: str, work: Path) -> Path | None:
    text = scene.narration
    if scene.dialogue:
        text += "\n" + "\n".join(scene.dialogue)
    text_file = work / f"{scene.id}.txt"
    text_file.write_text(text)
    if provider == "silent":
        return None
    if provider == "espeak":
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            raise RuntimeError("espeak-ng not found. Install it or use --voice silent/command.")
        wav = work / f"{scene.id}.wav"
        subprocess.run([exe, "-s", "150", "-w", str(wav), "-f", str(text_file)], check=True)
        _ffmpeg("-i", str(wav), "-ar", "48000", "-ac", "2", str(out))
        return out
    if provider == "command":
        tpl = os.environ.get("MOVIE_AGENT_TTS_CMD")
        if not tpl:
            raise RuntimeError("Set MOVIE_AGENT_TTS_CMD, e.g. 'python my_tts.py {text_file} {out}'")
        _run_template(tpl, text_file=text_file, out=out, scene_id=scene.id)
        return out
    raise ValueError(f"Unknown voice provider {provider!r}")


# ---------------------------------------------------------------- video ----

def make_preview_video(scene: Scene, out: Path, duration: float, work: Path) -> None:
    title_file = work / f"{scene.id}-title.txt"
    body_file = work / f"{scene.id}-body.txt"
    title_file.write_text(f"{scene.id}  ·  {scene.title}")
    body_file.write_text(textwrap.fill(scene.narration, 70)[:1400])
    f = _font_opt()
    vf = (
        f"drawtext={f}textfile='{title_file}':fontcolor=0xF5D28C:fontsize=54:x=(w-text_w)/2:y=140,"
        f"drawtext={f}textfile='{body_file}':fontcolor=white:fontsize=34:line_spacing=14:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+40,"
        f"drawtext={f}text='AI PREVIEW – replace with generated footage':fontcolor=0x888888:fontsize=24:"
        f"x=(w-text_w)/2:y=h-80"
    )
    _ffmpeg(
        "-f", "lavfi", "-i", f"color=c=0x15171c:s={W}x{H}:r={FPS}:d={duration:.2f}",
        "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
        "-pix_fmt", "yuv420p", str(out),
    )


def make_ai_video(scene: Scene, script: Script, out: Path, duration: float, work: Path) -> None:
    tpl = os.environ.get("MOVIE_AGENT_VIDEO_CMD")
    if not tpl:
        raise RuntimeError(
            "Set MOVIE_AGENT_VIDEO_CMD to a command that turns a prompt into a video, e.g.\n"
            "  export MOVIE_AGENT_VIDEO_CMD='python providers/my_video.py "
            "--prompt-file {prompt_file} --seconds {duration} --out {out}'"
        )
    prompt_file = work / f"{scene.id}-prompt.txt"
    prompt_file.write_text(
        f"{scene.visual_prompt}\nCamera: {scene.camera}\nOverall style: {script.style}"
    )
    _run_template(tpl, prompt_file=prompt_file, out=out, duration=round(duration),
                  width=W, height=H, scene_id=scene.id)


# ------------------------------------------------------------ per scene ----

def _scene_hash(scene: Scene, script: Script, video: str, voice: str) -> str:
    data = scene.model_dump(exclude={"social_hook"}) | {"style": script.style, "video": video, "voice": voice}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def render_scene(proj: Project, script: Script, scene: Scene, video: str, voice: str, force: bool = False) -> Path:
    """Render one scene to assets/scenes/<id>.mp4 (1920x1080, 30fps, AAC). Skips unchanged scenes."""
    proj.scenes_dir.mkdir(parents=True, exist_ok=True)
    final = proj.scenes_dir / f"{scene.id}.mp4"
    stamp = proj.scenes_dir / f"{scene.id}.hash"
    h = _scene_hash(scene, script, video, voice)
    if not force and final.exists() and stamp.exists() and stamp.read_text() == h:
        return final

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        audio = make_voice(scene, work / "voice.m4a", voice, work)
        duration = float(scene.duration_sec)
        if audio:
            duration = max(duration, _probe_duration(audio) + 0.5)

        raw = work / "raw.mp4"
        if video == "preview":
            make_preview_video(scene, raw, duration, work)
        elif video == "command":
            make_ai_video(scene, script, raw, duration, work)
        else:
            raise ValueError(f"Unknown video provider {video!r}")

        # Normalise: loop/trim to duration, fixed size/fps, add narration or silence.
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
              f"fps={FPS},format=yuv420p")
        args = ["-stream_loop", "-1", "-i", str(raw)]
        args += ["-i", str(audio)] if audio else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        args += [
            "-t", f"{duration:.2f}", "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-af", "apad", str(final),
        ]
        _ffmpeg(*args)
    stamp.write_text(h)
    return final


# ------------------------------------------------------------- assembly ----

def write_srt(script: Script, durations: list[float], out: Path) -> Path:
    def ts(sec: float) -> str:
        ms = int(round(sec * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    blocks, t, n = [], 0.0, 1
    for scene, dur in zip(script.scenes, durations):
        chunks = textwrap.wrap(scene.narration, 84) or [""]
        per = dur / len(chunks)
        for i, chunk in enumerate(chunks):
            start, end = t + i * per, t + (i + 1) * per
            blocks.append(f"{n}\n{ts(start)} --> {ts(end)}\n{textwrap.fill(chunk, 42)}\n")
            n += 1
        t += dur
    out.write_text("\n".join(blocks))
    return out


def assemble(proj: Project, script: Script, clips: list[Path]) -> dict[str, Path]:
    proj.output_dir.mkdir(parents=True, exist_ok=True)
    listing = proj.output_dir / "concat.txt"
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    full = proj.output_dir / "full_movie.mp4"
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
            "-movflags", "+faststart", str(full))
    durations = [_probe_duration(c) for c in clips]
    srt = write_srt(script, durations, proj.output_dir / "full_movie.srt")

    chapters, t = [], 0.0
    for scene, d in zip(script.scenes, durations):
        chapters.append(f"{fmt_time(t)} {scene.title}")
        t += d
    (proj.output_dir / "youtube_chapters.txt").write_text("\n".join(chapters) + "\n")
    return {"full": full, "srt": srt}


def make_vertical_clips(proj: Project, script: Script, max_seconds: int = 90) -> list[Path]:
    """Cut 9:16 clips (TikTok / Reels / Shorts) from scenes marked social_hook."""
    out_dir = proj.output_dir / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    hooks = [s for s in script.scenes if s.social_hook]
    for n, scene in enumerate(hooks, 1):
        src = proj.scenes_dir / f"{scene.id}.mp4"
        if not src.exists():
            continue
        cap = proj.output_dir / f"cap-{scene.id}.txt"
        cap.write_text(textwrap.fill(scene.title, 26))
        f = _font_opt()
        fc = (
            "[0:v]split[a][b];"
            "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2[bg];"
            "[b]scale=1080:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
            f"drawtext={f}textfile='{cap}':fontcolor=white:fontsize=64:borderw=4:bordercolor=black:"
            "x=(w-text_w)/2:y=220,"
            f"drawtext={f}text='Part {n} – full film on YouTube':fontcolor=white:fontsize=42:"
            "borderw=3:bordercolor=black:x=(w-text_w)/2:y=h-300[v]"
        )
        out = out_dir / f"clip_{n:02d}_{scene.id}.mp4"
        _ffmpeg("-i", str(src), "-t", str(max_seconds), "-filter_complex", fc,
                "-map", "[v]", "-map", "0:a:0", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "21", "-c:a", "aac", "-movflags", "+faststart", str(out))
        cap.unlink()
        made.append(out)
    return made
