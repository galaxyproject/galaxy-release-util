import datetime
from pathlib import Path

import pytest
from packaging.version import Version

from galaxy_release_util.release_config import load_release_config


@pytest.fixture
def config_dir(tmp_path):
    releases_dir = tmp_path / "doc" / "source" / "releases"
    releases_dir.mkdir(parents=True)
    return releases_dir


def _write_config(config_dir, filename, content):
    path = config_dir / filename
    path.write_text(content)
    return path


def test_load_release_config_default_path(tmp_path, config_dir):
    _write_config(
        config_dir,
        "release_98.2.yml",
        "current-version: '98.2'\nprevious-version: '98.1'\nfreeze-date: '2099-01-01'\nrelease-date: '2099-01-15'\n",
    )
    config = load_release_config(tmp_path, Version("98.2"))
    assert config.current_version == Version("98.2")
    assert config.previous_version == Version("98.1")
    assert config.next_version is None
    assert config.release_date == datetime.date(2099, 1, 15)
    assert config.freeze_date == datetime.date(2099, 1, 1)
    assert config.owner == "galaxyproject"
    assert config.repo == "galaxy"


def test_load_release_config_explicit_path(tmp_path, config_dir):
    path = _write_config(
        config_dir,
        "custom.yml",
        "current-version: '25.0'\nprevious-version: '24.2'\nrelease-date: '2025-07-01'\nfreeze-date: '2025-06-01'\nowner: myorg\nrepo: myrepo\n",
    )
    config = load_release_config(tmp_path, Version("25.0"), release_config_path=path)
    assert config.current_version == Version("25.0")
    assert config.previous_version == Version("24.2")
    assert config.next_version is None
    assert config.release_date == datetime.date(2025, 7, 1)
    assert config.freeze_date == datetime.date(2025, 6, 1)
    assert config.owner == "myorg"
    assert config.repo == "myrepo"


def test_load_release_config_explicit_path_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_release_config(
            tmp_path, Version("99.0"), release_config_path=tmp_path / "nonexistent.yml"
        )


def test_load_release_config_no_yaml_no_flags(tmp_path):
    with pytest.raises(ValueError, match="missing required flag"):
        load_release_config(tmp_path, Version("99.0"))


def test_load_release_config_cli_only(tmp_path):
    config = load_release_config(
        tmp_path,
        Version("99.0"),
        previous_version=Version("98.0"),
        release_date=datetime.date(2099, 1, 15),
        freeze_date=datetime.date(2099, 1, 1),
    )
    assert config.current_version == Version("99.0")
    assert config.previous_version == Version("98.0")
    assert config.next_version is None
    assert config.release_date == datetime.date(2099, 1, 15)
    assert config.freeze_date == datetime.date(2099, 1, 1)
    assert config.owner == "galaxyproject"
    assert config.repo == "galaxy"



def test_load_release_config_cli_overrides_yaml(tmp_path, config_dir):
    _write_config(
        config_dir,
        "release_98.2.yml",
        "current-version: '98.2'\nprevious-version: '98.1'\nfreeze-date: '2099-01-01'\nrelease-date: '2099-01-15'\n",
    )
    config = load_release_config(
        tmp_path, Version("98.2"),
        next_version=Version("99.5"),
        release_date=datetime.date(2099, 6, 1),
    )
    assert config.next_version == Version("99.5")
    assert config.release_date == datetime.date(2099, 6, 1)
    # Non-overridden values from YAML
    assert config.previous_version == Version("98.1")


def test_load_release_config_missing_field(tmp_path, config_dir):
    _write_config(
        config_dir,
        "release_99.0.yml",
        "current-version: '99.0'\n",
    )
    with pytest.raises(ValueError, match="Missing required field"):
        load_release_config(tmp_path, Version("99.0"))


def test_load_release_config_next_version_from_yaml(tmp_path, config_dir):
    """next-version is still parsed from YAML if present (backward compat)."""
    _write_config(
        config_dir,
        "release_98.2.yml",
        "current-version: '98.2'\nprevious-version: '98.1'\nnext-version: '99.0'\nfreeze-date: '2099-01-01'\nrelease-date: '2099-01-15'\n",
    )
    config = load_release_config(tmp_path, Version("98.2"))
    assert config.next_version == Version("99.0")


def test_load_release_config_null_required_field(tmp_path, config_dir):
    _write_config(
        config_dir,
        "release_99.0.yml",
        "current-version: '99.0'\nprevious-version:\nfreeze-date: '2099-01-01'\nrelease-date: '2099-01-15'\n",
    )
    with pytest.raises(ValueError, match="has no value"):
        load_release_config(tmp_path, Version("99.0"))


def test_load_release_config_invalid_version(tmp_path, config_dir):
    _write_config(
        config_dir,
        "release_99.0.yml",
        "current-version: '!!!'\nprevious-version: '98.0'\nfreeze-date: '2099-01-01'\nrelease-date: '2099-01-15'\n",
    )
    with pytest.raises(ValueError, match="Invalid 'current-version'"):
        load_release_config(tmp_path, Version("99.0"))


def test_load_release_config_invalid_date(tmp_path, config_dir):
    _write_config(
        config_dir,
        "release_99.0.yml",
        "current-version: '99.0'\nprevious-version: '98.0'\nfreeze-date: '2099-01-01'\nrelease-date: 'not-a-date'\n",
    )
    with pytest.raises(ValueError, match="Invalid 'release-date'"):
        load_release_config(tmp_path, Version("99.0"))


def test_load_release_config_null_freeze_date(tmp_path, config_dir):
    _write_config(
        config_dir,
        "release_99.0.yml",
        "current-version: '99.0'\nprevious-version: '98.0'\nrelease-date: '2099-01-15'\nfreeze-date:\n",
    )
    with pytest.raises(ValueError, match="has no value"):
        load_release_config(tmp_path, Version("99.0"))


def test_load_release_config_not_a_mapping(tmp_path, config_dir):
    _write_config(
        config_dir,
        "release_99.0.yml",
        "- item1\n- item2\n",
    )
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        load_release_config(tmp_path, Version("99.0"))


def test_load_release_config_version_mismatch(tmp_path, config_dir):
    _write_config(
        config_dir,
        "release_99.0.yml",
        "current-version: '98.0'\nprevious-version: '97.0'\nfreeze-date: '2099-01-01'\nrelease-date: '2099-01-15'\n",
    )
    with pytest.raises(ValueError, match="does not match release-version argument"):
        load_release_config(tmp_path, Version("99.0"), release_config_path=config_dir / "release_99.0.yml")


def test_load_release_config_from_fixture():
    config_path = Path("tests/test_data/release_98.2.yml")
    config = load_release_config(Path("."), Version("98.2"), release_config_path=config_path)
    assert config.current_version == Version("98.2")
    assert config.previous_version == Version("98.1")
    assert config.next_version is None
    assert config.freeze_date == datetime.date(2099, 1, 1)
    assert config.release_date == datetime.date(2099, 1, 15)
