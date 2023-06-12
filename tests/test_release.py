import pathlib

import pytest

from galaxy_release_util.point_release import (
    get_next_devN_version,
    get_root_version,
)

VERSION_PY_CONTENTS = """VERSION_MAJOR = "23.0"
VERSION_MINOR = "2"
VERSION = VERSION_MAJOR + (f".{VERSION_MINOR}" if VERSION_MINOR else "")
"""


@pytest.fixture()
def galaxy_root(tmp_path: pathlib.Path):
    version_py = tmp_path / "lib" / "galaxy" / "version.py"
    version_py.parent.mkdir(parents=True)
    version_py.write_text(VERSION_PY_CONTENTS)
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
