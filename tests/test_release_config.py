import datetime
from pathlib import Path

import pytest
from packaging.version import Version

from galaxy_release_util import release_config
from galaxy_release_util.release_config import (
    ReleaseConfig,
    load_release_config,
    load_repo_owner,
)

# Captured before the autouse stub below replaces it.
real_milestone_due_dates = release_config.milestone_due_dates

FULL_CONFIG = (
    "current-version: '98.2'\n"
    "previous-version: '98.1'\n"
    "freeze-date: '2099-01-01'\n"
    "release-date: '2099-01-15'\n"
)


@pytest.fixture
def config_dir(tmp_path):
    releases_dir = tmp_path / "doc" / "source" / "releases"
    releases_dir.mkdir(parents=True)
    return releases_dir


@pytest.fixture(autouse=True)
def no_github(monkeypatch):
    """Fail loudly if a test reaches for GitHub without saying so."""

    def _explode(owner, repo):
        raise AssertionError("test unexpectedly queried GitHub milestones")

    monkeypatch.setattr(release_config, "milestone_due_dates", _explode)


@pytest.fixture
def milestones(monkeypatch):
    """Stub the GitHub milestone lookup with a fixed {version: due date} mapping."""

    def _set(due_dates):
        monkeypatch.setattr(release_config, "milestone_due_dates", lambda owner, repo: due_dates)

    return _set


def _write_config(config_dir, filename, content):
    path = config_dir / filename
    path.write_text(content)
    return path


def test_load_release_config_default_path(tmp_path, config_dir):
    _write_config(config_dir, "98.2_release.yml", FULL_CONFIG)
    config = load_release_config(tmp_path, Version("98.2"), use_github=False)
    assert config.current_version == Version("98.2")
    assert config.previous_version == Version("98.1")
    assert config.release_date == datetime.date(2099, 1, 15)
    assert config.freeze_date == datetime.date(2099, 1, 1)
    assert config.owner == "galaxyproject"
    assert config.repo == "galaxy"


def test_load_release_config_explicit_path(tmp_path, config_dir):
    path = _write_config(
        config_dir,
        "custom.yml",
        "current-version: '25.0'\nprevious-version: '24.2'\nrelease-date: '2025-07-01'\n"
        "freeze-date: '2025-06-01'\nowner: myorg\nrepo: myrepo\n",
    )
    config = load_release_config(tmp_path, Version("25.0"), release_config_path=path, use_github=False)
    assert config.current_version == Version("25.0")
    assert config.previous_version == Version("24.2")
    assert config.release_date == datetime.date(2025, 7, 1)
    assert config.freeze_date == datetime.date(2025, 6, 1)
    assert config.owner == "myorg"
    assert config.repo == "myrepo"


def test_load_release_config_explicit_path_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_release_config(tmp_path, Version("99.0"), release_config_path=tmp_path / "nonexistent.yml")


def test_load_release_config_cli_overrides_yaml(tmp_path, config_dir):
    _write_config(config_dir, "98.2_release.yml", FULL_CONFIG)
    config = load_release_config(
        tmp_path,
        Version("98.2"),
        next_version=Version("99.5"),
        release_date=datetime.date(2099, 6, 1),
        use_github=False,
    )
    assert config.next_version == Version("99.5")
    assert config.release_date == datetime.date(2099, 6, 1)
    # Non-overridden values from YAML
    assert config.previous_version == Version("98.1")


def test_load_release_config_needs_no_yaml_or_flags(tmp_path, milestones):
    """The common case: nothing configured locally, everything read off the milestones."""
    milestones(
        {
            Version("26.0"): datetime.date(2026, 1, 27),
            Version("26.1"): datetime.date(2026, 5, 20),
            Version("26.2"): datetime.date(2026, 10, 14),
        }
    )
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.release_date == datetime.date(2026, 5, 20)
    assert config.previous_version == Version("26.0")
    assert config.next_version == Version("26.2")


def test_cli_flags_win_over_milestones(tmp_path, milestones):
    milestones({Version("26.1"): datetime.date(2026, 5, 20), Version("26.2"): datetime.date(2026, 10, 14)})
    config = load_release_config(
        tmp_path,
        Version("26.1"),
        release_date=datetime.date(2026, 6, 1),
        next_version=Version("27.0"),
    )
    assert config.release_date == datetime.date(2026, 6, 1)
    assert config.next_version == Version("27.0")


def test_yaml_wins_over_milestones(tmp_path, config_dir, milestones):
    _write_config(config_dir, "98.2_release.yml", FULL_CONFIG)
    milestones({Version("98.2"): datetime.date(2050, 1, 1)})
    config = load_release_config(tmp_path, Version("98.2"))
    assert config.release_date == datetime.date(2099, 1, 15)


def test_milestone_fills_gaps_left_by_yaml(tmp_path, config_dir, milestones):
    """A YAML without a release date still gets one from the milestone."""
    _write_config(config_dir, "98.2_release.yml", "previous-version: '98.1'\n")
    milestones({Version("98.2"): datetime.date(2050, 1, 1), Version("99.0"): None})
    config = load_release_config(tmp_path, Version("98.2"))
    assert config.previous_version == Version("98.1")
    assert config.release_date == datetime.date(2050, 1, 1)
    assert config.next_version == Version("99.0")


def test_milestone_without_due_date_leaves_release_date_unknown(tmp_path, milestones):
    milestones({Version("98.2"): None})
    config = load_release_config(tmp_path, Version("98.2"))
    assert config.release_date is None


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


def test_falls_back_to_release_notes_when_github_is_unavailable(tmp_path, config_dir, milestones):
    milestones({})
    for documented in ("26.0.rst", "25.1.rst", "24.2.rst"):
        (config_dir / documented).write_text("")
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.previous_version == Version("26.0")
    assert config.next_version == Version("26.2")
    assert config.release_date is None


def test_partial_yaml_is_accepted(tmp_path, config_dir):
    """Fields a command does not need must not be required."""
    _write_config(config_dir, "99.0_release.yml", "current-version: '99.0'\n")
    config = load_release_config(tmp_path, Version("99.0"), use_github=False)
    assert config.release_date is None
    assert config.freeze_date is None


def test_require_reports_missing_values(tmp_path, config_dir):
    _write_config(config_dir, "99.0_release.yml", "current-version: '99.0'\n")
    config = load_release_config(tmp_path, Version("99.0"), use_github=False)
    with pytest.raises(ValueError, match=r"--release-date, --freeze-date"):
        config.require("release_date", "freeze_date")


def test_require_passes_when_values_are_known():
    config = ReleaseConfig(current_version=Version("99.0"), release_date=datetime.date(2099, 1, 1))
    config.require("release_date")


def test_load_release_config_next_version_from_yaml(tmp_path, config_dir):
    _write_config(config_dir, "98.2_release.yml", FULL_CONFIG + "next-version: '99.0'\n")
    config = load_release_config(tmp_path, Version("98.2"), use_github=False)
    assert config.next_version == Version("99.0")


def test_load_release_config_null_field(tmp_path, config_dir):
    _write_config(config_dir, "99.0_release.yml", "current-version: '99.0'\nprevious-version:\n")
    with pytest.raises(ValueError, match="has no value"):
        load_release_config(tmp_path, Version("99.0"), use_github=False)


def test_load_release_config_invalid_version(tmp_path, config_dir):
    _write_config(config_dir, "99.0_release.yml", "current-version: '!!!'\n")
    with pytest.raises(ValueError, match="Invalid 'current-version'"):
        load_release_config(tmp_path, Version("99.0"), use_github=False)


def test_load_release_config_invalid_date(tmp_path, config_dir):
    _write_config(config_dir, "99.0_release.yml", "current-version: '99.0'\nrelease-date: 'not-a-date'\n")
    with pytest.raises(ValueError, match="Invalid 'release-date'"):
        load_release_config(tmp_path, Version("99.0"), use_github=False)


def test_load_release_config_not_a_mapping(tmp_path, config_dir):
    _write_config(config_dir, "99.0_release.yml", "- item1\n- item2\n")
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        load_release_config(tmp_path, Version("99.0"), use_github=False)


def test_load_release_config_empty_yaml(tmp_path, config_dir, milestones):
    _write_config(config_dir, "26.1_release.yml", "")
    milestones({Version("26.1"): datetime.date(2026, 5, 20)})
    config = load_release_config(tmp_path, Version("26.1"))
    assert config.release_date == datetime.date(2026, 5, 20)


def test_load_release_config_version_mismatch(tmp_path, config_dir):
    path = _write_config(config_dir, "99.0_release.yml", "current-version: '98.0'\n")
    with pytest.raises(ValueError, match="does not match release-version argument"):
        load_release_config(tmp_path, Version("99.0"), release_config_path=path, use_github=False)


def test_load_release_config_from_fixture():
    config_path = Path("tests/test_data/release_98.2.yml")
    config = load_release_config(Path("."), Version("98.2"), release_config_path=config_path, use_github=False)
    assert config.current_version == Version("98.2")
    assert config.previous_version == Version("98.1")
    assert config.freeze_date == datetime.date(2099, 1, 1)
    assert config.release_date == datetime.date(2099, 1, 15)


def test_load_repo_owner_from_config(config_dir, tmp_path):
    (config_dir / "98.2_release.yml").write_text(FULL_CONFIG + "owner: 'myorg'\nrepo: 'mygalaxy'\n")
    owner, repo = load_repo_owner(tmp_path, Version("98.2"))
    assert owner == "myorg"
    assert repo == "mygalaxy"


def test_load_repo_owner_point_release(config_dir, tmp_path):
    """Point release version 98.2.1 should find config for 98.2."""
    (config_dir / "98.2_release.yml").write_text(FULL_CONFIG + "owner: 'myorg'\nrepo: 'mygalaxy'\n")
    owner, repo = load_repo_owner(tmp_path, Version("98.2.1"))
    assert owner == "myorg"
    assert repo == "mygalaxy"


def test_load_repo_owner_defaults_when_no_config(tmp_path):
    owner, repo = load_repo_owner(tmp_path, Version("99.0"))
    assert owner == "galaxyproject"
    assert repo == "galaxy"


def test_load_repo_owner_defaults_when_no_owner_in_config(config_dir, tmp_path):
    (config_dir / "98.2_release.yml").write_text(FULL_CONFIG)
    owner, repo = load_repo_owner(tmp_path, Version("98.2"))
    assert owner == "galaxyproject"
    assert repo == "galaxy"
