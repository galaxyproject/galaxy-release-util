import datetime

import pytest
from packaging.version import Version

from galaxy_release_util import release_config
from galaxy_release_util.release_config import (
    ReleaseConfig,
    load_release_config,
)

# Captured before the autouse stub below replaces it.
real_milestone_due_dates = release_config.milestone_due_dates

GALAXY_MILESTONES = {
    Version("26.0"): datetime.date(2026, 1, 27),
    Version("26.1"): datetime.date(2026, 5, 20),
    Version("26.2"): datetime.date(2026, 10, 14),
}


@pytest.fixture
def releases_dir(tmp_path):
    path = tmp_path / "doc" / "source" / "releases"
    path.mkdir(parents=True)
    return path


@pytest.fixture(autouse=True)
def no_github(monkeypatch):
    """Fail loudly if a test reaches for GitHub without saying so."""

    def _explode(owner, repo):
        raise AssertionError("test unexpectedly queried GitHub milestones")

    monkeypatch.setattr(release_config, "milestone_due_dates", _explode)


@pytest.fixture
def milestones(monkeypatch):
    """Stub the GitHub milestone lookup with a fixed {version: due date} mapping."""

    def _set(due_dates=GALAXY_MILESTONES):
        monkeypatch.setattr(release_config, "milestone_due_dates", lambda owner, repo: due_dates)

    return _set


def test_everything_comes_from_the_milestones(tmp_path, milestones):
    """The common case: nothing passed, everything read off the milestones."""
    milestones()
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.release_date == datetime.date(2026, 5, 20)
    assert config.previous_version == Version("26.0")
    assert config.next_version == Version("26.2")


def test_flags_win_over_milestones(tmp_path, milestones):
    milestones()
    config = load_release_config(
        tmp_path,
        Version("26.1"),
        release_date=datetime.date(2026, 6, 1),
        next_version=Version("27.0"),
        previous_version=Version("25.1"),
        freeze_date=datetime.date(2026, 4, 15),
    )
    assert config.release_date == datetime.date(2026, 6, 1)
    assert config.next_version == Version("27.0")
    assert config.previous_version == Version("25.1")
    assert config.freeze_date == datetime.date(2026, 4, 15)


def test_milestones_fill_only_the_gaps(tmp_path, milestones):
    milestones()
    config = load_release_config(tmp_path, Version("26.1"), next_version=Version("27.0"))
    assert config.next_version == Version("27.0")
    assert config.release_date == datetime.date(2026, 5, 20)


def test_no_api_call_when_flags_cover_everything(tmp_path):
    """The autouse guard would fire if the milestones were consulted here."""
    config = load_release_config(
        tmp_path,
        Version("26.1"),
        previous_version=Version("26.0"),
        next_version=Version("26.2"),
        release_date=datetime.date(2026, 5, 20),
    )
    assert config.release_date == datetime.date(2026, 5, 20)


def test_milestone_without_due_date_leaves_release_date_unknown(tmp_path, milestones):
    milestones({Version("26.1"): None})
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.release_date is None


def test_owner_and_repo_select_the_milestones(tmp_path, monkeypatch):
    seen = {}

    def _record(owner, repo):
        seen["target"] = (owner, repo)
        return {}

    monkeypatch.setattr(release_config, "milestone_due_dates", _record)
    config = load_release_config(tmp_path, Version("26.1"), owner="mvdbeek", repo="galaxy-fork")
    assert seen["target"] == ("mvdbeek", "galaxy-fork")
    assert (config.owner, config.repo) == ("mvdbeek", "galaxy-fork")


def test_owner_and_repo_default_to_galaxy(tmp_path, milestones):
    milestones()
    config = load_release_config(tmp_path, Version("26.1"))
    assert (config.owner, config.repo) == ("galaxyproject", "galaxy")


def test_falls_back_to_release_notes_when_github_is_unavailable(tmp_path, releases_dir, milestones):
    milestones({})
    for documented in ("26.0.rst", "25.1.rst", "24.2.rst"):
        (releases_dir / documented).write_text("")
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.previous_version == Version("26.0")
    assert config.next_version == Version("26.2")
    assert config.release_date is None


def test_previous_version_unknown_without_docs_or_milestones(tmp_path, milestones):
    milestones({})
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.previous_version is None


def test_require_reports_missing_values(tmp_path, milestones):
    milestones({})
    config = load_release_config(tmp_path, Version("26.1"))
    with pytest.raises(ValueError, match=r"--release-date, --freeze-date"):
        config.require("release_date", "freeze_date")


def test_require_error_names_the_repository(tmp_path, milestones):
    milestones({})
    config = load_release_config(tmp_path, Version("26.1"), owner="mvdbeek", repo="galaxy-fork")
    with pytest.raises(ValueError, match="mvdbeek/galaxy-fork"):
        config.require("release_date")


def test_require_passes_when_values_are_known():
    config = ReleaseConfig(current_version=Version("26.1"), release_date=datetime.date(2026, 5, 20))
    config.require("release_date")


class _FakeMilestone:
    def __init__(self, title, due_on):
        self.title = title
        self.due_on = due_on


class _FakeRepo:
    def __init__(self, milestones):
        self._milestones = milestones

    def get_milestones(self, state):
        return self._milestones


class _FakeGithub:
    def __init__(self, repo):
        self._repo = repo

    def get_repo(self, name):
        return self._repo


def test_unparsable_milestone_titles_are_ignored(monkeypatch):
    repo = _FakeRepo(
        [
            _FakeMilestone("Backlog", None),
            _FakeMilestone("26.1", datetime.datetime(2026, 5, 20)),
        ]
    )
    monkeypatch.setattr(release_config, "github_client", lambda: _FakeGithub(repo))
    assert real_milestone_due_dates("galaxyproject", "galaxy") == {Version("26.1"): datetime.date(2026, 5, 20)}


def test_milestone_lookup_failure_is_not_fatal(monkeypatch, capsys):
    def _raise():
        raise RuntimeError("no GitHub auth configured")

    monkeypatch.setattr(release_config, "github_client", _raise)
    assert real_milestone_due_dates("galaxyproject", "galaxy") == {}
    assert "Warning: could not read milestones" in capsys.readouterr().err
