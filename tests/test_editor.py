import datetime as dt

import pytest

from movie_agent import editor
from movie_agent.catalog import find_movie, search_catalog
from movie_agent.models import Movie
from movie_agent.project import Project, to_markdown
from movie_agent.rights import decide_mode, us_public_domain_cutoff
from tests.sample import sample_script


def ids(s):
    return [x.id for x in s.scenes]


def test_add_remove_move_duplicate():
    s = sample_script()
    pos = editor.resolve_position(s, after="S02")
    new = editor.add_manual_scene(s, pos, "Extra", "Some words here.", "A ship at dusk")
    assert new.id == "S05" and ids(s) == ["S01", "S02", "S05", "S03", "S04"]
    editor.remove_scenes(s, ["S03", "s01"])
    assert ids(s) == ["S02", "S05", "S04"]
    editor.move_scene(s, "S04", after="start")
    assert ids(s) == ["S04", "S02", "S05"]
    editor.move_scene(s, "S04", before="S05")
    assert ids(s) == ["S02", "S04", "S05"]
    dup = editor.duplicate_scene(s, "S02")
    assert dup.id == "S06" and ids(s)[1] == "S06"


def test_set_field_retimes():
    s = sample_script()
    sc = editor.set_field(s, "S01", "narration", "word " * 240)
    assert sc.duration_sec == 103
    editor.set_field(s, "S01", "dialogue", "ANNA: Hello | HUTTER: Goodbye")
    assert s.scenes[0].dialogue == ["ANNA: Hello", "HUTTER: Goodbye"]
    with pytest.raises(ValueError):
        editor.set_field(s, "S01", "id", "X")
    with pytest.raises(KeyError):
        editor.set_field(s, "S99", "title", "x")


def test_project_save_and_undo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = Project.create(sample_script())
    s = p.load()
    editor.remove_scenes(s, ["S01"])
    p.save(s)
    editor.move_scene(s, "S04", after="start")
    p.save(s)
    assert ids(p.load()) == ["S04", "S02", "S03"]
    p.undo()
    assert ids(p.load()) == ["S02", "S03", "S04"]
    p.undo()
    assert len(p.load().scenes) == 4
    assert "Shadow Over Wisborg" in (p.path / "script.md").read_text()


def test_rights():
    today = dt.date(2026, 11, 20)
    assert us_public_domain_cutoff(today) == 1930
    assert decide_mode(Movie(title="X", year=1930), today)[0] == "adaptation"
    assert decide_mode(Movie(title="X", year=1931), today)[0] == "inspired"
    assert decide_mode(find_movie("Casablanca"), today)[0] == "inspired"
    assert decide_mode(find_movie("Night of the Living Dead"), today)[0] == "adaptation"


def test_catalog():
    assert all(m.year < 1900 for m in search_catalog(1800, 1899))
    assert not any(m.rights_hint == "copyrighted" for m in search_catalog(public_domain_only=True))
    with pytest.raises(ValueError):
        find_movie("Unknown Film")


def test_markdown():
    md = to_markdown(sample_script())
    assert "## S02" in md and "social hook" in md
