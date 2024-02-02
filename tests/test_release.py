import pathlib

import pytest

from galaxy_release_util.point_release import (
    get_next_devN_version,
    get_root_version,
    get_sorted_package_paths,
)

VERSION_PY_CONTENTS = """VERSION_MAJOR = "23.0"
VERSION_MINOR = "2"
VERSION = VERSION_MAJOR + (f".{VERSION_MINOR}" if VERSION_MINOR else "")
"""

PACKAGES_BY_DEP_DAG_CONTENTS = """
foo

bar
#this is a comment
baz
"""


def write_contents(path: pathlib.Path, contents: str):
    path.parent.mkdir(parents=True)
    path.write_text(contents)


@pytest.fixture()
def galaxy_root(tmp_path: pathlib.Path):
    write_contents(tmp_path / "lib" / "galaxy" / "version.py", VERSION_PY_CONTENTS)
    write_contents(tmp_path / "packages" / "packages_by_dep_dag.txt", PACKAGES_BY_DEP_DAG_CONTENTS)
    return tmp_path


def test_get_root_version(galaxy_root):
    version = get_root_version(galaxy_root)
    assert version.major == 23
    assert version.minor == 0
    assert version.micro == 2


def test_get_next_devN_version(galaxy_root):
    version = get_next_devN_version(galaxy_root)
    assert version.is_devrelease
    assert version.major == 23
    assert version.minor == 0
    assert version.micro == 3
    assert version.dev == 0


def test_get_sorted_package_paths(galaxy_root):
    packages = get_sorted_package_paths(galaxy_root)
    assert len(packages) == 3
    assert packages[0].name == "foo"
    assert packages[1].name == "bar"
    assert packages[2].name == "baz"
