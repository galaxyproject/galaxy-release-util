import datetime
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

TEST_DATA = Path(".") / "tests" / "test_data"

UPSTREAM_MILESTONES = {
    Version("98.1"): datetime.date(2098, 7, 15),
    Version("98.2"): datetime.date(2099, 1, 15),
    Version("99.0"): datetime.date(2099, 7, 15),
}


@pytest.fixture
def expected():
    """The release files as they should come out, keyed by name."""

    def _read(name):
        return (TEST_DATA / name).read_text()

    return _read


@pytest.fixture
def galaxy_root(tmp_path):
    """A directory that satisfies the real verify_galaxy_root check."""
    (tmp_path / "lib" / "galaxy" / "version").mkdir(parents=True)
    (tmp_path / "lib" / "galaxy" / "version" / "__init__.py").write_text("")
    (tmp_path / "doc" / "source" / "releases").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def releases_dir(galaxy_root):
    return galaxy_root / "doc" / "source" / "releases"


@pytest.fixture(autouse=True)
def no_milestones(monkeypatch):
    """Milestones come up empty unless a test says otherwise, so none of this hits GitHub."""
    monkeypatch.setattr(release_config, "milestone_due_dates", lambda owner, repo: {})


@pytest.fixture
def milestones(monkeypatch):
    """Publish milestones, either for every repository or per (owner, repo)."""

    def _set(due_dates=UPSTREAM_MILESTONES, per_repo=None):
        lookup = (lambda owner, repo: per_repo[(owner, repo)]) if per_repo else (lambda owner, repo: due_dates)
        monkeypatch.setattr(release_config, "milestone_due_dates", lookup)

    return _set


@pytest.fixture
def no_pr_scraping(monkeypatch):
    """Skip the walk over every pull request GitHub has; the generated files are what matter."""
    monkeypatch.setattr(bootstrap_history, "_load_prs", lambda *args, **kwargs: None)


@pytest.mark.parametrize(
    "extra_args",
    [
        pytest.param([], id="from-milestones"),
        pytest.param(["--next-version", "99.0", "--release-date", "2099-01-15"], id="from-flags"),
    ],
)
def test_create_changelog_writes_the_release_files(galaxy_root, releases_dir, milestones, no_pr_scraping, expected, extra_args):
    milestones()
    result = CliRunner().invoke(create_changelog, ["98.2", "--galaxy-root", str(galaxy_root), *extra_args])
    assert result.exit_code == 0, result.output

    for name in ("98.2_announce.rst", "98.2_announce_user.rst", "98.2_prs.rst", "99.0_announce.rst"):
        assert (releases_dir / name).read_text() == expected(name)


def test_owner_and_repo_choose_which_milestones_are_read(galaxy_root, releases_dir, milestones, no_pr_scraping):
    """A fork with a later 98.2 due date must produce a later date in the announcement."""
    milestones(
        per_repo={
            ("galaxyproject", "galaxy"): UPSTREAM_MILESTONES,
            ("mvdbeek", "galaxy-fork"): {Version("98.2"): datetime.date(2099, 6, 15), Version("99.0"): None},
        }
    )
    result = CliRunner().invoke(
        create_changelog,
        ["98.2", "--galaxy-root", str(galaxy_root), "--owner", "mvdbeek", "--repo", "galaxy-fork"],
    )
    assert result.exit_code == 0, result.output
    assert "98.2 Galaxy Release (June 2099)" in (releases_dir / "98.2_announce.rst").read_text()


def test_create_changelog_reports_an_unresolvable_release_date(galaxy_root):
    result = CliRunner().invoke(create_changelog, ["98.2", "--galaxy-root", str(galaxy_root)])
    assert result.exit_code != 0
    assert "--release-date" in result.output
    assert "milestone titled '98.2'" in result.output


def test_create_changelog_does_not_ask_for_values_it_never_reads():
    """The bug this guards: create-changelog demanded a previous version and a freeze date."""
    result = CliRunner().invoke(create_changelog, ["--help"])
    assert result.exit_code == 0
    assert "--previous-version" not in result.output
    assert "--freeze-date" not in result.output


def test_create_changelog_dry_run_writes_files_but_skips_github(galaxy_root, releases_dir, milestones):
    milestones()
    result = CliRunner().invoke(create_changelog, ["98.2", "--galaxy-root", str(galaxy_root), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Dry run: skipping GitHub API call" in result.output
    assert (releases_dir / "98.2_announce.rst").exists()


def test_check_blocking_prs_dry_run_reports_the_resolved_date(galaxy_root, milestones):
    milestones()
    result = CliRunner().invoke(check_blocking_prs, ["98.2", "--galaxy-root", str(galaxy_root), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "2099-01-15" in result.output


def test_check_blocking_issues_needs_no_dates(galaxy_root):
    """Issues are selected by milestone alone, so the empty milestone lookup must not matter."""
    result = CliRunner().invoke(check_blocking_issues, ["98.2", "--galaxy-root", str(galaxy_root), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Dry run: would check blocking issues" in result.output


def test_create_release_issue_needs_only_the_freeze_date(galaxy_root, milestones):
    milestones()
    result = CliRunner().invoke(
        create_release_issue,
        ["98.2", "--galaxy-root", str(galaxy_root), "--freeze-date", "2098-12-01", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "Freeze Release (on or around 2098-12-01)" in result.output
    assert "`99.0` for next release" in result.output  # next version, from the milestones
    assert "release_98.1" in result.output  # previous version, from the milestones


def test_create_release_issue_rejects_a_next_version_that_precedes_the_release(galaxy_root, milestones):
    milestones()
    result = CliRunner().invoke(
        create_release_issue,
        ["98.2", "--galaxy-root", str(galaxy_root), "--next-version", "98.0", "--freeze-date", "2098-12-01", "--dry-run"],
    )
    assert result.exit_code != 0
    assert "--next-version (98.0) must be greater than release version (98.2)" in result.output


def test_create_release_issue_reports_a_missing_freeze_date(galaxy_root, milestones):
    milestones()
    result = CliRunner().invoke(create_release_issue, ["98.2", "--galaxy-root", str(galaxy_root), "--dry-run"])
    assert result.exit_code != 0
    assert "--freeze-date" in result.output


def test_galaxy_root_is_verified(tmp_path):
    """An empty directory is not a Galaxy checkout."""
    result = CliRunner().invoke(create_changelog, ["98.2", "--galaxy-root", str(tmp_path)])
    assert result.exit_code != 0
    assert "Galaxy files not found" in str(result.exception)
