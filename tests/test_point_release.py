import pathlib
from unittest.mock import MagicMock, patch

import pytest
from packaging.version import Version

from galaxy_release_util import point_release
from galaxy_release_util.metadata import _text_target
from galaxy_release_util.point_release import (
    Package,
    build_meta_dependencies,
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


class TestBuildMetaDependencies:
    def _packages(self, tmp_path):
        meta_path = tmp_path / "packages" / "meta"
        meta_path.mkdir(parents=True)
        pinned_requirements = tmp_path / "lib" / "galaxy" / "dependencies" / "pinned-requirements.txt"
        pinned_requirements.parent.mkdir(parents=True)
        pinned_requirements.write_text("# generated\nrequests==2.32.4\n\n--extra-index-url https://example.com\n")
        return meta_path, [
            Package(path=tmp_path / "packages" / name, current_version="26.1.dev0")
            for name in ("util", "tool_shed", "meta", "app")
        ]

    def test_writes_static_pyproject_dependencies(self, tmp_path):
        meta_path, packages = self._packages(tmp_path)
        pyproject = meta_path / "pyproject.toml"
        pyproject.write_text("""\
[project]
name = "galaxy"
dependencies = [
]

[project.optional-dependencies]
postgresql = ["psycopg[binary]"]
""")

        build_meta_dependencies(packages[2], packages, Version("26.1"))

        contents = pyproject.read_text()
        assert '    "galaxy-app==26.1",\n' in contents
        assert '    "galaxy-util==26.1",\n' in contents
        assert '    "requests==2.32.4",\n' in contents
        assert "galaxy-meta" not in contents
        assert "galaxy-tool_shed" not in contents
        assert 'postgresql = ["psycopg[binary]"]' in contents

    def test_restores_legacy_setup_cfg_requirements_hook(self, tmp_path):
        meta_path, packages = self._packages(tmp_path)
        (meta_path / "pyproject.toml").write_text("""\
[project]
dynamic = ["dependencies", "version"]
name = "galaxy"
""")
        setup_cfg = meta_path / "setup.cfg"
        setup_cfg.write_text("""\
[metadata]
version = 26.1.dev0

[options]
packages = find:
python_requires = >=3.10

[options.extras_require]
postgresql =
    psycopg[binary]
""")

        build_meta_dependencies(packages[2], packages, Version("26.1"))

        assert "[options]\ninstall_requires = file: requirements.txt\n" in setup_cfg.read_text()
        assert (meta_path / "requirements.txt").read_text().splitlines() == [
            "galaxy-app==26.1",
            "galaxy-util==26.1",
            "requests==2.32.4",
        ]


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


def _pr_node(number, labels=("kind/bug",), login="someuser"):
    return {
        "number": number,
        "title": f"Fix thing {number}",
        "url": f"https://github.com/galaxyproject/galaxy/pull/{number}",
        "author": {"login": login},
        "labels": {"nodes": [{"name": label} for label in labels]},
    }


class FakeRequester:
    """Answers the batched commit -> PR query from a commit/PR-node mapping."""

    def __init__(self, commit_to_pr_node):
        self.commit_to_pr_node = commit_to_pr_node
        self.queries = []

    def graphql_query(self, query, variables):
        self.queries.append(variables)
        commits = [value for key, value in variables.items() if key.startswith("commit")]
        repository = {}
        for i, commit in enumerate(commits):
            node = self.commit_to_pr_node.get(commit)
            repository[f"commit{i}"] = {"associatedPullRequests": {"nodes": [node] if node else []}}
        return {}, {"data": {"repository": repository}}


def _patch_github(commit_to_pr_node):
    requester = FakeRequester(commit_to_pr_node)
    mock_github = MagicMock()
    mock_github.requester = requester
    return requester, patch("galaxy_release_util.point_release.github_client", return_value=mock_github)


class TestCommitsToPrs:
    def test_commits_mapped_to_prs(self):
        _, patched = _patch_github({"abc123": _pr_node(42)})
        package = Package(path=pathlib.Path("/fake"), current_version="1.0")
        package.commits = {"abc123"}

        with patched:
            commits_to_prs([package])

        assert len(package.prs) == 1
        pr = next(iter(package.prs))
        assert pr.number == 42
        assert pr.title == "Fix thing 42"
        assert pr.html_url == "https://github.com/galaxyproject/galaxy/pull/42"
        assert pr.user.login == "someuser"
        assert [label.name for label in pr.labels] == ["kind/bug"]

    def test_commits_without_prs_skipped(self):
        _, patched = _patch_github({})
        package = Package(path=pathlib.Path("/fake"), current_version="1.0")
        package.commits = {"abc123", "def456"}

        with patched:
            commits_to_prs([package])

        assert len(package.prs) == 0

    def test_same_pr_across_commits_deduped(self):
        node = _pr_node(42)
        _, patched = _patch_github({"abc123": node, "def456": node})
        package = Package(path=pathlib.Path("/fake"), current_version="1.0")
        package.commits = {"abc123", "def456"}

        with patched:
            commits_to_prs([package])

        assert len(package.prs) == 1

    def test_commits_are_batched(self, monkeypatch):
        monkeypatch.setattr(point_release, "COMMITS_PER_GRAPHQL_QUERY", 2)
        commits = {f"commit{i}": _pr_node(i) for i in range(5)}
        requester, patched = _patch_github(commits)
        package = Package(path=pathlib.Path("/fake"), current_version="1.0")
        package.commits = set(commits)

        with patched:
            commits_to_prs([package])

        assert len(requester.queries) == 3
        assert sorted(pr.number for pr in package.prs) == [0, 1, 2, 3, 4]

    def test_prs_are_queried_for_the_requested_repo(self):
        requester, patched = _patch_github({"abc123": _pr_node(42)})
        package = Package(path=pathlib.Path("/fake"), current_version="1.0")
        package.commits = {"abc123"}

        with patched:
            commits_to_prs([package], owner="someowner", repo_name="somerepo")

        assert requester.queries[0]["owner"] == "someowner"
        assert requester.queries[0]["name"] == "somerepo"

    def test_missing_author_falls_back_to_ghost(self):
        node = _pr_node(42)
        node["author"] = None
        _, patched = _patch_github({"abc123": node})
        package = Package(path=pathlib.Path("/fake"), current_version="1.0")
        package.commits = {"abc123"}

        with patched:
            commits_to_prs([package])

        assert next(iter(package.prs)).user.login == "ghost"

    def test_pr_summary_drives_changelog_categorization(self):
        _, patched = _patch_github({"abc123": _pr_node(42, labels=("kind/enhancement", "area/tools"))})
        package = Package(path=pathlib.Path("/fake"), current_version="1.0")
        package.commits = {"abc123"}

        with patched:
            commits_to_prs([package])

        assert _text_target(next(iter(package.prs)), skip_merge=False) == "enhancement_tag_tools\n"
