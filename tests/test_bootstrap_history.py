import os
from pathlib import Path

import pytest
from click.testing import CliRunner
from packaging.version import Version

from galaxy_release_util import bootstrap_history
from galaxy_release_util.bootstrap_history import (
    _get_previous_release_version,
    _get_release_version_strings,
    check_blocking_issues,
    check_blocking_prs,
    create_changelog,
)


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


def test_get_previous_release_version(monkeypatch):
    monkeypatch.setattr(
        bootstrap_history, "_get_release_version_strings", lambda x: sorted(["22.01", "22.05", "23.0", "23.1"])
    )

    assert _get_previous_release_version(None, Version("15.1")) is None
    assert _get_previous_release_version(None, Version("22.01")) is None
    assert _get_previous_release_version(None, Version("22.05")) == Version("22.01")
    assert _get_previous_release_version(None, Version("23.0")) == Version("22.05")
    assert _get_previous_release_version(None, Version("23.1")) == Version("23.0")
    assert _get_previous_release_version(None, Version("23.2")) == Version("23.1")
    assert _get_previous_release_version(None, Version("99.99")) == Version("23.1")


def test_get_release_version_strings(monkeypatch):
    filenames = [
        "15.0.not_rst",
        "22.01.rst",
        "22.05.rst",
        "23.0.rst",
        "23.1.rst",
        "23.not_a_release.rst",
        "not_a_release.23.rst",
    ]
    monkeypatch.setattr(bootstrap_history, "_get_release_documentation_filenames", lambda x: sorted(filenames))
    assert _get_release_version_strings(None) == ["22.01", "22.05", "23.0", "23.1"]


def test_get_release_version_strings_rstrip_regression(monkeypatch):
    """Verify that filenames ending with characters in '.rst' are handled correctly.

    The old implementation used f.rstrip('.rst') which strips individual characters,
    not the suffix. For example, 'foo.rst'.rstrip('.rst') would strip trailing
    r, s, t, and . characters. This test verifies the fix.
    """
    filenames = [
        "22.01.rst",
        "23.0.rst",
    ]
    monkeypatch.setattr(bootstrap_history, "_get_release_documentation_filenames", lambda x: sorted(filenames))
    result = _get_release_version_strings(None)
    assert result == ["22.01", "23.0"]
    # These must preserve the full version string before .rst
    assert "22.01" in result
    assert "23.0" in result


def test_create_changelog(
    monkeypatch,
    announcement_file,
    user_announcement_file,
    prs_file,
    next_release_announcement_file,
):
    monkeypatch.setattr(bootstrap_history, "verify_galaxy_root", lambda x: None)
    monkeypatch.setattr(
        bootstrap_history, "_load_prs", lambda *args, **kwargs: None
    )  # We don't want to call github's API on test data.
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        # Write a release config YAML
        config_content = (
            "current-version: '98.2'\n"
            "previous-version: '98.1'\n"
            "next-version: '99.0'\n"
            "release-date: '2099-01-15'\n"
            "freeze-date: '2099-01-01'\n"
        )
        config_path = Path("doc/source/releases/release_98.2.yml")
        config_path.write_text(config_content)
        result = runner.invoke(
            create_changelog, ["98.2", "--galaxy-root", "."]
        )  # version 98.2 to be released on January 15, 2099
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


def test_create_changelog_dry_run(monkeypatch):
    monkeypatch.setattr(bootstrap_history, "verify_galaxy_root", lambda x: None)
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        config_content = (
            "current-version: '98.2'\n"
            "previous-version: '98.1'\n"
            "next-version: '99.0'\n"
            "release-date: '2099-01-15'\n"
            "freeze-date: '2099-01-01'\n"
        )
        config_path = Path("doc/source/releases/release_98.2.yml")
        config_path.write_text(config_content)
        result = runner.invoke(
            create_changelog, ["98.2", "--galaxy-root", ".", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert "Dry run: skipping GitHub API call" in result.output


def test_check_blocking_prs_dry_run(monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        config_content = (
            "current-version: '98.2'\n"
            "previous-version: '98.1'\n"
            "next-version: '99.0'\n"
            "release-date: '2099-01-15'\n"
        )
        config_path = Path("doc/source/releases/release_98.2.yml")
        config_path.write_text(config_content)
        result = runner.invoke(
            check_blocking_prs, ["98.2", "--galaxy-root", ".", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert "Dry run: would check blocking PRs" in result.output


def test_check_blocking_issues_dry_run(monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        config_content = (
            "current-version: '98.2'\n"
            "previous-version: '98.1'\n"
            "next-version: '99.0'\n"
            "release-date: '2099-01-15'\n"
        )
        config_path = Path("doc/source/releases/release_98.2.yml")
        config_path.write_text(config_content)
        result = runner.invoke(
            check_blocking_issues, ["98.2", "--galaxy-root", ".", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert "Dry run: would check blocking issues" in result.output
