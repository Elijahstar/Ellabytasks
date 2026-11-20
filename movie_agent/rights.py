"""Copyright gate.

Retelling a film's plot, characters and dialogue is only safe when the film is in
the public domain. For everything else the agent writes an ORIGINAL story that
only borrows the era, genre and mood ("inspired" mode).

This is a practical heuristic for the United States, not legal advice. Other
countries use different rules (often life of the director + 70 years), and a
public-domain film can still be based on a novel, score or character that is
protected. Check before you monetise.
"""

from __future__ import annotations

import datetime as _dt

from .models import Mode, Movie


def us_public_domain_cutoff(today: _dt.date | None = None) -> int:
    """Latest release year that is public domain in the US.

    Works enter the US public domain on 1 January, 95 years after publication
    (e.g. on 1 Jan 2026, works from 1930 became free).
    """
    today = today or _dt.date.today()
    return today.year - 96


def decide_mode(movie: Movie, today: _dt.date | None = None) -> tuple[Mode, str]:
    """Return (mode, human-readable rights statement)."""
    cutoff = us_public_domain_cutoff(today)
    if movie.year <= cutoff:
        return (
            "adaptation",
            f"'{movie.title}' ({movie.year}) was released in or before {cutoff}, so the "
            "film itself is in the US public domain. The agent may retell its plot and "
            "characters. Check that any source novel or music is also free, and check "
            "local law outside the US.",
        )
    if movie.rights_hint == "public_domain":
        return (
            "adaptation",
            f"'{movie.title}' is listed as public domain. {movie.rights_note}".strip(),
        )
    if movie.rights_hint == "verify":
        return (
            "adaptation",
            f"'{movie.title}' is widely reported to have fallen into the US public "
            f"domain. {movie.rights_note} VERIFY this (e.g. Library of Congress / "
            "copyright renewal records) before publishing; if in doubt, rerun with "
            "--mode inspired.",
        )
    return (
        "inspired",
        f"'{movie.title}' ({movie.year}) is likely still under copyright. The agent "
        "will write an ORIGINAL story inspired only by its era, genre and themes: no "
        "copied plot, character names, dialogue or distinctive scenes.",
    )
