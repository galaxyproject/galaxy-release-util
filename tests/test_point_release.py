import pathlib
from unittest.mock import MagicMock, patch

import pytest
from packaging.version import Version

from galaxy_release_util.point_release import (
    Package,
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


def _write_package(tmp_path: pathlib.Path, setup_cfg: str = SETUP_CFG_CONTENTS, history_rst: str = HISTORY_RST_SIMPLE):
    pkg_path = tmp_path / "galaxy-app"
    pkg_path.mkdir()
    (pkg_path / "setup.cfg").write_text(setup_cfg)
    (pkg_path / "HISTORY.rst").write_text(history_rst)
    return pkg_path


class TestReadPackage:
    def test_basic(self, tmp_path):
        pkg_path = _write_package(tmp_path)
        package = read_package(pkg_path)
        assert package.current_version == "23.0.2"
        assert package.name == "galaxy-app"
        assert len(package.package_history) > 0

    def test_missing_version(self, tmp_path):
        pkg_path = tmp_path / "broken"
        pkg_path.mkdir()
        (pkg_path / "setup.cfg").write_text("[metadata]\nname = broken\n")
        (pkg_path / "HISTORY.rst").write_text(HISTORY_RST_SIMPLE)
        with pytest.raises(ValueError, match="does not contain version line"):
            read_package(pkg_path)


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
