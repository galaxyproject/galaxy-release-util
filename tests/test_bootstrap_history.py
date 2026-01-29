import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from galaxy_release_util import bootstrap_history
from galaxy_release_util.bootstrap_history import (
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
    monkeypatch.setattr(bootstrap_history, "verify_galaxy_root", lambda x: None)
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
    monkeypatch.setattr(bootstrap_history, "verify_galaxy_root", lambda x: None)
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
