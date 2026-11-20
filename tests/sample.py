from movie_agent.models import Scene, Script, SocialMeta


def sample_script(n: int = 4, dur: int = 30) -> Script:
    return Script(
        title="Shadow Over Wisborg",
        logline="A plague-bringing count sails to a quiet port town.",
        source_movie="Nosferatu", source_year=1922, mode="adaptation",
        rights_statement="Public domain (1922).", target_minutes=40,
        style="Hand-tinted silent-era expressionism",
        scenes=[
            Scene(id=f"S{i:02d}", title=f"Scene {i}", summary=f"Summary {i}",
                  narration=f"Narration for scene {i}. " * 8,
                  visual_prompt=f"Visual {i}", duration_sec=dur, social_hook=(i == 2))
            for i in range(1, n + 1)
        ],
        social=SocialMeta(youtube_title="T", youtube_description="D", tags=["a"],
                          short_caption="C", hashtags=["film"]),
    )
