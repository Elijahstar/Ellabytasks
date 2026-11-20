# Ellabytasks

## Classic Movie → AI Film Agent

An agent that finds interesting films from cinema's first century (1888–2000),
has Claude write a **30–45 minute** script for an AI-generated retelling, lets
you **add, remove, move and rewrite scenes**, renders the film, and cuts
vertical clips for **YouTube, Instagram Reels and TikTok**.

```
discover ─► plan (Claude writes script) ─► edit script ─► render ─► clips ─► publish
                                             ▲              │
                                             └── re-render only changed scenes
```

### ⚖️ Copyright: read this first

Turning someone else's film into a video for monetised channels is only safe
when the film is in the **public domain**. The agent checks every film and
picks a mode:

| Mode | When | What Claude writes |
|---|---|---|
| `adaptation` | Released in or before **1930** (US public domain as of 2026), or a later film known to have lapsed into PD | A retelling of the film's story in fresh words |
| `inspired` | Anything still under copyright (e.g. *Casablanca*, *Jaws*, *The Matrix*) | A **wholly original** story sharing only the era, genre and mood: new characters, plot and dialogue |

The agent refuses `--mode adaptation` for copyrighted films. Films marked
"verify PD" are widely reported to be public domain but you should confirm
before monetising. A PD film can still be based on a protected novel or score,
and other countries have different rules. This is a practical guard, not legal
advice. YouTube, TikTok and Instagram also require you to label realistic AI
content; the upload code sets the AI-content flags where the APIs support them.

### Install

```bash
pip install -r requirements.txt
# ffmpeg is required: https://ffmpeg.org/download.html  (apt install ffmpeg / brew install ffmpeg)
export ANTHROPIC_API_KEY=sk-ant-...        # from https://console.anthropic.com
```

### Quick start

```bash
# 1. Find films (built-in catalog; add --online to search Wikidata for the most famous films of any period)
python -m movie_agent discover --from 1900 --to 1930 -v
python -m movie_agent discover --pd-only --genre horror
python -m movie_agent discover --online --from 1950 --to 1960

# 2. Claude writes a 40-minute script  -> projects/nosferatu-1922/script.md
python -m movie_agent plan "Nosferatu" --minutes 40 --style "hand-tinted 1920s expressionist, film grain"

# A film that's not in the catalog: give the year (and a one-line description)
python -m movie_agent plan "The Lost World" --year 1925 --logline "Explorers find living dinosaurs on a South American plateau"

# 3. Read / edit the script (see below), then render
python -m movie_agent render nosferatu-1922

# Or do it all in one go
python -m movie_agent run "Metropolis" --minutes 35
```

### Editing the script

Every change is saved to `script.json` + a readable `script.md`, and the
previous version is kept, so `undo` always works.

```bash
P=nosferatu-1922
python -m movie_agent script show $P            # timeline with ids & timestamps (--full for text)

# Add a scene: Claude writes it from your description...
python -m movie_agent script add $P --after S05 --describe "A flashback to the count's childhood in the castle"
# ...or write it yourself
python -m movie_agent script add $P --before S10 --title "EXT. HARBOUR - DAWN" \
    --narration "The ship drifts in with no one at the helm." --visual "Ghost ship gliding through fog, 1830s German port"

python -m movie_agent script remove  $P S07 S08                 # remove scenes
python -m movie_agent script move    $P S12 --after S03         # reorder (--after start for the opening)
python -m movie_agent script rewrite $P S04 "Make it scarier and add a twist at the end"
python -m movie_agent script edit    $P S04 --field narration --value "New voice-over text..."
python -m movie_agent script edit    $P S04 --field dialogue  --value "ELLEN: Who is there? | ORLOK: Your guest."
python -m movie_agent script edit    $P S04 --field social_hook --value yes   # use it as a TikTok/Reels clip
python -m movie_agent script duplicate $P S04
python -m movie_agent script undo    $P
```

`show` warns when the runtime falls outside 30–45 minutes. Durations are
re-estimated automatically when you change narration or dialogue.
You can also edit `script.json` by hand.

### Rendering

`render` creates one clip per scene in `assets/scenes/`, then:

- `output/full_movie.mp4`: the 16:9 1080p film for YouTube
- `output/full_movie.srt`: subtitles
- `output/youtube_chapters.txt`: chapter timestamps for the description
- `output/clips/clip_NN_SXX.mp4`: 9:16 vertical clips (≤90 s) from scenes marked ⚡ social hook

Scenes you haven't changed are not re-rendered, so editing one scene is cheap.

**Video providers**

| `--video` | What it does |
|---|---|
| `preview` (default) | Free offline title cards showing each scene's narration, to check timing and flow before paying for generation |
| `command` | Runs `MOVIE_AGENT_VIDEO_CMD` per scene so you can plug in **any** AI video service |

```bash
export MOVIE_AGENT_VIDEO_CMD='python providers/video_provider_template.py --prompt-file {prompt_file} --seconds {duration} --out {out}'
python -m movie_agent render nosferatu-1922 --video command --voice command
```

Fill in `providers/video_provider_template.py` with the SDK of the service you
choose. Placeholders: `{prompt_file} {out} {duration} {width} {height} {scene_id}`.

**Voice providers** (`--voice`): `silent`, `espeak` (free, robotic; needs
`espeak-ng`), or `command` via `MOVIE_AGENT_TTS_CMD` (placeholders
`{text_file} {out} {scene_id}`), e.g. a script calling your favourite TTS service.

Use `--only S03,S04` to try generation on a few scenes before rendering everything.

### Publishing (dry run unless you add `--go`)

```bash
python -m movie_agent publish nosferatu-1922 youtube --privacy private      # full film + subtitles + chapters
python -m movie_agent publish nosferatu-1922 tiktok                         # each vertical clip
python -m movie_agent publish nosferatu-1922 instagram --url-template 'https://my-bucket.example.com/{name}'
```

| Platform | Setup |
|---|---|
| YouTube | Create an OAuth "Desktop app" client in Google Cloud with YouTube Data API v3 enabled; save it as `client_secret.json`. The first upload opens a browser to log in. |
| Instagram | Business/Creator account linked to a Facebook Page. Set `IG_USER_ID` and `IG_ACCESS_TOKEN`. Instagram downloads videos from a public URL, so upload the clips to public storage first. |
| TikTok | Register an app with the Content Posting API; set `TIKTOK_ACCESS_TOKEN` (scope `video.publish`). Unaudited apps can only post privately (`SELF_ONLY`). |

The 30–45 minute film goes to YouTube; Reels and TikTok get the short clips,
each pointing viewers to the full film.

### Configuration

| Variable | Default | |
|---|---|---|
| `MOVIE_AGENT_MODEL` | `claude-opus-5-5` | Claude model for writing |
| `MOVIE_AGENT_EFFORT` | `high` | `low`/`medium`/`high`/`xhigh`/`max` |

Script requests use automatic server-side fallback: if Claude declines a
request, the API retries it on a fallback model in the same call.

### Project layout

```
movie_agent/
  catalog.py      film discovery (curated list + Wikidata)
  rights.py       public-domain check → adaptation / inspired mode
  scriptwriter.py Claude: full scripts, new scenes, rewrites (structured JSON output)
  editor.py       add / remove / move / duplicate / edit scenes
  project.py      project folders, history & undo, Markdown export
  render.py       per-scene rendering, assembly, subtitles, vertical clips
  publish.py      YouTube / Instagram / TikTok uploads
  cli.py          command line
providers/        template for plugging in an AI video service
tests/            python -m pytest tests
```
