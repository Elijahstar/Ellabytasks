"""Template: connect any AI video service to movie_agent.

movie_agent calls this once per scene:

    export MOVIE_AGENT_VIDEO_CMD='python providers/video_provider_template.py \
        --prompt-file {prompt_file} --seconds {duration} --out {out}'

Your job: read the prompt, ask your video service for a clip, save an .mp4 to
--out. Any length/size is fine: movie_agent loops or trims it to the scene's
duration and scales it to 1920x1080. Most services make 5-10 s clips, so for a
40-60 s scene either loop one clip or generate several and join them here.

Fill in generate_clip() with the official SDK / REST call of the service you
use (Runway, Luma, Kling, Google Veo, Pika, a local model...). Keep API keys in
environment variables, never in this file.
"""

import argparse
from pathlib import Path


def generate_clip(prompt: str, seconds: int, out: Path) -> None:
    raise NotImplementedError(
        "Call your AI video provider here and write the resulting MP4 to `out`."
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--seconds", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    generate_clip(Path(a.prompt_file).read_text(), a.seconds, Path(a.out))


if __name__ == "__main__":
    main()
