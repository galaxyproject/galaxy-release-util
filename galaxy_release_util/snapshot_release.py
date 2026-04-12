import datetime
import re
import subprocess
from pathlib import Path
from typing import (
    List,
    Optional,
)

import click
from packaging.version import Version

from .cli.options import (
    galaxy_root_option,
    group_options,
    release_config_option,
)
from .metadata import get_repo_name
from .point_release import (
    ChangelogItem,
    Package,
    build_package,
    bump_package_version,
    commits_to_prs,
    create_tag,
    get_current_branch,
    get_root_version,
    get_sorted_package_paths,
    is_git_clean,
    load_packages,
    read_package,
    set_root_version,
    stage_changes_and_commit,
    update_client_version,
    update_packages,
    version_filepath,
)
from .release_config import load_repo_owner
from .util import verify_galaxy_root

CANONICAL_OWNER = "galaxyproject"
CANONICAL_REPO = "galaxy"
CANONICAL_HTTPS = f"https://github.com/{CANONICAL_OWNER}/{CANONICAL_REPO}.git"

SNAPSHOT_TAG_PREFIX = "snapshot-v"
SNAPSHOT_TAG_MESSAGE = "Validation snapshot for release process exercise on fork, derived from galaxyproject/galaxy dev"
INITIAL_SNAPSHOT_TEXT = "Initial snapshot — no prior baseline"


def find_canonical_upstream(galaxy_root: Path) -> str:
    """Find the canonical galaxyproject/galaxy remote URL from local git remotes."""
    result = subprocess.run(
        ["git", "remote", "-v"], cwd=galaxy_root, capture_output=True, text=True,
    )
    result.check_returncode()
    canonical_pattern = re.compile(r"galaxyproject[/:]galaxy(?:\.git)?(?:\s|$)", re.IGNORECASE)
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and "(fetch)" in line:
            url = parts[1]
            if canonical_pattern.search(url):
                return url
    return CANONICAL_HTTPS


def find_last_snapshot_tag(galaxy_root: Path, major_minor: str) -> Optional[str]:
    """Find the most recent snapshot tag reachable from HEAD for the given major.minor."""
    result = subprocess.run(
        ["git", "tag", "--list", f"{SNAPSHOT_TAG_PREFIX}{major_minor}.*",
         "--merged", "HEAD", "--sort=-v:refname"],
        cwd=galaxy_root, capture_output=True, text=True,
    )
    result.check_returncode()
    tags = result.stdout.strip().splitlines()
    return tags[0] if tags else None


def _tag_exists_locally(galaxy_root: Path, tag: str) -> bool:
    result = subprocess.run(
        ["git", "tag", "--list", tag], cwd=galaxy_root, capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def _tag_exists_on_remote(galaxy_root: Path, remote_url: str, tag: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", remote_url, f"refs/tags/{tag}"],
        cwd=galaxy_root, capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def _verify_upstream_alignment(galaxy_root: Path, canonical_url: str) -> None:
    """Verify HEAD matches canonical upstream dev."""
    result = subprocess.run(
        ["git", "ls-remote", canonical_url, "refs/heads/dev"],
        cwd=galaxy_root, capture_output=True, text=True,
    )
    result.check_returncode()
    if not result.stdout.strip():
        raise click.ClickException(
            f"Could not read refs/heads/dev from canonical upstream {canonical_url}"
        )
    remote_hash = result.stdout.split("\t")[0]
    local_result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=galaxy_root, capture_output=True, text=True,
    )
    local_result.check_returncode()
    local_hash = local_result.stdout.strip()
    if remote_hash != local_hash:
        raise click.ClickException(
            f"HEAD ({local_hash[:12]}) does not match canonical upstream dev ({remote_hash[:12]}). "
            f"Sync your fork to {canonical_url} before creating a snapshot."
        )


@click.group(help="Subcommands for creating release snapshots on private forks")
def cli():
    pass


@cli.command("create-release-snapshot", help="Create a date-based release snapshot for a private Galaxy fork")
@group_options(
    galaxy_root_option,
    release_config_option,
)
@click.option(
    "--push-remote",
    type=str,
    default=None,
    help="Git remote URL to push the snapshot tag to. Default: derived from config owner/repo.",
)
def create_release_snapshot(
    galaxy_root: Path,
    release_config: Optional[Path],
    push_remote: Optional[str],
):
    # 1. Validate galaxy root
    verify_galaxy_root(galaxy_root)

    # 2. Refuse if dirty tree (cheap local check, before any network call)
    if not is_git_clean(galaxy_root):
        raise click.ClickException("Working tree is not clean. Commit or stash changes before creating a snapshot.")

    # 3. Refuse if not on dev branch
    branch = get_current_branch(galaxy_root)
    if branch != "dev":
        raise click.ClickException(f"Snapshot releases must be created on the 'dev' branch, currently on '{branch}'.")

    # 4. Compute root version once, reuse throughout
    root_version = get_root_version(galaxy_root)
    major_minor = f"{root_version.major}.{root_version.minor}"

    # 5. Load owner/repo and refuse if targeting canonical repo
    owner, repo = load_repo_owner(galaxy_root, root_version, release_config)
    if owner == CANONICAL_OWNER and repo == CANONICAL_REPO:
        raise click.ClickException(
            "Snapshot releases must not target the official galaxyproject/galaxy repository. "
            "Set owner/repo in your release config YAML to point to your fork."
        )

    # 6. Compute snapshot version and refuse if tag already exists locally
    date_str = datetime.date.today().strftime("%Y%m%d")
    snapshot_version = Version(f"{major_minor}.dev{date_str}")
    snapshot_tag = f"{SNAPSHOT_TAG_PREFIX}{snapshot_version}"

    if _tag_exists_locally(galaxy_root, snapshot_tag):
        raise click.ClickException(f"Tag '{snapshot_tag}' already exists locally. A snapshot was already created today.")

    # 7. Compute push remote and refuse if tag already exists on remote
    if push_remote is None:
        push_remote = f"git@github.com:{get_repo_name(owner, repo)}.git"

    click.echo(f"Snapshot: {snapshot_version} -> {push_remote}")

    if _tag_exists_on_remote(galaxy_root, push_remote, snapshot_tag):
        raise click.ClickException(f"Tag '{snapshot_tag}' already exists on remote {push_remote}.")

    # 8. Verify HEAD matches canonical upstream dev
    canonical_url = find_canonical_upstream(galaxy_root)
    _verify_upstream_alignment(galaxy_root, canonical_url)

    # 9. Find previous snapshot tag for changelog baseline
    last_tag = find_last_snapshot_tag(galaxy_root, major_minor)

    # 10. Load packages and resolve PRs
    if last_tag:
        click.echo(f"Previous snapshot: {last_tag}")
        packages = load_packages(galaxy_root, [], last_tag)
        commits_to_prs(packages, CANONICAL_OWNER, CANONICAL_REPO)
    else:
        click.echo("First snapshot - no prior baseline")
        packages = _load_packages_without_baseline(galaxy_root)

    # 11. Bump versions and generate changelogs
    version_py = version_filepath(galaxy_root)
    set_root_version(version_py, snapshot_version)
    modified_paths: List[Path] = [version_py]

    if last_tag:
        update_packages(packages, snapshot_version, modified_paths)
    else:
        _apply_initial_snapshot_changelog(packages, snapshot_version, modified_paths)

    update_client_version(galaxy_root, snapshot_version, modified_paths)

    # 12. Build packages (validation only — artifacts are discarded)
    #     This runs before commit/tag so packaging failures abort the snapshot
    #     without leaving any trace in git history.
    _build_packages_or_abort(packages)

    # 13. Commit
    commit_message = f"Snapshot release {snapshot_version}\n\n{SNAPSHOT_TAG_MESSAGE}"
    stage_changes_and_commit(galaxy_root, snapshot_version, modified_paths, commit_message, no_confirm=True)

    # 14. Annotated tag
    create_tag(galaxy_root, snapshot_tag, no_confirm=True, message=SNAPSHOT_TAG_MESSAGE)

    # 15. Push tag only
    click.echo(f"Pushing {snapshot_tag} to {push_remote}")
    try:
        subprocess.run(
            ["git", "push", push_remote, snapshot_tag], cwd=galaxy_root,
        ).check_returncode()
    except subprocess.CalledProcessError:
        click.echo(f"\nPush failed. To complete manually:\n  git push {push_remote} {snapshot_tag}")
        raise

    click.echo(f"Snapshot release {snapshot_version} created and pushed as {snapshot_tag}")


def _build_packages_or_abort(packages: List[Package]) -> None:
    """Build each package to validate the packaging path.

    Builds are validation-only — artifacts are not uploaded or used.
    If any package fails to build, abort before any commit or tag is created
    so the snapshot does not produce a misleading release artifact.
    """
    click.echo(f"Building {len(packages)} package(s) to validate packaging path")
    for package in packages:
        try:
            build_package(package)
        except subprocess.CalledProcessError as e:
            raise click.ClickException(
                f"Package '{package.name}' failed to build: {e}. "
                "Aborting snapshot — no commit or tag has been created."
            ) from e


def _load_packages_without_baseline(galaxy_root: Path) -> List[Package]:
    """Load packages for first snapshot: no commit range, no PR resolution.

    Reads package metadata (setup.cfg, HISTORY.rst) without computing
    a commit diff. Packages will have empty commit and PR sets.
    """
    packages = []
    for package_path in get_sorted_package_paths(galaxy_root):
        package = read_package(package_path)
        packages.append(package)
    return packages


def _apply_initial_snapshot_changelog(packages: List[Package], snapshot_version: Version, modified_paths: List[Path]) -> None:
    """Apply explicit initial snapshot changelog to all packages.

    Used for the first snapshot when no prior baseline exists.
    Bypasses the normal PR-based changelog generation.
    """
    today = datetime.date.today().isoformat()
    for package in packages:
        bump_package_version(package, snapshot_version)
        changelog_item = ChangelogItem(
            version=snapshot_version,
            changes=[f"* {INITIAL_SNAPSHOT_TEXT}"],
            date=today,
        )
        package.package_history.insert(0, changelog_item)
        package.write_history()
        modified_paths.extend(package.modified_paths)
