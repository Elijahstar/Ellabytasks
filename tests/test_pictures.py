import json
import shutil
import subprocess

import pytest
import requests

from movie_agent import images as img
from movie_agent import render
from movie_agent.project import Project
from tests.sample import sample_script

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def test_license_filter():
    for ok in ["Public domain", "PD-US", "CC0", "CC BY 4.0", "CC-BY-2.0", "No restrictions"]:
        assert img.license_ok(ok), ok
    for bad in ["CC BY-SA 4.0", "CC BY-NC 2.0", "CC BY-ND 3.0", "GFDL", "", "All rights reserved"]:
        assert not img.license_ok(bad), bad


def commons_response():
    def page(i, title, lic, mime="image/jpeg", width=2000):
        return {"index": i, "title": f"File:{title}", "imageinfo": [{
            "url": f"https://upload.example/{title}", "thumburl": f"https://upload.example/thumb/{title}",
            "descriptionurl": f"https://commons.example/File:{title}", "mime": mime, "width": width,
            "extmetadata": {"LicenseShortName": {"value": lic},
                            "Artist": {"value": "<a href='x'>F. W. Murnau</a>"}},
        }]}
    return {"query": {"pages": {
        "3": page(3, "c.jpg", "CC BY 4.0"),
        "1": page(1, "a.jpg", "Public domain"),
        "2": page(2, "b.jpg", "CC BY-SA 3.0"),
        "4": page(4, "d.svg", "Public domain", mime="image/svg+xml"),
        "5": page(5, "e.jpg", "CC0", width=300),
    }}}


def test_parse_commons_order_and_filter():
    hits = img.parse_commons(commons_response())
    assert [h["title"] for h in hits] == ["a.jpg", "c.jpg"]
    assert hits[0]["artist"] == "F. W. Murnau" and hits[0]["url"].endswith("thumb/a.jpg")


def make_image(path, size="1200x900", color="red"):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c={color}:s={size}", "-frames:v", "1", str(path)], check=True)


class FakeResp:
    def __init__(self, data):
        self.content = data

    def raise_for_status(self):
        pass


@needs_ffmpeg
def test_commons_pictures_render_with_credits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src.jpg"
    make_image(src, "800x1200")  # portrait: gets fitted over a blurred background
    queries = []

    def fake_search(q, limit):
        queries.append(q)
        hits = img.parse_commons(commons_response())
        return hits[:limit]

    monkeypatch.setattr(img, "search_commons", fake_search)
    monkeypatch.setattr(img.requests, "get", lambda url, **kw: FakeResp(src.read_bytes()))

    script = sample_script(n=2, dur=14)  # 14 s -> 2 pictures
    script.scenes[0].image_search = "Nosferatu 1922 ship"
    proj = Project.create(script)
    clips = [render.render_scene(proj, script, s, "pictures", "silent") for s in script.scenes]
    assert queries[0] == "Nosferatu 1922 ship"
    assert 13.5 < render._probe_duration(clips[0]) < 15
    out = render.assemble(proj, script, clips)
    full = out["credits"].read_text()
    required = (proj.output_dir / "image_credits_required.txt").read_text()
    assert "a.jpg" in full and "c.jpg" in full
    assert "c.jpg" in required and "a.jpg" not in required  # public domain needs no credit

    # Cached: a second render of an unchanged scene doesn't search again
    n = len(queries)
    render.render_scene(proj, script, script.scenes[0], "pictures", "silent", force=True)
    assert len(queries) == n


@needs_ffmpeg
def test_no_network_falls_back_to_title_card(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def offline(q, limit):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(img, "search_commons", offline)
    script = sample_script(n=1, dur=3)
    proj = Project.create(script)
    clip = render.render_scene(proj, script, script.scenes[0], "pictures", "silent")
    assert clip.exists() and "title card" in capsys.readouterr().out


@needs_ffmpeg
def test_own_image_generator(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MOVIE_AGENT_IMAGE_CMD",
                       "ffmpeg -loglevel error -y -f lavfi -i color=c=blue:s=1024x1024 -frames:v 1 {out}")
    script = sample_script(n=1, dur=17)
    proj = Project.create(script)
    clip = render.render_scene(proj, script, script.scenes[0], "pictures", "silent", images="command")
    assert 16.5 < render._probe_duration(clip) < 18
    files = json.loads((proj.path / "assets/images/S01/manifest.json").read_text())["files"]
    assert len(files) == img.images_needed(17) == 2
