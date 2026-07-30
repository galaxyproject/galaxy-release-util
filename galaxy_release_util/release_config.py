import datetime
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    Mapping,
    Optional,
)

import click
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
    """Release metadata, resolved from CLI flags and GitHub milestones.

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
                f"{get_repo_name(self.owner, self.repo)}. Pass the value(s) explicitly."
            )


def load_release_config(
    galaxy_root: Path,
    release_version: Version,
    previous_version: Optional[Version] = None,
    next_version: Optional[Version] = None,
    release_date: Optional[datetime.date] = None,
    freeze_date: Optional[datetime.date] = None,
    owner: str = PROJECT_OWNER,
    repo: str = PROJECT_NAME,
) -> ReleaseConfig:
    """Resolve release metadata for ``release_version``.

    Values given as CLI flags win. Anything left over is read from the GitHub
    milestones of ``owner``/``repo``, which are the source of truth for release
    dates and for the surrounding release versions. If GitHub cannot be reached,
    what can be derived locally is derived locally.

    Values that stay unresolved are left as ``None``; use :meth:`ReleaseConfig.require`
    to assert on the ones a given command needs.
    """
    config = ReleaseConfig(
        current_version=release_version,
        previous_version=previous_version,
        next_version=next_version,
        release_date=release_date,
        freeze_date=freeze_date,
        owner=owner,
        repo=repo,
    )
    _fill_from_milestones(config)
    _fill_from_local_fallbacks(config, galaxy_root)
    return config


def due_dates_by_version(milestones: Iterable[Any]) -> Dict[Version, Optional[datetime.date]]:
    """Map milestones named after a release version to their due dates.

    Titles that are not versions are skipped, since milestones are not required to
    name a release. A milestone with no due date maps to ``None``.
    """
    due_dates: Dict[Version, Optional[datetime.date]] = {}
    for milestone in milestones:
        try:
            version = Version(milestone.title)
        except InvalidVersion:
            continue
        due_dates[version] = milestone.due_on.date() if milestone.due_on else None
    return due_dates


def milestone_due_dates(owner: str, repo: str) -> Dict[Version, Optional[datetime.date]]:
    """Read the milestones of ``owner``/``repo`` as a {version: due date} mapping.

    Returns an empty mapping (with a warning) if GitHub cannot be reached, so callers
    can fall back to local information.
    """
    try:
        github_repo = github_client().get_repo(get_repo_name(owner, repo))
        milestones = list(github_repo.get_milestones(state="all"))
    except Exception as e:  # noqa: BLE001 - missing auth, rate limits and network errors are all recoverable here
        click.echo(f"Warning: could not read milestones from {get_repo_name(owner, repo)}: {e}", err=True)
        return {}
    return due_dates_by_version(milestones)


def resolve_from_milestones(config: ReleaseConfig, due_dates: Mapping[Version, Optional[datetime.date]]) -> None:
    """Fill gaps in ``config`` from a {version: due date} mapping, leaving set values alone.

    The release date is the due date of the milestone naming the release; the
    surrounding versions are its nearest neighbours.
    """
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


def _fill_from_milestones(config: ReleaseConfig) -> None:
    if config.release_date is not None and config.previous_version is not None and config.next_version is not None:
        return  # Nothing left to look up, don't spend an API call.
    resolve_from_milestones(config, milestone_due_dates(config.owner, config.repo))


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
