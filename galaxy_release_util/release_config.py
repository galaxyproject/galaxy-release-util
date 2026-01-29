import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from packaging.version import Version


@dataclass
class ReleaseConfig:
    current_version: Version
    previous_version: Version
    next_version: Version
    release_date: datetime.date
    freeze_date: datetime.date
    owner: str = "galaxyproject"
    repo: str = "galaxy"


def load_release_config(
    galaxy_root: Path,
    release_version: Version,
    release_config_path: Optional[Path] = None,
    previous_version: Optional[Version] = None,
    next_version: Optional[Version] = None,
    release_date: Optional[datetime.date] = None,
    freeze_date: Optional[datetime.date] = None,
) -> ReleaseConfig:
    """Load release config from YAML, CLI flags, or both.

    Resolution order:
    1. If --release-config is given, load that file (must exist).
    2. Otherwise, try the default path {galaxy_root}/doc/source/releases/release_{version}.yml.
    3. CLI flags (--previous-version, --next-version, --release-date, --freeze-date) override YAML values.
    4. If no YAML is found, all required values must come from CLI flags.
    """
    yaml_config = _try_load_yaml_config(galaxy_root, release_version, release_config_path)

    if yaml_config is not None:
        # Apply CLI overrides
        if previous_version is not None:
            yaml_config.previous_version = previous_version
        if next_version is not None:
            yaml_config.next_version = next_version
        if release_date is not None:
            yaml_config.release_date = release_date
        if freeze_date is not None:
            yaml_config.freeze_date = freeze_date
        return yaml_config

    # No YAML found — build entirely from CLI flags
    missing = []
    if previous_version is None:
        missing.append("--previous-version")
    if next_version is None:
        missing.append("--next-version")
    if release_date is None:
        missing.append("--release-date")
    if freeze_date is None:
        missing.append("--freeze-date")
    if missing:
        raise ValueError(
            f"No release config YAML found and missing required flag(s): {', '.join(missing)}. "
            f"Provide a config YAML via --release-config or supply the flags directly."
        )
    return ReleaseConfig(
        current_version=release_version,
        previous_version=previous_version,
        next_version=next_version,
        release_date=release_date,
        freeze_date=freeze_date,
    )


def _try_load_yaml_config(
    galaxy_root: Path,
    release_version: Version,
    release_config_path: Optional[Path],
) -> Optional[ReleaseConfig]:
    """Try to load a YAML config file, returning None if no file is found at the default path."""
    if release_config_path is not None:
        if not release_config_path.exists():
            raise FileNotFoundError(f"Release config not found: {release_config_path}")
        return _load_yaml_file(release_config_path, release_version)

    default_path = galaxy_root / "doc" / "source" / "releases" / f"release_{release_version}.yml"
    if not default_path.exists():
        return None
    return _load_yaml_file(default_path, release_version)


def _load_yaml_file(path: Path, release_version: Version) -> ReleaseConfig:
    """Load and validate a YAML release config file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Release config must be a YAML mapping, got {type(data).__name__} in {path}")
    required_fields = ["current-version", "previous-version", "next-version", "freeze-date", "release-date"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise ValueError(
            f"Missing required field(s) {', '.join(repr(f) for f in missing)} in {path}"
        )
    for field in required_fields:
        if data[field] is None:
            raise ValueError(f"Field '{field}' is present but has no value in {path}")
    try:
        current_version = Version(str(data["current-version"]))
    except Exception as e:
        raise ValueError(f"Invalid 'current-version' value {data['current-version']!r} in {path}: {e}")
    try:
        previous_version = Version(str(data["previous-version"]))
    except Exception as e:
        raise ValueError(
            f"Invalid 'previous-version' value {data['previous-version']!r} in {path}: {e}"
        )
    try:
        next_version = Version(str(data["next-version"]))
    except Exception as e:
        raise ValueError(f"Invalid 'next-version' value {data['next-version']!r} in {path}: {e}")
    try:
        release_date = _parse_date(data["release-date"])
    except Exception as e:
        raise ValueError(f"Invalid 'release-date' value {data['release-date']!r} in {path}: {e}")
    try:
        freeze_date = _parse_date(data["freeze-date"])
    except Exception as e:
        raise ValueError(f"Invalid 'freeze-date' value {data['freeze-date']!r} in {path}: {e}")
    if current_version != release_version:
        raise ValueError(
            f"'current-version' in config ({current_version}) does not match "
            f"release-version argument ({release_version})"
        )
    owner = data.get("owner", "galaxyproject")
    repo = data.get("repo", "galaxy")
    return ReleaseConfig(
        current_version=current_version,
        previous_version=previous_version,
        next_version=next_version,
        release_date=release_date,
        freeze_date=freeze_date,
        owner=owner,
        repo=repo,
    )


def _parse_date(value) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    return datetime.datetime.strptime(str(value), "%Y-%m-%d").date()
