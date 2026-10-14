import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Dict

import pytest

PACKAGES = {"util": "galaxy-util", "app": "galaxy-app"}

VERSION_PY_TEMPLATE = """VERSION_MAJOR = "{major}"
VERSION_MINOR = "{minor}"
VERSION = VERSION_MAJOR + (f".{{VERSION_MINOR}}" if VERSION_MINOR else "")
"""

PACKAGE_PYPROJECT_TEMPLATE = """[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "{version}"
requires-python = ">=3.8"
dependencies = [{dependencies}]
"""

PACKAGE_HISTORY = """History
-------

.. to_doc

-------------------
26.1.0 (2026-06-01)
-------------------

* Initial release
"""

ROOT_PYPROJECT = """[project]
name = "galaxy-workspace"
version = "0.1.0"
requires-python = ">=3.8"
dependencies = ["galaxy-app"]

[tool.uv]
package = false
find-links = ["wheels"]
no-index = true

[tool.uv.sources]
galaxy-util = { workspace = true }
galaxy-app = { workspace = true }

[tool.uv.workspace]
members = ["packages/util", "packages/app"]
"""


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


def show(repo: Path, ref: str, path: str) -> str:
    return git(repo, "show", f"{ref}:{path}")


def root_version(repo: Path, ref: str) -> str:
    major, minor = re.findall(r'^VERSION_M\w+ = "(.*)"$', show(repo, ref, "lib/galaxy/version/__init__.py"), re.M)
    return f"{major}.{minor}"


def package_versions(repo: Path, ref: str) -> Dict[str, str]:
    """Versions declared by each package's pyproject.toml, by package name."""
    versions = {}
    for package, name in PACKAGES.items():
        pyproject = show(repo, ref, f"packages/{package}/pyproject.toml")
        match = re.search(r'^version = "(.*)"$', pyproject, re.M)
        assert match, pyproject
        versions[name] = match.group(1)
    return versions


def locked_version(repo: Path, ref: str, name: str) -> str:
    match = re.search(f'^name = "{name}"\nversion = "(.*)"$', show(repo, ref, "uv.lock"), re.M)
    assert match, name
    return match.group(1)


def locked_versions(repo: Path, ref: str) -> Dict[str, str]:
    """Versions recorded for each package in uv.lock, by package name."""
    return {name: locked_version(repo, ref, name) for name in PACKAGES.values()}


def client_version(repo: Path, ref: str) -> str:
    return json.loads(show(repo, ref, "client/package.json"))["version"]


def write_versions(root: Path, major: str, minor: str, package_version: str, client_version: str) -> None:
    (root / "lib" / "galaxy" / "version" / "__init__.py").write_text(
        VERSION_PY_TEMPLATE.format(major=major, minor=minor)
    )
    for package, name in PACKAGES.items():
        dependencies = '"galaxy-util"' if package == "app" else '"foo"'
        (root / "packages" / package / "pyproject.toml").write_text(
            PACKAGE_PYPROJECT_TEMPLATE.format(name=name, version=package_version, dependencies=dependencies)
        )
    package_json = {"name": "@galaxyproject/galaxy-client", "version": client_version, "private": True}
    (root / "client" / "package.json").write_text(f"{json.dumps(package_json, indent=2)}\n")


def write_wheel(directory: Path, name: str, version: str) -> None:
    dist_info = f"{name}-{version}.dist-info"
    files = {
        f"{name}/__init__.py": "",
        f"{dist_info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        f"{dist_info}/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    files[f"{dist_info}/RECORD"] = "".join(f"{path},,\n" for path in [*files, f"{dist_info}/RECORD"])
    with zipfile.ZipFile(directory / f"{name}-{version}-py3-none-any.whl", "w") as wheel:
        for path, contents in files.items():
            wheel.writestr(path, contents)


def uv_lock(root: Path) -> None:
    subprocess.run(["uv", "lock", "--quiet"], cwd=root, check=True)


def commit_all(root: Path, message: str) -> None:
    git(root, "add", "--all")
    git(root, "commit", "--quiet", "-m", message)


@pytest.fixture(autouse=True)
def isolated_git_config(tmp_path_factory, monkeypatch):
    """Keep the user's git configuration (commit signing, hooks) out of test repositories."""
    git_config = tmp_path_factory.mktemp("git-config") / "gitconfig"
    git_config.write_text("[user]\n\tname = Test\n\temail = test@example.org\n[init]\n\tdefaultBranch = dev\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def upstream_repo(tmp_path) -> Path:
    """A bare repository holding a Galaxy-like ``dev`` branch with a root uv workspace.

    Like Galaxy at the time 26.2 was branched, ``dev`` is at 26.2.dev0 while the
    packages and the client still declare 26.1.dev0, and there is no root package.json.
    A local wheel index stands in for PyPI: ``foo`` is locked at 1.0 while 1.1 is available.
    """
    seed = tmp_path / "seed"
    (seed / "lib" / "galaxy" / "version").mkdir(parents=True)
    (seed / "client").mkdir()
    for package in PACKAGES:
        (seed / "packages" / package).mkdir(parents=True)
        (seed / "packages" / package / "HISTORY.rst").write_text(PACKAGE_HISTORY)
    (seed / "packages" / "packages_by_dep_dag.txt").write_text("util\n\napp\n")
    (seed / "Makefile").write_text("VENV?=.venv\nRELEASE_CURR:=26.2\nRELEASE_UPSTREAM:=upstream\n")
    (seed / "pyproject.toml").write_text(ROOT_PYPROJECT)
    write_versions(seed, "26.2", "dev0", "26.1.dev0", "26.1.dev0")
    (seed / "wheels").mkdir()
    write_wheel(seed / "wheels", "foo", "1.0")
    git(seed, "init", "--quiet")
    uv_lock(seed)
    write_wheel(seed / "wheels", "foo", "1.1")
    commit_all(seed, "Initial commit")
    upstream = tmp_path / "upstream.git"
    git(tmp_path, "clone", "--quiet", "--bare", str(seed), str(upstream))
    return upstream


@pytest.fixture
def fork_repo(tmp_path) -> Path:
    fork = tmp_path / "fork.git"
    git(tmp_path, "init", "--quiet", "--bare", str(fork))
    return fork


@pytest.fixture
def galaxy_clone(tmp_path, upstream_repo, fork_repo) -> Path:
    """A clone with ``upstream`` and ``origin`` (the fork) remotes, as release managers have."""
    clone = tmp_path / "galaxy"
    git(tmp_path, "clone", "--quiet", "--origin", "upstream", str(upstream_repo), str(clone))
    git(clone, "remote", "add", "origin", str(fork_repo))
    return clone
