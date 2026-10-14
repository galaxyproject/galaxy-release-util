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
    ClickVersion,
    galaxy_root_option,
    group_options,
    next_version_option,
    owner_option,
    repo_option,
)
from .point_release import (
    bump_package_version,
    check_uv_available,
    get_root_version,
    get_sorted_package_paths,
    Package,
    read_package_version,
    set_root_version,
    update_client_version,
    update_uv_lock,
)
from .release_config import (
    milestone_due_dates,
    ReleaseConfig,
    resolve_from_milestones,
)
from .util import (
    verify_galaxy_root,
    version_filepath,
)

GITHUB_OWNER_REGEX = re.compile(r"github\.com[:/]([^/]+)/")
MAKEFILE_RELEASE_REGEX = re.compile(r"^RELEASE_CURR:=.*$", re.MULTILINE)


def _git(galaxy_root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=galaxy_root, capture_output=True, text=True)
    if result.returncode != 0:
        raise click.ClickException(f"'git {' '.join(args)}' failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _ref_exists(galaxy_root: Path, ref: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=galaxy_root).returncode == 0


def _is_clean(galaxy_root: Path) -> bool:
    return subprocess.run(["git", "diff-index", "--quiet", "HEAD"], cwd=galaxy_root).returncode == 0


def _starting_point(galaxy_root: Path) -> str:
    """The checked out branch, or the commit for a detached HEAD."""
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=galaxy_root, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else _git(galaxy_root, "rev-parse", "HEAD")


def _is_major_minor(version: Version) -> bool:
    return str(version) == f"{version.major}.{version.minor}"


def _ensure_new_branches(galaxy_root: Path, branches: List[str]) -> None:
    existing = [branch for branch in branches if _ref_exists(galaxy_root, f"refs/heads/{branch}")]
    if existing:
        raise click.ClickException(
            f"Branch(es) {', '.join(existing)} already exist, delete them with 'git branch -D {' '.join(existing)}'"
        )


def _check_out_new_branch(galaxy_root: Path, branch: str, start_point: str, created_branches: List[str]) -> None:
    _git(galaxy_root, "checkout", "--quiet", "--no-track", "-b", branch, start_point)
    created_branches.append(branch)


def _commit(galaxy_root: Path, modified_paths: List[Path], message: str) -> None:
    _git(galaxy_root, "add", "--", *[str(path) for path in modified_paths])
    _git(galaxy_root, "commit", "--quiet", "-m", message)
    click.echo(f"Committed '{message}'")


def set_package_versions(galaxy_root: Path, new_version: Version, modified_paths: List[Path]) -> None:
    for package_path in get_sorted_package_paths(galaxy_root):
        package = Package(path=package_path, current_version=read_package_version(package_path))
        bump_package_version(package, new_version)
        modified_paths.extend(package.modified_paths)


def set_makefile_release(galaxy_root: Path, release: str, modified_paths: List[Path]) -> None:
    makefile = galaxy_root / "Makefile"
    contents, count = MAKEFILE_RELEASE_REGEX.subn(f"RELEASE_CURR:={release}", makefile.read_text())
    if not count:
        raise click.ClickException(f"{makefile} does not set RELEASE_CURR")
    makefile.write_text(contents)
    modified_paths.append(makefile)


def update_versions(galaxy_root: Path, version: Version, package_version: Version) -> List[Path]:
    """Set the Galaxy version and the package and client versions, and lock the workspace again."""
    version_py = set_root_version(version_filepath(galaxy_root), version)
    modified_paths = [version_py]
    set_package_versions(galaxy_root, package_version, modified_paths)
    update_client_version(galaxy_root, package_version, modified_paths)
    update_uv_lock(galaxy_root, modified_paths)
    return modified_paths


def resolve_next_version(release_version: Version, next_version: Optional[Version], owner: str, repo: str) -> Version:
    config = ReleaseConfig(current_version=release_version, next_version=next_version, owner=owner, repo=repo)
    if config.next_version is None:
        due_dates = milestone_due_dates(owner, repo)
        resolve_from_milestones(
            config, {version: date for version, date in due_dates.items() if _is_major_minor(version)}
        )
    if config.next_version is None:
        raise click.UsageError(
            f"Could not determine --next-version: found no milestone after {release_version} in {owner}/{repo}. "
            "Set GITHUB_AUTH to read the milestones, or pass --next-version."
        )
    if not _is_major_minor(config.next_version):
        raise click.UsageError(f"Expected a next version like 27.0, got {config.next_version}")
    if config.next_version <= release_version:
        raise click.UsageError(f"--next-version ({config.next_version}) must be greater than {release_version}")
    return config.next_version


def fork_owner(galaxy_root: Path, fork_remote: str) -> Optional[str]:
    match = GITHUB_OWNER_REGEX.search(_git(galaxy_root, "remote", "get-url", fork_remote))
    return match.group(1) if match else None


def push(galaxy_root: Path, commands: List[List[str]], no_confirm: bool, dry_run: bool) -> None:
    for i, command in enumerate(commands):
        command_line = " ".join(command)
        if dry_run:
            click.echo(f"Dry run, not running: {command_line}")
            continue
        confirmed = no_confirm or click.confirm(f"Run '{command_line}'?")
        if confirmed and subprocess.run(command, cwd=galaxy_root).returncode == 0:
            continue
        click.echo("\nNot everything was pushed. To finish, run:")
        for remaining in commands[i:]:
            click.echo(f"  {' '.join(remaining)}")
        if not confirmed:
            raise click.Abort()
        raise click.ClickException(f"'{command_line}' failed")


def print_pull_request(owner: str, repo: str, base: str, fork: Optional[str], branch: str, fork_remote: str) -> None:
    if fork:
        click.echo(
            f"Open a pull request against {base}: https://github.com/{owner}/{repo}/compare/{base}...{fork}:{branch}"
        )
    else:
        click.echo(f"Open a pull request from branch '{branch}' of remote '{fork_remote}' against {base}")


def create_initial_release_candidate(
    galaxy_root: Path,
    release_version: Version,
    next_version: Version,
    upstream_remote: str,
    created_branches: List[str],
) -> None:
    """Create the rc1 commit, and the commit moving dev to the next release with the rc1 commit merged."""
    dev = f"{upstream_remote}/dev"
    _git(galaxy_root, "checkout", "--quiet", "--detach", dev)
    dev_version = get_root_version(galaxy_root)
    if Version(f"{dev_version.major}.{dev_version.minor}") != release_version:
        raise click.ClickException(
            f"{dev} is at version {dev_version}, expected {release_version} to be in development"
        )
    rc_branch = f"version-{release_version}.rc1"
    next_branch = f"version-{next_version}.dev"
    _ensure_new_branches(galaxy_root, [rc_branch, next_branch])

    _check_out_new_branch(galaxy_root, rc_branch, dev, created_branches)
    modified_paths = update_versions(galaxy_root, Version(f"{release_version}rc1"), Version(f"{release_version}.0rc1"))
    _commit(galaxy_root, modified_paths, f"Update version to {release_version}.rc1")

    next_dev_version = Version(f"{next_version}.dev0")
    _check_out_new_branch(galaxy_root, next_branch, dev, created_branches)
    modified_paths = update_versions(galaxy_root, next_dev_version, next_dev_version)
    set_makefile_release(galaxy_root, str(next_version), modified_paths)
    _commit(galaxy_root, modified_paths, f"Update version to {next_dev_version}")
    _git(
        galaxy_root,
        "merge",
        "--quiet",
        "-X",
        "ours",
        "-m",
        f"Merge branch 'release_{release_version}' into 'dev'",
        rc_branch,
    )
    changed = _git(galaxy_root, "diff", "--name-only", "HEAD^1", "HEAD")
    if changed:
        raise click.ClickException(f"Merging {rc_branch} into {next_branch} changed {', '.join(changed.split())}")


def create_next_release_candidate(
    galaxy_root: Path, release_version: Version, upstream_remote: str, created_branches: List[str]
) -> None:
    """Create the commit for the next rcN on top of the release branch."""
    release_branch = f"{upstream_remote}/release_{release_version}"
    _git(galaxy_root, "checkout", "--quiet", "--detach", release_branch)
    current_version = get_root_version(galaxy_root)
    pre = current_version.pre
    if Version(current_version.base_version) != release_version or pre is None or pre[0] != "rc" or current_version.dev:
        raise click.ClickException(
            f"{release_branch} is at version {current_version}, which is not a release candidate of {release_version}"
        )
    rc = pre[1] + 1
    rc_branch = f"version-{release_version}.rc{rc}"
    _ensure_new_branches(galaxy_root, [rc_branch])
    _check_out_new_branch(galaxy_root, rc_branch, release_branch, created_branches)
    modified_paths = update_versions(
        galaxy_root, Version(f"{release_version}rc{rc}"), Version(f"{release_version}.0rc{rc}")
    )
    _commit(galaxy_root, modified_paths, f"Update version to {release_version}.rc{rc}")


@click.group(help="Subcommands of this script can create Galaxy release branches")
def cli():
    pass


@cli.command(
    "create-release-branch",
    help="""Create the release branch for RELEASE_VERSION (e.g. 26.2), or its next release candidate.

    If the release branch (e.g. release_26.2) does not exist upstream yet, it is created from the upstream
    dev branch. Two branches are pushed to your fork for pull requests: one setting the release branch to
    26.2.rc1, and one moving dev to the next release (e.g. 27.0.dev0).

    If the release branch exists, a branch bumping it to the next release candidate is pushed to your fork.
    """,
)
@click.argument("release-version", type=ClickVersion())
@group_options(galaxy_root_option, next_version_option, owner_option, repo_option)
@click.option(
    "--upstream-remote",
    default="upstream",
    show_default=True,
    help="Git remote of the Galaxy repository in which the release branch is created.",
)
@click.option(
    "--fork-remote",
    default="origin",
    show_default=True,
    help="Git remote of your fork, to which the branches for the version pull requests are pushed.",
)
@click.option("--no-confirm", is_flag=True, default=False, help="Push without asking for confirmation.")
@click.option("--dry-run", is_flag=True, default=False, help="Create the branches and commits locally, push nothing.")
def create_release_branch(
    release_version: Version,
    galaxy_root: Path,
    next_version: Optional[Version],
    owner: str,
    repo: str,
    upstream_remote: str,
    fork_remote: str,
    no_confirm: bool,
    dry_run: bool,
):
    verify_galaxy_root(galaxy_root)
    if not _is_major_minor(release_version):
        raise click.UsageError(f"Expected a release version like 26.2, got {release_version}")
    check_uv_available(galaxy_root)
    if not _is_clean(galaxy_root):
        raise click.ClickException(f"The Galaxy clone at {galaxy_root} has uncommitted changes")
    starting_point = _starting_point(galaxy_root)
    fork = fork_owner(galaxy_root, fork_remote)
    click.echo(f"Fetching {upstream_remote}")
    _git(galaxy_root, "fetch", "--quiet", "--prune", upstream_remote)
    release_branch = f"release_{release_version}"
    initial = not _ref_exists(galaxy_root, f"refs/remotes/{upstream_remote}/{release_branch}")
    if initial:
        next_version = resolve_next_version(release_version, next_version, owner, repo)
        click.echo(f"Creating {release_branch} at {release_version}.rc1, dev moves to {next_version}.dev0")

    created_branches: List[str] = []
    try:
        try:
            if initial:
                assert next_version
                create_initial_release_candidate(
                    galaxy_root, release_version, next_version, upstream_remote, created_branches
                )
            else:
                create_next_release_candidate(galaxy_root, release_version, upstream_remote, created_branches)
        except BaseException:
            # HEAD is on a branch created here or detached, so resetting it touches nothing of the user's.
            subprocess.run(["git", "reset", "--quiet", "--hard"], cwd=galaxy_root)
            subprocess.run(["git", "checkout", "--quiet", starting_point], cwd=galaxy_root)
            if created_branches:
                subprocess.run(["git", "branch", "--quiet", "-D", *created_branches], cwd=galaxy_root)
            raise

        commands = [["git", "push", fork_remote, f"{branch}:{branch}"] for branch in created_branches]
        if initial:
            # Refuse to move release_X if it was created upstream in the meantime.
            commands.append(
                [
                    "git",
                    "push",
                    f"--force-with-lease=refs/heads/{release_branch}:",
                    upstream_remote,
                    f"refs/remotes/{upstream_remote}/dev:refs/heads/{release_branch}",
                ]
            )
        push(galaxy_root, commands, no_confirm, dry_run)
        for branch, base in zip(created_branches, [release_branch, "dev"]):
            print_pull_request(owner, repo, base, fork, branch, fork_remote)
        if dry_run:
            click.echo(f"Delete the local branches before running again: git branch -D {' '.join(created_branches)}")
    finally:
        if _is_clean(galaxy_root):
            subprocess.run(["git", "checkout", "--quiet", starting_point], cwd=galaxy_root)
