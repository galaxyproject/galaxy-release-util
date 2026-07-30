import datetime
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Dict,
    Optional,
    Tuple,
)

import click
import yaml
from packaging.version import (
    InvalidVersion,
    Version,
)

from .github_client import github_client
from .metadata import (
    PROJECT_NAME,
    PROJECT_OWNER,
    get_repo_name,
)

RELEASE_NOTES_FILENAME = re.compile(r"^(\d+\.\d+)\.rst$")


@dataclass
class ReleaseConfig:
    """Release metadata, resolved from CLI flags, an optional YAML config and GitHub milestones.

    Every value except ``current_version`` is optional: commands declare what they
    actually need via :meth:`require`, so a command never fails over a value it
    does not use.
    """

    current_version: Version
    previous_version: Optional[Version] = None
    release_date: Optional[datetime.date] = None
    freeze_date: Optional[datetime.date] = None
    next_version: Optional[Version] = None
    owner: str = PROJECT_OWNER
    repo: str = PROJECT_NAME

    def require(self, *fields: str) -> None:
        """Raise if any of ``fields`` could not be resolved."""
        missing = [f"--{field.replace('_', '-')}" for field in fields if getattr(self, field) is None]
        if missing:
            raise ValueError(
                f"Could not determine {', '.join(missing)} for release {self.current_version}. "
                f"Expected a milestone titled '{self.current_version}' with a due date in "
                f"{get_repo_name(self.owner, self.repo)}. Pass the value(s) explicitly, or add them to a "
                f"release config YAML."
            )


def load_release_config(
    galaxy_root: Path,
    release_version: Version,
    release_config_path: Optional[Path] = None,
    previous_version: Optional[Version] = None,
    next_version: Optional[Version] = None,
    release_date: Optional[datetime.date] = None,
    freeze_date: Optional[datetime.date] = None,
    use_github: bool = True,
) -> ReleaseConfig:
    """Resolve release metadata for ``release_version``.

    Resolution order, highest precedence first:

    1. CLI flags (``--previous-version``, ``--next-version``, ``--release-date``, ``--freeze-date``).
    2. A release config YAML: the file given by ``--release-config``, or
       ``{galaxy_root}/doc/source/releases/{version}_release.yml`` if it exists.
       The YAML is optional and so are all of its fields.
    3. GitHub milestones, the source of truth for release dates and for the
       surrounding release versions.
    4. Locally derived fallbacks, used when GitHub is unreachable.

    Values that cannot be resolved are left as ``None``; use :meth:`ReleaseConfig.require`
    to assert on the ones a given command needs.
    """
    config = _try_load_yaml_config(galaxy_root, release_version, release_config_path)
    if config is None:
        config = ReleaseConfig(current_version=release_version)

    # CLI flags override anything from the YAML.
    if previous_version is not None:
        config.previous_version = previous_version
    if next_version is not None:
        config.next_version = next_version
    if release_date is not None:
        config.release_date = release_date
    if freeze_date is not None:
        config.freeze_date = freeze_date

    if use_github:
        _fill_from_milestones(config)
    _fill_from_local_fallbacks(config, galaxy_root)
    return config


def milestone_due_dates(owner: str, repo: str) -> Dict[Version, Optional[datetime.date]]:
    """Return a {version: due date} mapping of all milestones that are named after a version.

    Milestones without a due date map to ``None``. Returns an empty mapping (with a
    warning) if GitHub cannot be reached, so callers can fall back to local information.
    """
    try:
        github_repo = github_client().get_repo(get_repo_name(owner, repo))
        milestones = list(github_repo.get_milestones(state="all"))
    except Exception as e:  # noqa: BLE001 - missing auth, rate limits and network errors are all recoverable here
        click.echo(f"Warning: could not read milestones from {get_repo_name(owner, repo)}: {e}", err=True)
        return {}
    due_dates: Dict[Version, Optional[datetime.date]] = {}
    for milestone in milestones:
        try:
            version = Version(milestone.title)
        except InvalidVersion:
            continue  # Milestones are not required to be named after a release.
        due_dates[version] = milestone.due_on.date() if milestone.due_on else None
    return due_dates


def _fill_from_milestones(config: ReleaseConfig) -> None:
    """Fill in release date and surrounding versions from the GitHub milestones."""
    if config.release_date is not None and config.previous_version is not None and config.next_version is not None:
        return  # Nothing left to look up, don't spend an API call.
    due_dates = milestone_due_dates(config.owner, config.repo)
    if not due_dates:
        return
    if config.release_date is None:
        config.release_date = due_dates.get(config.current_version)
    if config.previous_version is None:
        earlier = [version for version in due_dates if version < config.current_version]
        if earlier:
            config.previous_version = max(earlier)
    if config.next_version is None:
        later = [version for version in due_dates if version > config.current_version]
        if later:
            config.next_version = min(later)


def _fill_from_local_fallbacks(config: ReleaseConfig, galaxy_root: Path) -> None:
    """Derive whatever is still missing without talking to GitHub."""
    if config.next_version is None:
        config.next_version = Version(f"{config.current_version.major}.{config.current_version.minor + 1}")
    if config.previous_version is None:
        config.previous_version = _previous_release_from_docs(galaxy_root, config.current_version)


def _previous_release_from_docs(galaxy_root: Path, version: Version) -> Optional[Version]:
    """Return the newest release documented in ``doc/source/releases`` that precedes ``version``."""
    releases_path = galaxy_root / "doc" / "source" / "releases"
    if not os.path.isdir(releases_path):
        return None
    documented = []
    for filename in os.listdir(releases_path):
        match = RELEASE_NOTES_FILENAME.match(filename)
        if match:
            documented.append(Version(match.group(1)))
    earlier = [documented_version for documented_version in documented if documented_version < version]
    return max(earlier) if earlier else None


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

    default_path = _default_config_path(galaxy_root, release_version)
    if not default_path.exists():
        return None
    return _load_yaml_file(default_path, release_version)


def _default_config_path(galaxy_root: Path, release_version: Version) -> Path:
    return galaxy_root / "doc" / "source" / "releases" / f"{release_version}_release.yml"


def _load_yaml_file(path: Path, release_version: Version) -> ReleaseConfig:
    """Load and validate a YAML release config file.

    All fields are optional, but a field that is present must hold a valid value.
    """
    data = _read_yaml_mapping(path)
    current_version = _optional_version(data, "current-version", path)
    if current_version is not None and current_version != release_version:
        raise ValueError(
            f"'current-version' in config ({current_version}) does not match "
            f"release-version argument ({release_version})"
        )
    return ReleaseConfig(
        current_version=release_version,
        previous_version=_optional_version(data, "previous-version", path),
        next_version=_optional_version(data, "next-version", path),
        release_date=_optional_date(data, "release-date", path),
        freeze_date=_optional_date(data, "freeze-date", path),
        owner=data.get("owner") or PROJECT_OWNER,
        repo=data.get("repo") or PROJECT_NAME,
    )


def load_repo_owner(
    galaxy_root: Path,
    release_version: Version,
    release_config_path: Optional[Path] = None,
) -> Tuple[str, str]:
    """Load owner and repo from release config YAML.

    For point releases (e.g. 26.0.1), derives the major.minor version (26.0)
    to locate the config file. Returns (owner, repo) tuple, falling back to
    defaults only if no config file exists at the default path.
    """
    major_minor = Version(f"{release_version.major}.{release_version.minor}")
    if release_config_path is not None:
        if not release_config_path.exists():
            raise FileNotFoundError(f"Release config not found: {release_config_path}")
        path = release_config_path
    else:
        path = _default_config_path(galaxy_root, major_minor)
        if not path.exists():
            return (PROJECT_OWNER, PROJECT_NAME)
    data = _read_yaml_mapping(path)
    return (data.get("owner") or PROJECT_OWNER, data.get("repo") or PROJECT_NAME)


def _read_yaml_mapping(path: Path) -> dict:
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Release config must be a YAML mapping, got {type(data).__name__} in {path}")
    return data


def _optional_version(data: dict, field: str, path: Path) -> Optional[Version]:
    if field not in data:
        return None
    value = data[field]
    if value is None:
        raise ValueError(f"Field '{field}' is present but has no value in {path}")
    try:
        return Version(str(value))
    except InvalidVersion as e:
        raise ValueError(f"Invalid '{field}' value {value!r} in {path}: {e}")


def _optional_date(data: dict, field: str, path: Path) -> Optional[datetime.date]:
    if field not in data:
        return None
    value = data[field]
    if value is None:
        raise ValueError(f"Field '{field}' is present but has no value in {path}")
    try:
        return _parse_date(value)
    except ValueError as e:
        raise ValueError(f"Invalid '{field}' value {value!r} in {path}: {e}")


def _parse_date(value) -> datetime.date:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.datetime.strptime(str(value), "%Y-%m-%d").date()
