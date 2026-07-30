import datetime
from types import SimpleNamespace

import pytest
from packaging.version import Version

from galaxy_release_util import release_config
from galaxy_release_util.release_config import (
    ReleaseConfig,
    due_dates_by_version,
    load_release_config,
    resolve_from_milestones,
)

# The 26.x milestones as GitHub reports them.
GALAXY_MILESTONES = {
    Version("26.0"): datetime.date(2026, 1, 27),
    Version("26.1"): datetime.date(2026, 7, 30),
    Version("26.2"): datetime.date(2026, 10, 14),
}


def _config(**kwargs) -> ReleaseConfig:
    return ReleaseConfig(current_version=Version("26.1"), **kwargs)


def _milestone(title, due_on=None):
    """Stand-in for a PyGithub Milestone, which is a title and a due date to us."""
    return SimpleNamespace(title=title, due_on=due_on)


# Reading milestones off GitHub -------------------------------------------------


def test_milestone_titles_become_versions_and_due_dates_become_dates():
    milestones = [_milestone("26.1", datetime.datetime(2026, 7, 30))]
    assert due_dates_by_version(milestones) == {Version("26.1"): datetime.date(2026, 7, 30)}


def test_milestones_not_named_after_a_release_are_skipped():
    milestones = [_milestone("Backlog"), _milestone("sprint 4"), _milestone("26.1")]
    assert list(due_dates_by_version(milestones)) == [Version("26.1")]


def test_milestone_without_a_due_date_maps_to_none():
    assert due_dates_by_version([_milestone("26.1")]) == {Version("26.1"): None}


def test_milestone_lookup_failure_is_not_fatal(monkeypatch, capsys):
    """A missing token must degrade to local resolution, not abort the release."""

    def _raise():
        raise RuntimeError("no GitHub auth configured")

    monkeypatch.setattr(release_config, "github_client", _raise)
    assert release_config.milestone_due_dates("galaxyproject", "galaxy") == {}
    assert "Warning: could not read milestones" in capsys.readouterr().err


# Resolving a release against the milestones ------------------------------------


def test_release_date_is_the_due_date_of_its_own_milestone():
    config = _config()
    resolve_from_milestones(config, GALAXY_MILESTONES)
    assert config.release_date == datetime.date(2026, 7, 30)


def test_surrounding_versions_are_the_neighbouring_milestones():
    config = _config()
    resolve_from_milestones(config, {Version(v): None for v in ("24.0", "25.1", "26.0", "26.2", "27.0")})
    assert config.previous_version == Version("26.0")
    assert config.next_version == Version("26.2")


def test_values_already_set_survive_the_milestones():
    config = _config(release_date=datetime.date(2026, 6, 1), next_version=Version("27.0"))
    resolve_from_milestones(config, GALAXY_MILESTONES)
    assert config.release_date == datetime.date(2026, 6, 1)
    assert config.next_version == Version("27.0")
    assert config.previous_version == Version("26.0")  # the remaining gap is still filled


def test_release_date_stays_unknown_when_its_milestone_has_no_due_date():
    config = _config()
    resolve_from_milestones(config, {Version("26.1"): None, Version("26.0"): datetime.date(2026, 1, 27)})
    assert config.release_date is None
    assert config.previous_version == Version("26.0")


def test_nothing_is_invented_when_there_are_no_milestones():
    config = _config()
    resolve_from_milestones(config, {})
    assert (config.release_date, config.previous_version, config.next_version) == (None, None, None)


# What a command is allowed to demand -------------------------------------------


def test_require_names_the_missing_flags_and_the_repository():
    config = _config(owner="mvdbeek", repo="galaxy-fork")
    with pytest.raises(ValueError) as excinfo:
        config.require("release_date", "freeze_date")
    assert "--release-date, --freeze-date" in str(excinfo.value)
    assert "mvdbeek/galaxy-fork" in str(excinfo.value)


def test_require_accepts_a_resolved_value():
    _config(release_date=datetime.date(2026, 7, 30)).require("release_date")


# Falling back when GitHub is unreachable ---------------------------------------


@pytest.fixture
def offline(monkeypatch):
    """Every milestone lookup comes up empty, as it would with no network."""
    monkeypatch.setattr(release_config, "milestone_due_dates", lambda owner, repo: {})


def test_previous_version_falls_back_to_the_documented_releases(tmp_path, offline):
    releases = tmp_path / "doc" / "source" / "releases"
    releases.mkdir(parents=True)
    for name in ("24.2.rst", "25.1.rst", "26.0.rst", "26.1_announce.rst", "index.rst"):
        (releases / name).write_text("")
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.previous_version == Version("26.0")


def test_next_version_falls_back_to_the_next_minor(tmp_path, offline):
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.next_version == Version("26.2")


def test_release_date_has_no_fallback(tmp_path, offline):
    """Nothing on disk records it, so the command must ask for it rather than guess."""
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.release_date is None


def test_milestones_are_not_read_when_the_flags_cover_everything(tmp_path, monkeypatch):
    def _explode(owner, repo):
        raise AssertionError("milestones were read despite every value being supplied")

    monkeypatch.setattr(release_config, "milestone_due_dates", _explode)
    load_release_config(
        tmp_path,
        Version("26.1"),
        previous_version=Version("26.0"),
        next_version=Version("26.2"),
        release_date=datetime.date(2026, 7, 30),
    )
