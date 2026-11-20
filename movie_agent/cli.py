"""Command-line interface.  Run `python -m movie_agent --help`."""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

from . import catalog, editor
from . import recommendations as recs
from .models import Movie
from .project import ROOT, Project, fmt_time
from .rights import decide_mode, us_public_domain_cutoff


# ------------------------------------------------------------ discover ----

def cmd_discover(a: argparse.Namespace) -> None:
    if a.online:
        movies = catalog.search_wikidata(a.start, a.end, limit=a.limit)
    else:
        movies = catalog.search_catalog(a.start, a.end, a.genre, a.pd_only, a.query)
        mine = [r.to_movie() for r in recs.load()
                if a.start <= r.year <= a.end and r.status == "queued"
                and (not a.genre or a.genre.lower() in r.genre.lower())
                and (not a.query or a.query.lower() in (r.title + " " + r.logline).lower())]
        if a.pd_only:
            mine = [m for m in mine if decide_mode(m)[0] == "adaptation"]
        known = {(m.title.lower(), m.year) for m in mine}
        movies = mine + [m for m in movies if (m.title.lower(), m.year) not in known]
    cutoff = us_public_domain_cutoff()
    print(f"{'YEAR':<6}{'TITLE':<42}{'GENRE':<20}{'AGENT MODE'}")
    for m in movies[: a.limit]:
        mode, _ = decide_mode(m)
        flag = mode + (" (verify PD)" if m.rights_hint == "verify" and m.year > cutoff else "")
        star = "★ " if m.source == "your recommendation" else ""
        print(f"{m.year:<6}{(star + m.title)[:40]:<42}{m.genre[:18]:<20}{flag}")
        if m.logline and a.verbose:
            print(textwrap.indent(textwrap.fill(m.logline, 80), "      "))
    print(f"\n{len(movies[: a.limit])} films. US public domain cutoff today: released in or before {cutoff}.")
    print("adaptation = retell the film; inspired = original story in the same spirit.")
    print("★ = your recommendation (add more with `recommend add`).")


# ---------------------------------------------------------------- plan ----

def _movie_from_args(a: argparse.Namespace) -> Movie:
    m = catalog.find_movie(a.title, a.year)
    if a.logline:
        m.logline = a.logline
    return m


def cmd_plan(a: argparse.Namespace) -> Project:
    from .scriptwriter import write_script

    movie = _movie_from_args(a)
    rec = recs.find(recs.load(), movie.title, movie.year)
    if rec:  # your recommendation's settings fill in anything not given on the command line
        a.minutes = a.minutes or rec.minutes
        a.style = a.style or rec.style
        a.notes = a.notes or rec.notes
    a.minutes = a.minutes or 40
    mode, statement = decide_mode(movie)
    if a.mode == "inspired":
        mode, statement = "inspired", statement + " Producer chose inspired mode."
    elif a.mode == "adaptation" and mode == "inspired":
        sys.exit("Refusing: this film looks copyrighted, so a direct adaptation is not allowed. "
                 "Use --mode inspired (an original story in its spirit).")
    print(f"Rights check: {statement}\n")
    print(f"Writing a {a.minutes}-minute {mode} script with Claude (this can take a few minutes)...")
    script = write_script(movie, mode, statement, a.minutes, a.style or "", a.notes or "")
    proj = Project.create(script, a.name)
    if rec:
        recs.mark(rec.title, rec.year, "planned", proj.path.name)
    print(f"\nProject created: {proj.path}")
    print(f"  {len(script.scenes)} scenes, runtime {fmt_time(script.total_seconds())}")
    print(f"  Read the script: {proj.path / 'script.md'}")
    return proj


def cmd_list(a: argparse.Namespace) -> None:
    if not ROOT.exists():
        print("No projects yet. Run `plan`.")
        return
    for p in sorted(ROOT.iterdir()):
        if (p / "script.json").exists():
            s = Project(p).load()
            print(f"{p.name:<40} {fmt_time(s.total_seconds())}  {len(s.scenes):>3} scenes  {s.title}")


# -------------------------------------------------------------- script ----

def _show(proj: Project, full: bool) -> None:
    s = proj.load()
    print(f"{s.title}  [{s.mode} of {s.source_movie} ({s.source_year})]")
    print(f"Runtime {fmt_time(s.total_seconds())} / target {s.target_minutes}:00, {len(s.scenes)} scenes\n")
    t = 0
    for sc in s.scenes:
        hook = " ⚡" if sc.social_hook else ""
        print(f"{sc.id:<5}{fmt_time(t)}  {sc.duration_sec:>3}s  {sc.title}{hook}")
        if full:
            print(textwrap.indent(textwrap.fill(sc.narration, 90), "            "))
            print(textwrap.indent(textwrap.fill("VISUAL: " + sc.visual_prompt, 90), "            "))
            print()
        t += sc.duration_sec
    mins = s.total_seconds() / 60
    if not 30 <= mins <= 45:
        print(f"\n⚠ Runtime is {mins:.1f} min, outside 30-45 min. Add/remove scenes or change durations.")


def cmd_script(a: argparse.Namespace) -> None:
    proj = Project.open(a.project)
    if a.action == "show":
        _show(proj, a.full)
        return
    if a.action == "undo":
        proj.undo()
        print("Reverted the last change.")
        _show(proj, False)
        return

    script = proj.load()
    if a.action == "add":
        pos = editor.resolve_position(script, a.after, a.before)
        if a.describe:
            from .scriptwriter import write_new_scene
            print("Asking Claude to write the scene...")
            scene = write_new_scene(script, pos, a.describe, script.next_id())
            editor.insert_scene(script, scene, pos)
        else:
            if not (a.scene_title and a.narration and a.visual):
                sys.exit("Give --describe \"...\" (AI writes it) or all of --title, --narration, --visual.")
            scene = editor.add_manual_scene(script, pos, a.scene_title, a.narration, a.visual, duration_sec=a.duration)
        print(f"Added {scene.id}: {scene.title} ({scene.duration_sec}s)")
    elif a.action == "remove":
        for sc in editor.remove_scenes(script, a.ids):
            print(f"Removed {sc.id}: {sc.title}")
    elif a.action == "move":
        editor.move_scene(script, a.id, a.after, a.before)
        print(f"Moved {a.id}.")
    elif a.action == "edit":
        sc = editor.set_field(script, a.id, a.field, a.value)
        print(f"Updated {sc.id}.{a.field} (duration now {sc.duration_sec}s)")
    elif a.action == "rewrite":
        from .scriptwriter import rewrite_scene
        print("Asking Claude to rewrite the scene...")
        new = rewrite_scene(script, a.id, a.instruction)
        script.scenes[script.find(a.id)] = new
        print(f"Rewrote {new.id}: {new.title}")
    elif a.action == "duplicate":
        sc = editor.duplicate_scene(script, a.id)
        print(f"Duplicated {a.id} as {sc.id}")
    elif a.action == "renumber":
        editor.renumber(script)
        print("Scene ids renumbered S01..; existing renders will be redone on next `render`.")
    proj.save(script)
    _show(proj, False)


# -------------------------------------------------------------- render ----

def cmd_render(a: argparse.Namespace) -> None:
    from . import render

    proj = Project.open(a.project)
    script = proj.load()
    only = {i.strip().lower() for i in a.only.split(",")} if a.only else None
    clips = []
    for n, sc in enumerate(script.scenes, 1):
        if only and sc.id.lower() not in only:
            continue
        print(f"[{n}/{len(script.scenes)}] {sc.id} {sc.title}")
        clips.append(render.render_scene(proj, script, sc, a.video, a.voice, a.force, a.images))
    if only:
        print("Rendered selected scenes. Run without --only to assemble the full film.")
        return
    out = render.assemble(proj, script, clips)
    print(f"\nFull film: {out['full']}\nSubtitles: {out['srt']}")
    if out["credits"].read_text().strip():
        print(f"Image credits: {out['credits']} (the ones that legally need credit are added to the YouTube description)")
    if not a.no_clips:
        made = render.make_vertical_clips(proj, script, a.clip_seconds)
        print(f"Vertical clips: {len(made)} in {proj.output_dir / 'clips'}")


def cmd_clips(a: argparse.Namespace) -> None:
    from . import render

    proj = Project.open(a.project)
    made = render.make_vertical_clips(proj, proj.load(), a.clip_seconds)
    for m in made:
        print(m)


# ------------------------------------------------------------- publish ----

def cmd_publish(a: argparse.Namespace) -> None:
    from . import publish

    proj = Project.open(a.project)
    script = proj.load()
    out = proj.output_dir
    sm = script.social
    caption = f"{sm.short_caption} " + " ".join("#" + h.lstrip("#") for h in sm.hashtags)
    clips = sorted((out / "clips").glob("clip_*.mp4"))

    if a.platform == "youtube":
        video = out / "full_movie.mp4"
        print(f"YouTube: {video} as {a.privacy!r}\n  title: {sm.youtube_title}")
        if a.go:
            vid = publish.upload_youtube(video, script, a.privacy, out / "full_movie.srt",
                                         out / "youtube_chapters.txt")
            print(f"  uploaded: https://youtu.be/{vid}")
    elif a.platform == "instagram":
        if not a.url_template:
            sys.exit("Instagram fetches videos from a public URL. Upload the clips somewhere public and pass "
                     "--url-template 'https://your-cdn/{name}'.")
        for c in clips:
            url = a.url_template.format(name=c.name)
            print(f"Instagram Reel: {url}")
            if a.go:
                print("  published:", publish.upload_instagram_reel(url, caption))
    elif a.platform == "tiktok":
        for c in clips:
            print(f"TikTok: {c}")
            if a.go:
                print("  publish id:", publish.upload_tiktok(c, caption, a.privacy if a.privacy != "private" else "SELF_ONLY"))
    if not a.go:
        print("\n(dry run — add --go to really post)")


# ----------------------------------------------------------- recommend ----

def cmd_recommend(a: argparse.Namespace) -> None:
    if a.action == "add":
        if not 1888 <= a.year <= 2000:
            print(f"Note: {a.year} is outside 1888-2000; adding it anyway.")
        r = recs.add(recs.Recommendation(
            title=a.title, year=a.year, logline=a.logline or "", genre=a.genre or "",
            director=a.director or "", notes=a.notes or "", style=a.style or "",
            minutes=a.minutes or 40,
        ))
        mode, statement = decide_mode(catalog.find_movie(r.title, r.year))
        print(f"Added '{r.title}' ({r.year}) to your recommendations.")
        print(f"Rights check: {statement}")
        if not r.logline:
            print("Tip: add --logline to describe the film; it helps with lesser-known titles.")
    elif a.action == "list":
        items = recs.load()
        if not items:
            print("No recommendations yet. Add one: recommend add \"Title\" --year 1925")
            return
        print(f"{'STATUS':<9}{'YEAR':<6}{'TITLE':<38}{'MIN':<5}{'MODE':<12}PROJECT")
        for r in items:
            mode, _ = decide_mode(catalog.find_movie(r.title, r.year))
            print(f"{r.status:<9}{r.year:<6}{r.title[:36]:<38}{r.minutes:<5}{mode:<12}{r.project}")
    elif a.action == "remove":
        r = recs.remove(a.title)
        print(f"Removed '{r.title}' ({r.year}).")
    elif a.action == "skip":
        r = recs.find(recs.load(), a.title)
        if not r:
            raise KeyError(f"'{a.title}' is not in your recommendations.")
        recs.mark(r.title, r.year, "skipped")
        print(f"Skipped '{r.title}'.")
    elif a.action == "next":
        r = recs.next_queued()
        if not r:
            print("Nothing queued. Add films with `recommend add`.")
            return
        print(f"Next up: {r.title} ({r.year})")
        a.title, a.year, a.logline = r.title, r.year, None
        a.minutes = a.style = a.notes = a.name = None
        a.mode = "auto"
        if a.render:
            cmd_run(a)
        else:
            cmd_plan(a)


# ----------------------------------------------------------------- run ----

def cmd_run(a: argparse.Namespace) -> None:
    proj = cmd_plan(a)
    a.project = str(proj.path)
    a.only, a.force, a.no_clips = None, False, False
    cmd_render(a)
    print("\nDone. Review the script and video, edit scenes with `script ...`, re-run `render` "
          "(only changed scenes are re-rendered), then `publish`.")


# ---------------------------------------------------------------- main ----

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="movie_agent", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="Find interesting films from 1888-2000")
    d.add_argument("--from", dest="start", type=int, default=1888)
    d.add_argument("--to", dest="end", type=int, default=2000)
    d.add_argument("--genre")
    d.add_argument("--query")
    d.add_argument("--pd-only", action="store_true", help="Only films the agent can adapt directly")
    d.add_argument("--online", action="store_true", help="Search Wikidata (most-covered films) instead of the catalog")
    d.add_argument("--limit", type=int, default=50)
    d.add_argument("-v", "--verbose", action="store_true")
    d.set_defaults(func=cmd_discover)

    def plan_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("title")
        sp.add_argument("--year", type=int)
        sp.add_argument("--minutes", type=int, choices=range(30, 46), metavar="30-45",
                        help="Target length (default 40, or your recommendation's setting)")
        sp.add_argument("--style", help="e.g. 'hand-tinted silent film', 'Pixar-like 3D', 'anime'")
        sp.add_argument("--notes", help="Anything extra the writer should know")
        sp.add_argument("--logline", help="Describe the film if it's not in the catalog")
        sp.add_argument("--mode", choices=["auto", "adaptation", "inspired"], default="auto")
        sp.add_argument("--name", help="Project folder name")

    pl = sub.add_parser("plan", help="Pick a film and have Claude write the script")
    plan_args(pl)
    pl.set_defaults(func=cmd_plan)

    sub.add_parser("list", help="List projects").set_defaults(func=cmd_list)

    s = sub.add_parser("script", help="View or edit a script")
    ss = s.add_subparsers(dest="action", required=True)
    x = ss.add_parser("show"); x.add_argument("project"); x.add_argument("--full", action="store_true")
    x = ss.add_parser("add", help="Add a scene (AI-written with --describe, or manual)")
    x.add_argument("project"); x.add_argument("--after", help="Scene id or 'start'"); x.add_argument("--before")
    x.add_argument("--describe", help="What should happen; Claude writes the scene")
    x.add_argument("--title", dest="scene_title"); x.add_argument("--narration"); x.add_argument("--visual")
    x.add_argument("--duration", type=int)
    x = ss.add_parser("remove", help="Remove one or more scenes"); x.add_argument("project"); x.add_argument("ids", nargs="+")
    x = ss.add_parser("move"); x.add_argument("project"); x.add_argument("id")
    x.add_argument("--after"); x.add_argument("--before")
    x = ss.add_parser("edit", help="Change one field of a scene"); x.add_argument("project"); x.add_argument("id")
    x.add_argument("--field", required=True, choices=sorted(editor.EDITABLE_FIELDS))
    x.add_argument("--value", required=True, help="For dialogue, separate lines with |")
    x = ss.add_parser("rewrite", help="Have Claude rewrite a scene"); x.add_argument("project"); x.add_argument("id")
    x.add_argument("instruction")
    x = ss.add_parser("duplicate"); x.add_argument("project"); x.add_argument("id")
    x = ss.add_parser("renumber"); x.add_argument("project")
    x = ss.add_parser("undo"); x.add_argument("project")
    s.set_defaults(func=cmd_script)

    def render_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--video", choices=["pictures", "preview", "command"], default="pictures",
                        help="pictures = free stills with zoom/pan (default); preview = title cards; "
                             "command = your AI video script")
        sp.add_argument("--images", choices=["commons", "command"], default="commons",
                        help="Where pictures come from: commons = free Wikimedia Commons images (default); "
                             "command = your own image generator via MOVIE_AGENT_IMAGE_CMD")
        sp.add_argument("--voice", choices=["piper", "silent", "espeak", "command"], default="piper",
                        help="piper = free natural voice on your computer (default)")
        sp.add_argument("--clip-seconds", type=int, default=90)

    r = sub.add_parser("render", help="Render scenes and assemble the film + clips")
    r.add_argument("project"); render_args(r)
    r.add_argument("--only", help="Comma-separated scene ids")
    r.add_argument("--force", action="store_true"); r.add_argument("--no-clips", action="store_true")
    r.set_defaults(func=cmd_render)

    c = sub.add_parser("clips", help="Re-cut vertical clips for TikTok/Reels/Shorts")
    c.add_argument("project"); c.add_argument("--clip-seconds", type=int, default=90)
    c.set_defaults(func=cmd_clips)

    pb = sub.add_parser("publish", help="Upload to YouTube / Instagram / TikTok (dry run unless --go)")
    pb.add_argument("project"); pb.add_argument("platform", choices=["youtube", "instagram", "tiktok"])
    pb.add_argument("--privacy", default="private", help="YouTube: private/unlisted/public; TikTok: SELF_ONLY/PUBLIC_TO_EVERYONE...")
    pb.add_argument("--url-template", help="Instagram: public URL pattern for clips, with {name}")
    pb.add_argument("--go", action="store_true")
    pb.set_defaults(func=cmd_publish)

    rc = sub.add_parser("recommend", help="Your own movie recommendations for the agent")
    rcs = rc.add_subparsers(dest="action", required=True)
    x = rcs.add_parser("add", help="Recommend a film")
    x.add_argument("title"); x.add_argument("--year", type=int, required=True)
    x.add_argument("--logline", help="One line on what the film is about")
    x.add_argument("--genre"); x.add_argument("--director")
    x.add_argument("--notes", help="Instructions for the scriptwriter, e.g. 'focus on the heroine'")
    x.add_argument("--style", help="Visual style for this film")
    x.add_argument("--minutes", type=int, choices=range(30, 46), metavar="30-45")
    rcs.add_parser("list", help="Show your recommendations")
    x = rcs.add_parser("remove"); x.add_argument("title")
    x = rcs.add_parser("skip", help="Keep it in the list but don't make it"); x.add_argument("title")
    x = rcs.add_parser("next", help="Write the script for the next queued recommendation")
    x.add_argument("--render", action="store_true", help="Also render the film and clips")
    render_args(x)
    rc.set_defaults(func=cmd_recommend)

    rn = sub.add_parser("run", help="Full automation: plan + render + clips")
    plan_args(rn); render_args(rn)
    rn.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (KeyError, ValueError, FileNotFoundError, RuntimeError) as e:
        sys.exit(f"Error: {e.args[0] if e.args else e}")


if __name__ == "__main__":
    main()
