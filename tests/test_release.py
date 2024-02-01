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


@pytest.fixture(scope="session")
def make_version_file():
    def f(root):
        file = root / "lib" / "galaxy" / "version.py"
        file.parent.mkdir(parents=True)
        file.write_text(VERSION_PY_CONTENTS)

    return f


@pytest.fixture(scope="session")
def make_packages_file():
    def f(root):
        file = root / "packages" / "packages_by_dep_dag.txt"
        file.parent.mkdir(parents=True)
        file.write_text(PACKAGES_BY_DEP_DAG_CONTENTS)

    return f


@pytest.fixture(scope="session")
def galaxy_root(tmp_path_factory, make_version_file, make_packages_file):
    tmp_root = tmp_path_factory.mktemp("galaxy_root")
    make_version_file(tmp_root)
    make_packages_file(tmp_root)
    return tmp_root


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
