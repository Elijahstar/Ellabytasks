"""Your own movie recommendations: a queue the agent works through.

Stored in recommendations.json (in the folder you run the agent from), so you
can also edit it by hand or share it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .models import Movie

FILE = Path("recommendations.json")

Status = Literal["queued", "planned", "skipped"]


class Recommendation(BaseModel):
    title: str
    year: int
    logline: str = ""
    genre: str = ""
    director: str = ""
    notes: str = ""      # passed to the scriptwriter
    style: str = ""      # visual style for this film
    minutes: int = 40
    status: Status = "queued"
    project: str = ""    # filled in once the script is written

    def to_movie(self) -> Movie:
        return Movie(title=self.title, year=self.year, logline=self.logline,
                     genre=self.genre, director=self.director, source="your recommendation")


def load() -> list[Recommendation]:
    if not FILE.exists():
        return []
    return [Recommendation.model_validate(r) for r in json.loads(FILE.read_text())]


def save(recs: list[Recommendation]) -> None:
    FILE.write_text(json.dumps([r.model_dump() for r in recs], indent=2, ensure_ascii=False) + "\n")


def find(recs: list[Recommendation], title: str, year: int | None = None) -> Recommendation | None:
    for r in recs:
        if r.title.lower() == title.lower() and (year is None or r.year == year):
            return r
    return None


def add(rec: Recommendation) -> Recommendation:
    recs = load()
    if find(recs, rec.title, rec.year):
        raise ValueError(f"'{rec.title}' ({rec.year}) is already in your recommendations.")
    recs.append(rec)
    save(recs)
    return rec


def remove(title: str) -> Recommendation:
    recs = load()
    r = find(recs, title)
    if not r:
        raise KeyError(f"'{title}' is not in your recommendations.")
    recs.remove(r)
    save(recs)
    return r


def next_queued() -> Recommendation | None:
    return next((r for r in load() if r.status == "queued"), None)


def mark(title: str, year: int, status: Status, project: str = "") -> None:
    recs = load()
    r = find(recs, title, year)
    if r:
        r.status, r.project = status, project or r.project
        save(recs)
