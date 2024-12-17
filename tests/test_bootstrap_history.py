import os
from pathlib import Path

import pytest
from click.testing import CliRunner
from packaging.version import Version

from galaxy_release_util import bootstrap_history
from galaxy_release_util.bootstrap_history import (  # _get_release_date,
    _get_next_release_version,
    _get_previous_release_version,
    _get_release_version_strings,
    create_changelog,
)


@pytest.fixture
def release_files_dir():
    return Path(".") / "tests" / "test_data"


@pytest.fixture
def release_file(release_files_dir):
    with open(release_files_dir / "98.2.rst") as f:
        return f.read()


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


def test_get_next_release_version():
    assert _get_next_release_version(Version("25.0")) == Version("25.1")
    assert _get_next_release_version(Version("26.1")) == Version("26.2")


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


def test_create_changelog(
    monkeypatch,
    release_file,
    announcement_file,
    user_announcement_file,
    prs_file,
    next_release_announcement_file,
):
    monkeypatch.setattr(bootstrap_history, "verify_galaxy_root", lambda x: None)
    monkeypatch.setattr(
        bootstrap_history, "_load_prs", lambda x, y, z: None
    )  # We don't want to call github's API on test data.
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs("doc/source/releases")
        result = runner.invoke(
            create_changelog, ["98.2", "--galaxy-root", ".", "--release-date", "2099-1-15", "--next-version", "99.0"]
        )  # version 98.2 to be released on January 15, 2099
        assert result.exit_code == 0

        releases_path = Path("doc") / "source" / "releases"

        with open(releases_path / "98.2.rst") as f:
            assert f.read() == release_file
        with open(releases_path / "98.2_announce.rst") as f:
            assert f.read() == announcement_file
        with open(releases_path / "98.2_announce_user.rst") as f:
            assert f.read() == user_announcement_file
        with open(releases_path / "98.2_prs.rst") as f:
            assert f.read() == prs_file
        with open(releases_path / "99.0_announce.rst") as f:
            assert f.read() == next_release_announcement_file
