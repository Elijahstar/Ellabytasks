"""Find interesting movies from 1888 (the first surviving film) to 2000.

Two sources:
  * a curated built-in catalog (works offline), and
  * Wikidata, ranked by how many Wikipedia language editions cover the film
    (a good proxy for "famous / interesting").
"""

from __future__ import annotations

import requests

from .models import Movie
from .rights import us_public_domain_cutoff

_PD = "public_domain"

CATALOG: list[Movie] = [
    # --- 1800s: the birth of cinema -------------------------------------
    Movie(title="Roundhay Garden Scene", year=1888, director="Louis Le Prince", genre="Actuality", country="UK",
          logline="Two seconds of family members walking in a Leeds garden: the oldest surviving film.", rights_hint=_PD),
    Movie(title="Workers Leaving the Lumière Factory", year=1895, director="Louis Lumière", genre="Actuality", country="France",
          logline="Factory workers stream out of the gates in Lyon, the first film ever shown to a paying audience.", rights_hint=_PD),
    Movie(title="The Arrival of a Train at La Ciotat", year=1896, director="Auguste & Louis Lumière", genre="Actuality", country="France",
          logline="A steam train pulls into a station, legend says sending audiences running.", rights_hint=_PD),
    Movie(title="The House of the Devil", year=1896, director="Georges Méliès", genre="Horror", country="France",
          logline="A bat turns into Mephistopheles in the first known horror film.", rights_hint=_PD),
    # --- Silent era ------------------------------------------------------
    Movie(title="A Trip to the Moon", year=1902, director="Georges Méliès", genre="Sci-fi", country="France",
          logline="Astronomers fire a capsule into the eye of the Moon and battle the Selenites.", rights_hint=_PD),
    Movie(title="The Great Train Robbery", year=1903, director="Edwin S. Porter", genre="Western", country="USA",
          logline="Bandits hold up a steam train and are hunted down by a posse.", rights_hint=_PD),
    Movie(title="Frankenstein", year=1910, director="J. Searle Dawley", genre="Horror", country="USA",
          logline="Edison Studios' first screen version of Mary Shelley's creature.", rights_hint=_PD),
    Movie(title="The Cabinet of Dr. Caligari", year=1920, director="Robert Wiene", genre="Horror", country="Germany",
          logline="A sinister showman uses a sleepwalker to commit murders in a twisted town.", rights_hint=_PD),
    Movie(title="The Kid", year=1921, director="Charlie Chaplin", genre="Comedy-drama", country="USA",
          logline="The Tramp raises an abandoned baby, until the authorities come for the boy.", rights_hint=_PD),
    Movie(title="Nosferatu", year=1922, director="F. W. Murnau", genre="Horror", country="Germany",
          logline="Count Orlok brings plague and terror to the port town of Wisborg.", rights_hint=_PD),
    Movie(title="Safety Last!", year=1923, director="Fred C. Newmeyer & Sam Taylor", genre="Comedy", country="USA",
          logline="A shop clerk must climb a department-store skyscraper to win his girl.", rights_hint=_PD),
    Movie(title="Sherlock Jr.", year=1924, director="Buster Keaton", genre="Comedy", country="USA",
          logline="A projectionist dreams himself into the detective film he is screening.", rights_hint=_PD),
    Movie(title="The Phantom of the Opera", year=1925, director="Rupert Julian", genre="Horror", country="USA",
          logline="A masked genius haunts the Paris Opera and obsesses over a young soprano.", rights_hint=_PD),
    Movie(title="The Gold Rush", year=1925, director="Charlie Chaplin", genre="Comedy", country="USA",
          logline="The Lone Prospector braves the Klondike, starvation and a teetering cabin.", rights_hint=_PD),
    Movie(title="Battleship Potemkin", year=1925, director="Sergei Eisenstein", genre="Historical drama", country="USSR",
          logline="Sailors mutiny over rotten meat, sparking a massacre on the Odessa Steps.", rights_hint=_PD),
    Movie(title="The General", year=1926, director="Buster Keaton", genre="Action comedy", country="USA",
          logline="A Southern engineer chases Union spies who stole his beloved locomotive.", rights_hint=_PD),
    Movie(title="Metropolis", year=1927, director="Fritz Lang", genre="Sci-fi", country="Germany",
          logline="In a city of towers and machines, a robot double incites the workers to revolt.", rights_hint=_PD),
    Movie(title="Wings", year=1927, director="William A. Wellman", genre="War", country="USA",
          logline="Two rival pilots become friends in the skies over World War I France.", rights_hint=_PD),
    Movie(title="The Passion of Joan of Arc", year=1928, director="Carl Theodor Dreyer", genre="Historical drama", country="France",
          logline="The trial and execution of Joan of Arc, told almost entirely in close-ups.", rights_hint=_PD),
    Movie(title="All Quiet on the Western Front", year=1930, director="Lewis Milestone", genre="War", country="USA",
          logline="German schoolboys enlist with patriotic fervour and meet the horror of the trenches.",
          rights_hint=_PD, rights_note="The source novel (Remarque, 1929) is also PD in the US."),
    # --- Later films widely reported to have lapsed into US public domain
    Movie(title="Reefer Madness", year=1936, director="Louis J. Gasnier", genre="Exploitation", country="USA",
          logline="A lurid 1930s morality tale about teenagers and marijuana.", rights_hint="verify",
          rights_note="Copyright was reportedly never renewed."),
    Movie(title="His Girl Friday", year=1940, director="Howard Hawks", genre="Screwball comedy", country="USA",
          logline="A newspaper editor schemes to keep his ex-wife, his best reporter, on one last story.",
          rights_hint="verify", rights_note="Film copyright not renewed; the source play 'The Front Page' may still be protected."),
    Movie(title="Detour", year=1945, director="Edgar G. Ulmer", genre="Film noir", country="USA",
          logline="A hitchhiking pianist is trapped by a dead man's identity and a ruthless drifter.", rights_hint="verify"),
    Movie(title="D.O.A.", year=1950, director="Rudolph Maté", genre="Film noir", country="USA",
          logline="A poisoned man has days to live and uses them to find his own murderer.", rights_hint="verify"),
    Movie(title="The Little Shop of Horrors", year=1960, director="Roger Corman", genre="Horror comedy", country="USA",
          logline="A florist's clerk raises a plant that hungers for human blood.", rights_hint="verify",
          rights_note="The 1960 film only; the later musical is copyrighted."),
    Movie(title="Carnival of Souls", year=1962, director="Herk Harvey", genre="Horror", country="USA",
          logline="After surviving a car crash, an organist is drawn to an abandoned lakeside pavilion.", rights_hint="verify"),
    Movie(title="Charade", year=1963, director="Stanley Donen", genre="Romantic thriller", country="USA",
          logline="A widow in Paris is hunted for the fortune her husband stole.", rights_hint="verify",
          rights_note="Published without a valid copyright notice."),
    Movie(title="The Last Man on Earth", year=1964, director="Ubaldo Ragona & Sidney Salkow", genre="Horror", country="Italy/USA",
          logline="The sole survivor of a plague hunts the undead by day and is besieged by night.", rights_hint="verify",
          rights_note="Film is PD in the US; the novel 'I Am Legend' is not, so don't borrow beyond the film."),
    Movie(title="Night of the Living Dead", year=1968, director="George A. Romero", genre="Horror", country="USA",
          logline="Strangers barricade a farmhouse against the risen dead.", rights_hint="verify",
          rights_note="Released without a copyright notice."),
    # --- Classics still under copyright: the agent writes ORIGINAL stories inspired by them
    Movie(title="Casablanca", year=1942, director="Michael Curtiz", genre="Romantic drama", country="USA",
          logline="A cynical club owner in wartime Morocco must choose between love and virtue.", rights_hint="copyrighted"),
    Movie(title="Psycho", year=1960, director="Alfred Hitchcock", genre="Thriller", country="USA",
          logline="A secretary on the run checks into a lonely motel run by a troubled young man.", rights_hint="copyrighted"),
    Movie(title="2001: A Space Odyssey", year=1968, director="Stanley Kubrick", genre="Sci-fi", country="UK/USA",
          logline="A mysterious monolith guides humanity from the dawn of man to Jupiter.", rights_hint="copyrighted"),
    Movie(title="The Godfather", year=1972, director="Francis Ford Coppola", genre="Crime", country="USA",
          logline="The reluctant son of a mafia patriarch becomes the family's ruthless new head.", rights_hint="copyrighted"),
    Movie(title="Jaws", year=1975, director="Steven Spielberg", genre="Thriller", country="USA",
          logline="A police chief, a scientist and a fisherman hunt a great white shark.", rights_hint="copyrighted"),
    Movie(title="Back to the Future", year=1985, director="Robert Zemeckis", genre="Sci-fi comedy", country="USA",
          logline="A teenager accidentally travels to 1955 and must get his parents together.", rights_hint="copyrighted"),
    Movie(title="Titanic", year=1997, director="James Cameron", genre="Romance", country="USA",
          logline="A poor artist and a rich young woman fall in love aboard the doomed liner.", rights_hint="copyrighted"),
    Movie(title="The Matrix", year=1999, director="The Wachowskis", genre="Sci-fi action", country="USA",
          logline="A hacker learns his reality is a simulation and joins the rebellion.", rights_hint="copyrighted"),
]

_WIKIDATA_URL = "https://query.wikidata.org/sparql"
_SPARQL = """
SELECT ?film ?filmLabel (MIN(?y) AS ?year) (SAMPLE(?dirLabel) AS ?director)
       (SAMPLE(?genreLabel) AS ?genre) ?links WHERE {{
  ?film wdt:P31 wd:Q11424; wdt:P577 ?date; wikibase:sitelinks ?links.
  BIND(YEAR(?date) AS ?y)
  FILTER(?y >= {start} && ?y <= {end} && ?links >= {min_links})
  OPTIONAL {{ ?film wdt:P57 ?dir. ?dir rdfs:label ?dirLabel. FILTER(LANG(?dirLabel) = "en") }}
  OPTIONAL {{ ?film wdt:P136 ?g. ?g rdfs:label ?genreLabel. FILTER(LANG(?genreLabel) = "en") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
GROUP BY ?film ?filmLabel ?links
ORDER BY DESC(?links)
LIMIT {limit}
"""


def search_catalog(
    start: int = 1888,
    end: int = 2000,
    genre: str | None = None,
    public_domain_only: bool = False,
    query: str | None = None,
) -> list[Movie]:
    cutoff = us_public_domain_cutoff()
    out = []
    for m in CATALOG:
        if not (start <= m.year <= end):
            continue
        if genre and genre.lower() not in m.genre.lower():
            continue
        if query and query.lower() not in (m.title + " " + m.logline).lower():
            continue
        if public_domain_only and not (m.year <= cutoff or m.rights_hint in ("public_domain", "verify")):
            continue
        out.append(m)
    return sorted(out, key=lambda m: m.year)


def search_wikidata(start: int, end: int, limit: int = 25, min_links: int = 30, timeout: int = 60) -> list[Movie]:
    """Most-covered films released between start and end (inclusive)."""
    q = _SPARQL.format(start=start, end=end, limit=limit, min_links=min_links)
    r = requests.get(
        _WIKIDATA_URL,
        params={"query": q, "format": "json"},
        headers={"User-Agent": "movie-agent/0.1 (classic film research tool)"},
        timeout=timeout,
    )
    r.raise_for_status()
    movies = []
    for row in r.json()["results"]["bindings"]:
        movies.append(
            Movie(
                title=row["filmLabel"]["value"],
                year=int(row["year"]["value"]),
                director=row.get("director", {}).get("value", ""),
                genre=row.get("genre", {}).get("value", ""),
                source=f"wikidata ({row['links']['value']} wikis)",
            )
        )
    return movies


def find_movie(title: str, year: int | None = None) -> Movie:
    """Look a title up in your recommendations, then the catalog; otherwise return a
    bare Movie the user described."""
    from . import recommendations

    rec = recommendations.find(recommendations.load(), title, year)
    if rec:
        movie = rec.to_movie()
        for m in CATALOG:  # keep the catalog's rights info and fill in blanks
            if m.title.lower() == rec.title.lower() and m.year == rec.year:
                movie.rights_hint, movie.rights_note = m.rights_hint, m.rights_note
                movie.logline = movie.logline or m.logline
                movie.genre = movie.genre or m.genre
                movie.director = movie.director or m.director
        return movie
    for m in CATALOG:
        if m.title.lower() == title.lower() and (year is None or m.year == year):
            return m
    for m in CATALOG:
        if title.lower() in m.title.lower() and (year is None or m.year == year):
            return m
    if year is None:
        raise ValueError(f"'{title}' is not in the built-in catalog; pass --year so rights can be checked.")
    return Movie(title=title, year=year, source="user")
