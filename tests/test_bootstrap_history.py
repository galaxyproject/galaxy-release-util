import datetime
import os
from pathlib import Path

import pytest
from click.testing import CliRunner
from packaging.version import Version

from galaxy_release_util import (
    bootstrap_history,
    release_config,
)
from galaxy_release_util.bootstrap_history import (
    check_blocking_issues,
    check_blocking_prs,
    create_changelog,
    create_release_issue,
)

MILESTONES = {
    Version("98.1"): datetime.date(2098, 7, 15),
    Version("98.2"): datetime.date(2099, 1, 15),
    Version("99.0"): datetime.date(2099, 7, 15),
}


@pytest.fixture
def release_files_dir():
    return Path(".") / "tests" / "test_data"


@pytest.fixture
def announcement_file(release_files_dir):
    with open(release_files_dir / "98.2_announce.rst") as f:
        return f.read()


@pytest.fixture
def user_announcement_file(release_files_dir):
    with open(release_files_dir / "98.2_announce_user.rst") as f:
        return f.read()


@pytest.fixture
def next_release_announcement_file(release_files_dir):
    with open(release_files_dir / "99.0_announce.rst") as f:
        return f.read()


@pytest.fixture
def prs_file(release_files_dir):
    with open(release_files_dir / "98.2_prs.rst") as f:
        return f.read()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Never let the tests reach GitHub; milestones are stubbed per test instead."""
    monkeypatch.setattr(bootstrap_history, "verify_galaxy_root", lambda x: None)
    monkeypatch.setattr(release_config, "milestone_due_dates", lambda owner, repo: {})


@pytest.fixture
def milestones(monkeypatch):
    def _set(due_dates=MILESTONES):
        monkeypatch.setattr(release_config, "milestone_due_dates", lambda owner, repo: due_dates)

    return _set


def test_create_changelog_from_milestones_only(
    monkeypatch,
    milestones,
    announcement_file,
    user_announcement_file,
    prs_file,
    next_release_announcement_file,
):
    """No config YAML, no date or version flags: the milestones supply everything."""
    milestones()
    monkeypatch.setattr(bootstrap_history, "_load_prs", lambda *args, **kwargs: None)
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(create_changelog, ["98.2"])
        assert result.exit_code == 0, result.output

        releases_path = Path("doc") / "source" / "releases"
        with open(releases_path / "98.2_announce.rst") as f:
            assert f.read() == announcement_file
        with open(releases_path / "98.2_announce_user.rst") as f:
            assert f.read() == user_announcement_file
        with open(releases_path / "98.2_prs.rst") as f:
            assert f.read() == prs_file
        with open(releases_path / "99.0_announce.rst") as f:
            assert f.read() == next_release_announcement_file


def test_create_changelog_from_flags(monkeypatch, announcement_file, next_release_announcement_file):
    """Flags still work when the milestones are unavailable."""
    monkeypatch.setattr(bootstrap_history, "_load_prs", lambda *args, **kwargs: None)
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(
            create_changelog,
            ["98.2", "--galaxy-root", ".", "--next-version", "99.0", "--release-date", "2099-01-15"],
        )
        assert result.exit_code == 0, result.output

        releases_path = Path("doc") / "source" / "releases"
        with open(releases_path / "98.2_announce.rst") as f:
            assert f.read() == announcement_file
        with open(releases_path / "99.0_announce.rst") as f:
            assert f.read() == next_release_announcement_file


def test_create_changelog_reads_milestones_of_the_given_repo(monkeypatch):
    """--owner/--repo decide which milestones are consulted."""
    seen = {}

    def _record(owner, repo):
        seen["target"] = (owner, repo)
        return MILESTONES

    monkeypatch.setattr(release_config, "milestone_due_dates", _record)
    monkeypatch.setattr(bootstrap_history, "_load_prs", lambda *args, **kwargs: None)
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(create_changelog, ["98.2", "--owner", "mvdbeek", "--repo", "galaxy-fork"])
        assert result.exit_code == 0, result.output
        assert seen["target"] == ("mvdbeek", "galaxy-fork")


def test_create_changelog_reports_unresolvable_release_date():
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(create_changelog, ["98.2"])
        assert result.exit_code != 0
        assert "--release-date" in result.output
        assert "milestone titled '98.2'" in result.output


def test_create_changelog_does_not_ask_for_unused_values(milestones):
    """previous-version and freeze-date are irrelevant here and must not be options."""
    milestones()
    runner = CliRunner()
    result = runner.invoke(create_changelog, ["--help"])
    assert result.exit_code == 0
    assert "--previous-version" not in result.output
    assert "--freeze-date" not in result.output


def test_create_changelog_dry_run(milestones):
    milestones()
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(create_changelog, ["98.2", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Dry run: skipping GitHub API call" in result.output


def test_check_blocking_prs_dry_run(milestones):
    milestones()
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(check_blocking_prs, ["98.2", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Dry run: would check blocking PRs" in result.output
        assert "2099-01-15" in result.output


def test_check_blocking_issues_dry_run():
    """Blocking issues are selected by milestone alone, so no dates are needed."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(check_blocking_issues, ["98.2", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Dry run: would check blocking issues" in result.output


def test_create_release_issue_from_milestones(milestones):
    """Only the freeze date, which no milestone records, has to be supplied."""
    milestones()
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(create_release_issue, ["98.2", "--freeze-date", "2098-12-01", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Freeze Release (on or around 2098-12-01)" in result.output
        assert "`99.0` for next release" in result.output


def test_create_release_issue_rejects_invalid_next_version(milestones):
    milestones()
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(
            create_release_issue,
            ["98.2", "--next-version", "98.0", "--freeze-date", "2098-12-01", "--dry-run"],
        )
        assert result.exit_code != 0
        assert "--next-version (98.0) must be greater than release version (98.2)" in result.output


def test_create_release_issue_reports_missing_freeze_date(milestones):
    milestones()
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(create_release_issue, ["98.2", "--dry-run"])
        assert result.exit_code != 0
        assert "--freeze-date" in result.output
