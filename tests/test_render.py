import shutil

import pytest

from movie_agent import render
from movie_agent.project import Project
from tests.sample import sample_script

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def test_preview_render_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = sample_script(n=3, dur=3)
    proj = Project.create(script)
    clips = [render.render_scene(proj, script, s, "preview", "silent") for s in script.scenes]
    mtime = clips[0].stat().st_mtime_ns
    # unchanged scenes are not re-rendered
    render.render_scene(proj, script, script.scenes[0], "preview", "silent")
    assert clips[0].stat().st_mtime_ns == mtime
    out = render.assemble(proj, script, clips)
    assert 8.5 < render._probe_duration(out["full"]) < 10
    assert "-->" in out["srt"].read_text()
    made = render.make_vertical_clips(proj, script)
    assert len(made) == 1 and made[0].exists()


def test_command_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    script = sample_script(n=1, dur=2)
    proj = Project.create(script)
    monkeypatch.setenv(
        "MOVIE_AGENT_VIDEO_CMD",
        "ffmpeg -loglevel error -y -f lavfi -i testsrc=s=640x360:d={duration} {out}",
    )
    clip = render.render_scene(proj, script, script.scenes[0], "command", "silent")
    assert 1.5 < render._probe_duration(clip) < 3
