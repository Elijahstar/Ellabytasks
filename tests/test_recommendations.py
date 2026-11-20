import pytest

from movie_agent import recommendations as recs
from movie_agent.catalog import find_movie
from movie_agent.cli import main
from movie_agent.rights import decide_mode


@pytest.fixture(autouse=True)
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_add_list_remove_and_queue(capsys):
    main(["recommend", "add", "The Lost World", "--year", "1925",
          "--logline", "Explorers find dinosaurs", "--minutes", "35", "--style", "stop-motion"])
    main(["recommend", "add", "Casablanca", "--year", "1942"])
    with pytest.raises(ValueError):
        recs.add(recs.Recommendation(title="the lost world", year=1925))
    main(["recommend", "list"])
    out = capsys.readouterr().out
    assert "The Lost World" in out and "inspired" in out and "adaptation" in out

    assert recs.next_queued().title == "The Lost World"
    recs.mark("The Lost World", 1925, "planned", "the-lost-world-1925")
    assert recs.next_queued().title == "Casablanca"
    main(["recommend", "skip", "Casablanca"])
    assert recs.next_queued() is None
    main(["recommend", "remove", "Casablanca"])
    assert [r.title for r in recs.load()] == ["The Lost World"]


def test_recommendation_used_by_lookup_and_discover(capsys):
    main(["recommend", "add", "The Lost World", "--year", "1925", "--genre", "Adventure"])
    m = find_movie("The Lost World")  # no --year needed any more
    assert m.year == 1925 and m.source == "your recommendation"
    main(["discover", "--from", "1920", "--to", "1930"])
    assert "★ The Lost World" in capsys.readouterr().out


def test_catalog_rights_info_kept():
    recs.add(recs.Recommendation(title="Charade", year=1963, notes="focus on Paris"))
    m = find_movie("Charade")
    assert m.rights_hint == "verify" and m.logline and decide_mode(m)[0] == "adaptation"
