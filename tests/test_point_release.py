import pathlib
from unittest.mock import MagicMock, patch

import pytest
from packaging.version import Version

from galaxy_release_util.point_release import (
    Package,
    bump_package_version,
    commits_to_prs,
    parse_changelog,
    read_package,
)

SETUP_CFG_CONTENTS = """\
[metadata]
name = galaxy-app
version = 23.0.2
author = Galaxy Project
"""

# Shared build config that older branches symlink to as ``pyproject.toml``
SHARED_PYPROJECT_CONTENTS = """\
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
"""

# Newer branches declare the version in a per-package ``pyproject.toml``
PYPROJECT_CONTENTS = """\
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "galaxy-app"
version = "23.0.2"
requires-python = ">=3.10"
"""

HISTORY_RST_SIMPLE = """\
History
-------

.. to_doc

-------------------
23.0.2 (2024-01-15)
-------------------

* Fix bug in tool loading
* Improve performance of history queries

-------------------
23.0.1 (2024-01-01)
-------------------

* Initial point release
"""

HISTORY_RST_WITH_SECTIONS = """\
History
-------

.. to_doc

-------------------
23.0.2 (2024-01-15)
-------------------

Bug fixes
=========

* Fix bug in tool loading

Enhancements
============

* Improve performance of history queries

-------------------
23.0.1 (2024-01-01)
-------------------

* Initial point release
"""

HISTORY_RST_DEV = """\
History
-------

.. to_doc

-----------
23.0.3.dev0
-----------

-------------------
23.0.2 (2024-01-15)
-------------------

* Fix bug in tool loading
"""

HISTORY_RST_BAD_STRUCTURE = """\
Not a real RST document
"""


def _write_package(
    tmp_path: pathlib.Path,
    setup_cfg: str = SETUP_CFG_CONTENTS,
    history_rst: str = HISTORY_RST_SIMPLE,
    pyproject: str = SHARED_PYPROJECT_CONTENTS,
):
    pkg_path = tmp_path / "galaxy-app"
    pkg_path.mkdir()
    if setup_cfg:
        (pkg_path / "setup.cfg").write_text(setup_cfg)
    if pyproject:
        (pkg_path / "pyproject.toml").write_text(pyproject)
    (pkg_path / "HISTORY.rst").write_text(history_rst)
    return pkg_path


class TestReadPackage:
    def test_basic(self, tmp_path):
        pkg_path = _write_package(tmp_path)
        package = read_package(pkg_path)
        assert package.current_version == "23.0.2"
        assert package.name == "galaxy-app"
        assert len(package.package_history) > 0
        assert package.version_file == pkg_path / "setup.cfg"

    def test_pyproject_only(self, tmp_path):
        pkg_path = _write_package(tmp_path, setup_cfg="", pyproject=PYPROJECT_CONTENTS)
        package = read_package(pkg_path)
        assert package.current_version == "23.0.2"
        assert package.version_file == pkg_path / "pyproject.toml"

    def test_setup_cfg_wins_over_shared_pyproject(self, tmp_path):
        # older branches symlink pyproject.toml to a shared, versionless build config
        pkg_path = _write_package(tmp_path)
        assert read_package(pkg_path).version_file == pkg_path / "setup.cfg"

    def test_missing_version(self, tmp_path):
        pkg_path = tmp_path / "broken"
        pkg_path.mkdir()
        (pkg_path / "setup.cfg").write_text("[metadata]\nname = broken\n")
        (pkg_path / "HISTORY.rst").write_text(HISTORY_RST_SIMPLE)
        with pytest.raises(ValueError, match="contains a version line"):
            read_package(pkg_path)

    def test_no_version_file(self, tmp_path):
        pkg_path = tmp_path / "broken"
        pkg_path.mkdir()
        (pkg_path / "HISTORY.rst").write_text(HISTORY_RST_SIMPLE)
        with pytest.raises(ValueError, match="contains a version line"):
            read_package(pkg_path)


class TestBumpPackageVersion:
    def test_bumps_setup_cfg(self, tmp_path):
        pkg_path = _write_package(tmp_path)
        package = read_package(pkg_path)
        bump_package_version(package, Version("23.0.3"))
        assert "version = 23.0.3\n" in (pkg_path / "setup.cfg").read_text()
        assert package.modified_paths == [pkg_path / "setup.cfg"]
        # the shared build config is left alone
        assert (pkg_path / "pyproject.toml").read_text() == SHARED_PYPROJECT_CONTENTS

    def test_bumps_pyproject_keeping_quotes(self, tmp_path):
        pkg_path = _write_package(tmp_path, setup_cfg="", pyproject=PYPROJECT_CONTENTS)
        package = read_package(pkg_path)
        bump_package_version(package, Version("23.0.3"))
        contents = (pkg_path / "pyproject.toml").read_text()
        assert 'version = "23.0.3"\n' in contents
        # unrelated lines are preserved
        assert 'name = "galaxy-app"' in contents
        assert package.modified_paths == [pkg_path / "pyproject.toml"]


class TestParseChangelog:
    def test_simple_changelog(self, tmp_path):
        pkg_path = _write_package(tmp_path)
        package = Package(path=pkg_path, current_version="23.0.2")
        items = parse_changelog(package)
        assert len(items) == 2
        assert items[0].version == Version("23.0.2")
        assert items[0].date == "2024-01-15"
        assert len(items[0].changes) == 2
        assert "Fix bug in tool loading" in items[0].changes[0]
        assert items[1].version == Version("23.0.1")

    def test_sectioned_changelog(self, tmp_path):
        pkg_path = _write_package(tmp_path, history_rst=HISTORY_RST_WITH_SECTIONS)
        package = Package(path=pkg_path, current_version="23.0.2")
        items = parse_changelog(package)
        assert len(items) == 2
        # The sectioned entry should have section headers and items
        changes_text = "\n".join(items[0].changes)
        assert "Bug fixes" in changes_text
        assert "Enhancements" in changes_text
        assert "Fix bug in tool loading" in changes_text

    def test_dev_release_filtered(self, tmp_path):
        pkg_path = _write_package(tmp_path, history_rst=HISTORY_RST_DEV)
        package = Package(path=pkg_path, current_version="23.0.3.dev0")
        items = parse_changelog(package)
        # Dev release without changes should be filtered out
        assert len(items) == 1
        assert items[0].version == Version("23.0.2")

    def test_bad_structure_raises(self, tmp_path):
        pkg_path = _write_package(tmp_path, history_rst=HISTORY_RST_BAD_STRUCTURE)
        package = Package(path=pkg_path, current_version="23.0.2")
        with pytest.raises(ValueError, match="Expected top-level section"):
            parse_changelog(package)


class TestCommitsToPrs:
    def test_commits_mapped_to_prs(self):
        mock_pr = MagicMock()
        mock_pr.number = 42
        mock_pr.title = "Fix something"

        mock_pulls = MagicMock()
        mock_pulls.totalCount = 1
        mock_pulls.__iter__ = MagicMock(return_value=iter([mock_pr]))
        mock_pulls.__bool__ = MagicMock(return_value=True)

        mock_commit = MagicMock()
        mock_commit.get_pulls.return_value = mock_pulls

        mock_repo = MagicMock()
        mock_repo.get_commit.return_value = mock_commit

        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo

        package = Package(path=pathlib.Path("/fake"), current_version="1.0")
        package.commits = {"abc123"}

        with patch("galaxy_release_util.point_release.github_client", return_value=mock_github):
            commits_to_prs([package])

        assert len(package.prs) == 1
        pr = next(iter(package.prs))
        assert pr.number == 42

    def test_commits_without_prs_skipped(self):
        mock_pulls = MagicMock()
        mock_pulls.totalCount = 0
        mock_pulls.__bool__ = MagicMock(return_value=False)

        mock_commit = MagicMock()
        mock_commit.get_pulls.return_value = mock_pulls

        mock_repo = MagicMock()
        mock_repo.get_commit.return_value = mock_commit

        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo

        package = Package(path=pathlib.Path("/fake"), current_version="1.0")
        package.commits = {"abc123", "def456"}

        with patch("galaxy_release_util.point_release.github_client", return_value=mock_github):
            commits_to_prs([package])

        assert len(package.prs) == 0
