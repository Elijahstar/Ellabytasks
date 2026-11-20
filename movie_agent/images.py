"""Free pictures for each scene.

Sources:
  commons  - Wikimedia Commons: public-domain and openly licensed photos, paintings
             and film stills. Free, no account. Only images that are public domain,
             CC0 or CC BY are used (no ShareAlike / NonCommercial / NoDerivatives),
             and the credits are saved so they can go in your video description.
  command  - runs MOVIE_AGENT_IMAGE_CMD to make each picture yourself, e.g. a free
             local AI image model (Stable Diffusion, FLUX...) on your own computer.
             Placeholders: {prompt_file} {out} {scene_id} {index}
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from .models import Scene, Script

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia asks automated tools to identify themselves; put your channel or email here if you like.
USER_AGENT = os.environ.get("MOVIE_AGENT_USER_AGENT", "movie-agent/0.1 (classic film picture videos)")
SECONDS_PER_IMAGE = 8
MAX_IMAGES_PER_SCENE = 6


@dataclass
class ImageCredit:
    file: str
    title: str
    license: str
    artist: str
    source_url: str


def license_ok(name: str) -> bool:
    """True for public domain, CC0 and CC BY. False for SA/NC/ND or unknown."""
    s = name.lower().strip()
    if re.search(r"\b(sa|nc|nd)\b", s.replace("-", " ")):
        return False
    return s.startswith(("public domain", "pd", "cc0", "cc by", "cc-by", "no restrictions"))


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def parse_commons(data: dict) -> list[dict]:
    """Turn a Commons API response into usable image hits, best match first."""
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    hits = []
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if info.get("mime") not in ("image/jpeg", "image/png") or not license_ok(lic):
            continue
        if info.get("width", 0) < 640:
            continue
        hits.append({
            "url": info.get("thumburl") or info.get("url"),
            "title": p.get("title", "").removeprefix("File:"),
            "license": lic,
            "artist": _strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown",
            "source_url": info.get("descriptionurl", ""),
        })
    return hits


def search_commons(query: str, limit: int) -> list[dict]:
    r = requests.get(COMMONS_API, timeout=30, headers={"User-Agent": USER_AGENT}, params={
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": min(50, limit * 5),
        "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 2560,
    })
    r.raise_for_status()
    return parse_commons(r.json())[:limit]


def images_needed(duration: float) -> int:
    return max(1, min(MAX_IMAGES_PER_SCENE, round(duration / SECONDS_PER_IMAGE)))


def search_queries(scene: Scene, script: Script) -> list[str]:
    """Queries to try in order: the scene's own, then broader fallbacks."""
    qs = [scene.image_search] if scene.image_search else []
    if script.mode == "adaptation":
        qs.append(f"{script.source_movie} {script.source_year}")
    words = re.sub(r"\b(INT|EXT)\.?\b|[-–—.,:]", " ", scene.title).split()
    qs.append(" ".join(words[:4]))
    return [q for q in qs if q.strip()]


def fetch_scene_images(scene: Scene, script: Script, folder: Path, count: int, source: str) -> list[Path]:
    """Download (or generate) up to `count` images for a scene. Cached by query."""
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps(
        [source, count, scene.image_search, scene.visual_prompt, script.style]).encode()).hexdigest()[:12]
    manifest = folder / "manifest.json"
    if manifest.exists():
        m = json.loads(manifest.read_text())
        files = [folder / f for f in m.get("files", [])]
        if m.get("key") == key and all(f.exists() for f in files):
            return files

    for old in folder.glob("img_*"):
        old.unlink()
    files: list[Path] = []
    credits: list[ImageCredit] = []
    if source == "commons":
        seen: set[str] = set()
        for q in search_queries(scene, script):
            if len(files) >= count:
                break
            for hit in search_commons(q, count):
                if hit["url"] in seen or len(files) >= count:
                    continue
                seen.add(hit["url"])
                ext = ".png" if hit["url"].lower().endswith(".png") else ".jpg"
                out = folder / f"img_{len(files) + 1:02d}{ext}"
                resp = requests.get(hit["url"], timeout=60, headers={"User-Agent": USER_AGENT})
                resp.raise_for_status()
                out.write_bytes(resp.content)
                files.append(out)
                credits.append(ImageCredit(out.name, hit["title"], hit["license"], hit["artist"], hit["source_url"]))
    elif source == "command":
        tpl = os.environ.get("MOVIE_AGENT_IMAGE_CMD")
        if not tpl:
            raise RuntimeError("Set MOVIE_AGENT_IMAGE_CMD, e.g. 'python my_sd.py --prompt-file {prompt_file} --out {out}'")
        prompt_file = folder / "prompt.txt"
        prompt_file.write_text(f"{scene.visual_prompt}\nStyle: {script.style}")
        for i in range(1, count + 1):
            out = folder / f"img_{i:02d}.png"
            cmd = tpl.format(**{k: shlex.quote(str(v)) for k, v in
                                dict(prompt_file=prompt_file, out=out, scene_id=scene.id, index=i).items()})
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if res.returncode != 0 or not out.exists():
                raise RuntimeError(f"Image command failed ({cmd}):\n{res.stderr.strip()[-1500:]}")
            files.append(out)
    else:
        raise ValueError(f"Unknown image source {source!r}")

    manifest.write_text(json.dumps({
        "key": key, "files": [f.name for f in files], "credits": [asdict(c) for c in credits],
    }, indent=1))
    return files


def collect_credits(images_root: Path, scene_ids: list[str]) -> list[dict]:
    out = []
    for sid in scene_ids:
        m = images_root / sid / "manifest.json"
        if m.exists():
            out += json.loads(m.read_text()).get("credits", [])
    # one line per distinct image
    return list({c["source_url"] or c["title"]: c for c in out}.values())


def needs_attribution(c: dict) -> bool:
    return c["license"].lower().replace("-", " ").startswith("cc by")


def credits_text(credits: list[dict], required_only: bool = False) -> str:
    """Full list for image_credits.txt; with required_only, just the CC BY images,
    which must be credited (public-domain and CC0 images need no credit)."""
    if required_only:
        credits = [c for c in credits if needs_attribution(c)]
    if not credits:
        return ""
    lines = ["Image credits (Wikimedia Commons):"]
    for c in credits:
        lines.append(f"- {c['title']} by {c['artist'][:80]} ({c['license']}) {c['source_url']}")
    return "\n".join(lines)
