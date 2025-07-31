import datetime
import json
import re
import subprocess
from dataclasses import (
    dataclass,
    field,
)
from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

import click
import docutils
from docutils import (
    frontend,
    utils,
)
from docutils.parsers.rst import Parser
from github import PullRequest
from packaging.version import Version

from .cli.options import (
    ClickVersion,
    galaxy_root_option,
    group_options,
)
from .github_client import github_client
from .metadata import (
    _text_target,
    strip_release,
)
from .util import (
    verify_galaxy_root,
    version_filepath,
)

g = github_client()
PROJECT_OWNER = "galaxyproject"
PROJECT_NAME = "galaxy"
REPO = f"{PROJECT_OWNER}/{PROJECT_NAME}"
DEFAULT_UPSTREAM_URL = f"https://github.com/{REPO}.git"

HISTORY_TEMPLATE = """History
-------

.. to_doc

"""
RELEASE_BRANCH_REGEX = re.compile(r"^release_(\d{2}\.\d{1,2})$")
FIRST_RELEASE_CHANGELOG_TEXT = "First release"


@dataclass
class ReleaseItem:
    version: Version
    date: Optional[str] = None


@dataclass
class ChangelogItem:
    version: Version
    changes: List[str]
    date: Optional[str] = None

    @property
    def datetime_date(self) -> datetime.datetime:
        if self.date:
            return datetime.datetime.fromisoformat(self.date)
        raise Exception(f"Changelog item for version {self.version} is missing date.")

    @property
    def is_empty_devrelease(self):
        return (self.version.is_devrelease or self.version.is_prerelease) and not self.changes

    def __str__(self) -> str:
        change_lines = "\n".join(self.changes)
        if self.date:
            version_line = f"{self.version} ({self.date})"
        else:
            version_line = str(self.version)
        return f"""{'-' * len(version_line)}
{version_line}
{'-' * len(version_line)}

{change_lines}
"""


@dataclass
class Package:
    path: Path
    current_version: str
    commits: Set[str] = field(default_factory=set)
    prs: Set[PullRequest.PullRequest] = field(default_factory=set)
    modified_paths: List[Path] = field(default_factory=list)
    package_history: List[ChangelogItem] = field(default_factory=list)
    release_items: List[ReleaseItem] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def setup_cfg(self) -> Path:
        return self.path / "setup.cfg"

    @property
    def history_rst(self) -> Path:
        return self.path / "HISTORY.rst"

    @property
    def changelog(self) -> str:
        changelog_string = "\n".join(str(h) for h in self.package_history)
        return f"{HISTORY_TEMPLATE}{changelog_string}"

    @property
    def pinned_requirements_txt(self) -> Path:
        return self.path / ".." / ".." / "lib" / "galaxy" / "dependencies" / "pinned-requirements.txt"

    def write_history(self):
        self.history_rst.write_text(self.changelog)
        self.modified_paths.append(self.history_rst)

    def add_release(self, item: ReleaseItem) -> None:
        self.release_items.append(item)

    @property
    def code_paths(self) -> List[Path]:
        if self.name == "meta":
            # every commit is relevant:
            return [self.path / ".." / ".."]
        package_code_paths = []
        for code_dir in ["galaxy", "tests", "galaxy_test"]:
            package_code_path = self.path / code_dir
            if package_code_path.exists():
                # get all symlinks pointing to a directory
                for item in package_code_path.iterdir():
                    # Check if the item is a symlink and if its target points to a directory
                    if item.is_symlink() and item.resolve().is_dir():
                        package_code_paths.append(item.resolve())
        return package_code_paths

    def get_commits_since_last_version(self, last_version_tag: str) -> Set[str]:
        click.echo(f"finding commits to package {self.name} made since {last_version_tag}")
        commits = set()
        for package_source_path in self.code_paths:
            result = subprocess.run(
                [
                    "git",
                    "log",
                    "--oneline",
                    "--no-merges",
                    "--pretty=format:%h",
                    f"{last_version_tag}..HEAD",
                    package_source_path,
                ],
                cwd=self.path,
                capture_output=True,
                text=True,
            )
            try:
                result.check_returncode()
            except subprocess.CalledProcessError as err:
                if "unknown revision" in result.stderr:
                    raise Exception(
                        f"last version tag `{last_version_tag}` was not recognized by git as a valid revision identifier"
                    ) from err
                raise err

            for line in result.stdout.splitlines():
                if line:
                    commits.add(line)
        return commits

    @property
    def is_new(self) -> bool:
        """Package has not been released:
        - has only one release item,
        - which is a devrelease,
        - and has no date.
        """
        return (
            len(self.release_items) == 1
            and self.release_items[0].version.is_devrelease
            and not self.release_items[0].date
        )

    def __repr__(self) -> str:
        pretty_string = f"[Package: {self.name}, Current Version: {self.current_version}"
        return pretty_string


def get_sorted_package_paths(galaxy_root: Path) -> List[Path]:
    root_package_path = galaxy_root.joinpath("packages")
    sorted_packages = root_package_path.joinpath("packages_by_dep_dag.txt").read_text().splitlines()
    # Ignore empty lines and lines beginning with "#"
    return [root_package_path.joinpath(p) for p in sorted_packages if p and not p.startswith("#")]


def read_package(package_path: Path) -> Package:
    setup_cfg = package_path / "setup.cfg"
    package = None
    with setup_cfg.open() as content:
        for line in content:
            if line.startswith("version = "):
                version = line.strip().split("version = ")[-1]
                package = Package(path=package_path, current_version=version)
                break
    if not package:
        raise ValueError(f"{setup_cfg} does not contain version line")
    package.package_history = parse_changelog(package)
    return package


def parse_changelog(package: Package) -> List[ChangelogItem]:
    def add_changelog_item(changes, child):
        rawsource = child.rawsource.strip()
        if rawsource:
            changes.append(f"* {rawsource}")

    settings = frontend.get_default_settings(Parser)  # type: ignore[attr-defined] ## upstream type stubs not updated?
    document = utils.new_document(str(package.history_rst), settings)
    Parser().parse(package.history_rst.read_text(), document)
    changelog_items: List[ChangelogItem] = []
    root_section = document[0]
    assert isinstance(root_section, docutils.nodes.section)
    for node in root_section.children:
        # ignore title and comment
        assert isinstance(node, (docutils.nodes.title, docutils.nodes.comment, docutils.nodes.section)), node
        if isinstance(node, docutils.nodes.section):
            release_version = node[0].astext()
            current_date = None
            if " (" in release_version:
                version_str, current_date = release_version.split(" (")
                current_date = current_date.split(")")[0]
            else:
                # this should be a dev-release without changelog items
                # we will just omit this later
                version_str = release_version
            current_version = Version(version_str)
            package.add_release(ReleaseItem(version=current_version, date=current_date))
            changes: List = []
            for changelog_item in node[1:]:
                # could be bullet list or a nested section with bugfix, docs, etc
                if isinstance(changelog_item, docutils.nodes.bullet_list):
                    for child in changelog_item.children:
                        add_changelog_item(changes, child)
                elif isinstance(changelog_item, docutils.nodes.paragraph):
                    changes = changelog_item.rawsource.splitlines()
                elif isinstance(changelog_item, docutils.nodes.section):
                    kind = changelog_item[0].astext()
                    section_delimiter = "=" * len(kind)
                    changes.append(f"\n{section_delimiter}\n{kind}\n{section_delimiter}\n")
                    for section_changelog_item in changelog_item[1:]:
                        if isinstance(section_changelog_item, docutils.nodes.system_message):
                            # Likely a warning that subsection (e.g. Bug fixes) is not unique
                            continue
                        assert isinstance(section_changelog_item, docutils.nodes.bullet_list), type(
                            section_changelog_item
                        )
                        for child in section_changelog_item:
                            add_changelog_item(changes, child)
            changelog_items.append(ChangelogItem(version=current_version, date=current_date, changes=changes))

    # Filter out dev release versions without changelog,
    # we're going to add these back after committing the release version
    clean_changelog_items: List[ChangelogItem] = []
    for item in changelog_items:
        if not (item.is_empty_devrelease or package.is_new):
            if item.date is None:
                raise Exception(
                    f"Error in '{package.history_rst}'. Changelog entry for non-dev version '{item.version}' has no date but contains changes. You have to fix this manually."
                )
            clean_changelog_items.append(item)
    return sorted(
        clean_changelog_items,
        key=lambda item: item.datetime_date,
        reverse=True,
    )


def bump_package_version(package: Package, new_version: Version) -> None:
    content = package.setup_cfg.read_text().splitlines()
    new_content = [f"version = {new_version}" if line.startswith("version = ") else line for line in content]
    package.setup_cfg.write_text("\n".join(new_content) + "\n")
    package.modified_paths.append(package.setup_cfg)


def commits_to_prs(packages: List[Package]) -> None:
    commits = set.union(*(p.commits for p in packages))
    pr_cache = {}
    commit_to_pr = {}
    repo = g.get_repo(REPO)
    total_commits = len(commits)
    for i, commit in enumerate(commits):
        click.echo(f"Processing commit {i + 1} of {total_commits}")
        # Get the list of pull requests associated with the commit
        commit_obj = repo.get_commit(commit)
        prs = commit_obj.get_pulls()
        if not prs:
            raise Exception(f"commit {commit} has no associated PRs")
        for pr in prs:
            if pr.number not in pr_cache:
                pr_cache[pr.number] = pr
            commit_to_pr[commit] = pr_cache[pr.number]
    for package in packages:
        # Exclude commits without PRs
        package.prs = set(commit_to_pr[commit] for commit in package.commits if commit in commit_to_pr)


def get_package_history(package: Package, new_version: Version) -> ChangelogItem:
    sorted_and_formatted_changes = []
    changes: Dict[str, List[str]] = {
        "Bug fixes": [],
        "Enhancements": [],
        "Other changes": [],
    }
    if package.is_new:
        # For new packages, replace any current text; do not list PRs.
        sorted_and_formatted_changes.append(FIRST_RELEASE_CHANGELOG_TEXT)
    elif not package.prs:
        # Skip publishing packages if no change ?
        sorted_and_formatted_changes.append("No recorded changes since last release")
    else:
        for pr in sorted(package.prs, key=lambda pr: pr.number):
            category = "Other changes"
            text_target = _text_target(pr, skip_merge=False)
            if text_target:
                if "bug" in text_target:
                    category = "Bug fixes"
                if "enhancement" in text_target or "feature" in text_target:
                    category = "Enhancements"
            changes[category].append(
                f"* {strip_release(pr.title)} by `@{pr.user.login} <https://github.com/{pr.user.login}>`_ in `#{pr.number} <{pr.html_url}>`_"
            )

    for kind, entries in changes.items():
        if entries:
            section_delimiter = "=" * len(kind)
            sorted_and_formatted_changes.append(f"\n{section_delimiter}\n{kind}\n{section_delimiter}\n")
        sorted_and_formatted_changes.extend(entries)

    now = datetime.datetime.now().strftime("%Y-%m-%d")
    return ChangelogItem(version=new_version, changes=sorted_and_formatted_changes, date=now)


def build_package(package: Package) -> None:
    click.echo(f"Running make clean for package {package.name}")
    subprocess.run(["make", "clean"], cwd=package.path).check_returncode()
    click.echo(f"running make dist for package {package.name}")
    subprocess.run(["make", "dist"], cwd=package.path).check_returncode()
    click.echo(f"running make lint-dist for package {package.name}")
    subprocess.run(["make", "lint-dist"], cwd=package.path).check_returncode()


def upload_package(package: Package) -> None:
    click.echo(f"uploading package {package.name}")
    subprocess.run(
        ["twine", "upload", "--skip-existing"]
        + [str(artifact_path) for artifact_path in package.path.joinpath("dist").glob("*")],
        cwd=package.path,
    ).check_returncode()


def get_root_version(galaxy_root: Path) -> Version:
    version_py = version_filepath(galaxy_root)
    version_py_contents = version_py.read_text().splitlines()
    assert len(version_py_contents) == 3
    major_version = version_py_contents[0].split('"')[1]
    minor_version = version_py_contents[1].split('"')[1]
    return Version(f"{major_version}.{minor_version}")


def set_root_version(version_py: Path, new_version: Version) -> Path:
    major_galaxy_release_string, minor_galaxy_release_string = get_major_minor_version_strings(new_version)
    VERSION_PY_TEMPLATE = f"""VERSION_MAJOR = "{major_galaxy_release_string}"
VERSION_MINOR = "{minor_galaxy_release_string}"
VERSION = VERSION_MAJOR + (f".{{VERSION_MINOR}}" if VERSION_MINOR else "")
"""
    version_py.write_text(VERSION_PY_TEMPLATE)
    return version_py


def get_major_minor_version_strings(version: Version) -> Tuple[str, str]:
    major_galaxy_release_string = f"{version.major}.{version.minor}"
    # use "0" if minor version and/or point version was not specified
    if str(version) == str(version.major) or str(version) == major_galaxy_release_string:
        minor_galaxy_release_string = "0"
    else:
        minor_galaxy_release_string = str(version).replace(f"{major_galaxy_release_string}.", "")
    return major_galaxy_release_string, minor_galaxy_release_string


def is_git_clean(galaxy_root: Path) -> bool:
    click.echo(f"Making sure galaxy clone at '{galaxy_root}' is clean:")
    command = ["git", "diff-index", "--quiet", "HEAD"]
    result = subprocess.run(command, capture_output=True, text=True, cwd=galaxy_root)
    if result.returncode == 0:
        return True
    else:
        msg = f"Command '{' '.join(command)}' failed with exit code {result.returncode}"
        if result.returncode != 1 and result.stderr:
            msg = f"{msg}, stderr: {result.stderr}"
        click.echo(msg)
        return False


def get_current_branch(galaxy_root) -> str:
    current_branch_cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    result = subprocess.run(current_branch_cmd, cwd=galaxy_root, capture_output=True, text=True)
    result.check_returncode()
    return result.stdout.strip()


def get_branches(galaxy_root: Path, new_version: Version, current_branch: str) -> List[str]:
    """
    Tries to get release and dev branches that we need to merge forward to.
    """
    major_minor_new_version = Version(f"{new_version.major}.{new_version.minor}")
    cmd = ["git", "branch", "--format=%(refname:short)"]
    result = subprocess.run(cmd, cwd=galaxy_root, capture_output=True, text=True)
    result.check_returncode()
    release_branches = []
    branches = result.stdout.splitlines()
    for branch in branches:
        match = RELEASE_BRANCH_REGEX.match(branch)
        if match:
            version = match.group(1)
            branch_version = Version(version)
            if branch_version > major_minor_new_version:
                release_branches.append(branch)
    if current_branch != "dev":
        release_branches.append("dev")
    return release_branches


def merge_and_resolve_branches(
    galaxy_root: Path,
    base_branch: str,
    new_branch: str,
    packages: List[Package],
) -> None:
    checkout_cmd = ["git", "checkout", new_branch]
    subprocess.run(checkout_cmd, cwd=galaxy_root).check_returncode()

    package_paths = {p.path: p for p in packages}
    packages_to_rewrite: List[Package] = [p for p in packages if p.name == "meta"]
    for package_path in get_sorted_package_paths(galaxy_root):
        if package_path not in package_paths:
            continue
        package = read_package(package_path)
        packages_to_rewrite.append(package)

    merge_cmd = ["git", "merge", base_branch]
    result = subprocess.run(merge_cmd, cwd=galaxy_root, capture_output=True, text=True)
    merge_conflict = result.returncode != 0  # merge conflict expected
    # restore base galaxy versions
    galaxy_versions = [
        version_filepath(galaxy_root),
        galaxy_root.joinpath("package.json"),
        galaxy_root.joinpath("client", "package.json"),
    ]
    subprocess.run(
        ["git", "checkout", new_branch, *galaxy_versions],
        cwd=galaxy_root,
    )
    # we rewrite the packages changelog
    for new_package in packages_to_rewrite:
        previous_package = package_paths[new_package.path]
        combined_history = previous_package.package_history + new_package.package_history
        new_history: List[ChangelogItem] = []
        last_changelog_item: Optional[ChangelogItem] = None
        for changelog_item in sorted(combined_history, key=lambda item: item.version, reverse=True):
            if last_changelog_item and changelog_item.version == last_changelog_item.version:
                assert (
                    last_changelog_item.changes == changelog_item.changes
                ), f"Changelog differs for version {changelog_item.version} of package {new_package.name}, you have to fix this manually.\nOffending lines are {last_changelog_item.changes} and {changelog_item.changes}"
                continue
            if not changelog_item.date and not changelog_item.changes:
                # dev0 version, we'll inject that later
                continue
            new_history.append(changelog_item)
            last_changelog_item = changelog_item
        # we change the original package in place so this continues to work if we merge forward across multiple branches
        previous_package.package_history = sorted(
            new_history,
            key=lambda item: item.datetime_date,
            reverse=True,
        )
        dev_version = get_root_version(galaxy_root)
        previous_package.package_history.insert(0, ChangelogItem(version=dev_version, changes=[], date=None))
        previous_package.write_history()
        subprocess.run(["git", "add", str(previous_package.history_rst)], cwd=galaxy_root)
        # restore setup.cfg
        subprocess.run(
            ["git", "checkout", new_branch, str(previous_package.setup_cfg)], cwd=galaxy_root
        ).check_returncode()
    # Commit changes
    if merge_conflict:
        subprocess.run(["git", "commit", "--no-edit"], cwd=galaxy_root).check_returncode()
    else:
        subprocess.run(["git", "commit", "--amend", "--no-edit"], cwd=galaxy_root).check_returncode()


def get_next_devN_version(galaxy_root) -> Version:
    root_version = get_root_version(galaxy_root)
    if root_version.dev is not None:
        minor_version = root_version.minor
        micro_version = root_version.micro
        dev_version = root_version.dev + 1
    else:
        minor_version = root_version.minor
        micro_version = root_version.micro + 1
        dev_version = 0
    return Version(f"{root_version.major}.{minor_version}.{micro_version}.dev{dev_version}")


def is_merge_required(base_branch: str, new_branch: str, galaxy_root: Path) -> bool:
    subprocess.run(["git", "checkout", new_branch], cwd=galaxy_root).check_returncode()
    process = subprocess.run(
        ["git", "merge", "--no-commit", "--no-ff", base_branch],
        cwd=galaxy_root,
        capture_output=True,
    )
    if not process.stdout == b"Already up to date.\n":
        subprocess.run(["git", "merge", "--abort"], cwd=galaxy_root)
    if process.returncode == 0:
        return False
    return True


def ensure_branches_up_to_date(branches: List[str], base_branch: str, upstream: str, galaxy_root: Path) -> None:
    click.echo("Making sure that all branches are up to date")
    try:
        for branch in branches:
            subprocess.run(["git", "checkout", branch], cwd=galaxy_root).check_returncode()
            # Check that the head commit matches the commit for the same branch at the specified remote repo url
            result = subprocess.run(
                ["git", "ls-remote", upstream, f"refs/heads/{branch}"],
                cwd=galaxy_root,
                capture_output=True,
                text=True,
            )
            result.check_returncode()
            remote_commit_hash = result.stdout.split("\t")[0]
            result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=galaxy_root, capture_output=True, text=True)
            result.check_returncode()
            local_commit_hash = result.stdout.strip()
            if remote_commit_hash != local_commit_hash:
                raise Exception(
                    f"Local tip of branch {branch} is {local_commit_hash}, remote tip of branch is {remote_commit_hash}. Make sure that your local branches are up to date and track f{upstream}."
                )
    finally:
        if branch != base_branch:
            subprocess.run(["git", "checkout", base_branch], cwd=galaxy_root).check_returncode()


def ensure_clean_merges(newer_branches: List[str], base_branch: str, galaxy_root: Path, no_confirm: bool) -> None:
    click.echo("Making sure that merging forward will result in clean merges")
    current_branch = base_branch
    try:
        for new_branch in newer_branches:
            merge_required = is_merge_required(
                base_branch=current_branch, new_branch=new_branch, galaxy_root=galaxy_root
            )
            if merge_required:
                msg = f"Merge conflicts occurred while attempting to merge branch {current_branch} into {new_branch}. You should resolve conflicts and try again."
                if no_confirm:
                    raise Exception(msg)
                click.echo(msg)
                if click.confirm("Continue anyway ?", abort=True):
                    current_branch = new_branch
                    break
    finally:
        subprocess.run(["git", "checkout", base_branch], cwd=galaxy_root).check_returncode()


@click.group(help="Subcommands of this script can create new releases and build and upload package artifacts")
def cli():
    pass


packages_option = click.option(
    "--packages",
    "package_subset",
    multiple=True,
    type=str,
    default=None,
    help="Restrict build to specified packages",
)
no_confirm_option = click.option("--no-confirm", type=bool, is_flag=True, default=False)


@group_options(galaxy_root_option, packages_option)
@cli.command("build", help="Build packages without uploading")
def build(
    galaxy_root: Path,
    package_subset: List[str],
):
    _build(galaxy_root, package_subset)


def _build(
    galaxy_root: Path,
    package_subset: List[str],
):
    packages: List[Package] = []
    for package_path in get_sorted_package_paths(galaxy_root):
        if package_subset and package_path.name not in package_subset:
            continue
        package = read_package(package_path)
        packages.append(package)
    for package in packages:
        click.echo(f"Building package {package}")
        if package.name == "meta":
            build_meta_dependencies(package, packages, get_root_version(galaxy_root))
        build_package(package)
    return packages


@group_options(galaxy_root_option, packages_option, no_confirm_option)
@cli.command("build-and-upload", help="Build and upload packages")
def build_and_upload(
    galaxy_root: Path,
    package_subset: List[str],
    no_confirm: bool,
):
    packages = _build(galaxy_root, package_subset)
    if no_confirm or click.confirm("Upload packages ?"):
        for package in packages:
            click.echo(f"Uploading package {package}")
            upload_package(package)


@cli.command("create-release", help="Create a new point release")
@group_options(galaxy_root_option)
@click.option(
    "--new-version",
    type=ClickVersion(),
    help="Specify new release version. Must be valid PEP 440 version",
    required=True,
)
@click.option(
    "--last-commit",
    type=str,
    help="Specify commit or tag that was used for the last package release. This is used to find the changelog for packages.",
    required=True,
)
@click.option("--build-packages/--no-build-packages", type=bool, is_flag=True, default=True)
@click.option("--upload-packages", type=bool, is_flag=True, default=False)
@click.option("--upstream", type=str, default=DEFAULT_UPSTREAM_URL)
@group_options(packages_option, no_confirm_option)
def create_point_release(
    galaxy_root: Path,
    new_version: Version,
    build_packages: bool,
    last_commit: str,
    package_subset: List[str],
    upload_packages: bool,
    no_confirm: bool,
    upstream: str,
):
    verify_galaxy_root(galaxy_root)
    check_galaxy_repo_is_clean(galaxy_root)
    base_branch = get_current_branch(galaxy_root)
    user_confirmation(galaxy_root, new_version, base_branch, no_confirm)
    newer_branches = get_branches(galaxy_root, new_version, base_branch)
    all_branches = newer_branches + [base_branch]
    ensure_branches_up_to_date(all_branches, base_branch, upstream, galaxy_root)
    ensure_clean_merges(newer_branches, base_branch, galaxy_root, no_confirm)
    version_py = version_filepath(galaxy_root)

    set_root_version(version_py, new_version)
    modified_paths = [version_py]
    packages = load_packages(galaxy_root, package_subset, last_commit)
    commits_to_prs(packages)
    update_packages(packages, new_version, modified_paths)
    update_client_version(galaxy_root, new_version, modified_paths)
    run_build_packages(build_packages, packages)
    show_modified_paths_and_diff(galaxy_root, modified_paths, no_confirm)
    run_upload_packages(build_packages, upload_packages, no_confirm, packages)
    commit_message = f"Create version {new_version}"
    stage_changes_and_commit(galaxy_root, new_version, modified_paths, commit_message, no_confirm)
    release_tag = f"v{new_version}"
    create_tag(galaxy_root, release_tag, no_confirm)

    dev_version = get_next_devN_version(galaxy_root)
    set_root_version(version_py, dev_version)
    modified_paths = [version_py]
    update_packages(packages, dev_version, modified_paths, is_dev_version=True)
    update_client_version(galaxy_root, dev_version, modified_paths)
    commit_message = f"Start work on {dev_version}"
    stage_changes_and_commit(galaxy_root, dev_version, modified_paths, commit_message, no_confirm)

    merge_changes_into_newer_branches(galaxy_root, packages, newer_branches, base_branch, no_confirm)
    push_references(galaxy_root, release_tag, all_branches, upstream, no_confirm)


def update_client_version(galaxy_root: Path, new_version: Version, modified_paths: List[Path]) -> None:
    package_json = galaxy_root.joinpath("client", "package.json")
    modified_paths.append(package_json)
    package_json_dict = json.loads(package_json.read_text())
    package_json_dict["version"] = str(new_version)
    package_json.write_text(f"{json.dumps(package_json_dict, indent=2)}\n")
    if not new_version.is_devrelease:
        # Only update root package.json if not a dev release, since those are not uploaded to npm
        root_package_json = galaxy_root.joinpath("package.json")
        modified_paths.append(root_package_json)
        root_package_json_dict = json.loads(root_package_json.read_text())
        root_package_json_dict["version"] = str(new_version)
        root_package_json.write_text(f"{json.dumps(root_package_json_dict, indent=2)}\n")


def check_galaxy_repo_is_clean(galaxy_root: Path) -> None:
    if not is_git_clean(galaxy_root):
        click.confirm(
            "Your galaxy clone has untracked or staged changes, are you sure you want to continue?",
            abort=True,
        )


def user_confirmation(galaxy_root: Path, new_version: Version, base_branch: str, no_confirm: bool) -> None:
    root_version = get_root_version(galaxy_root)
    click.echo(
        f"- Current Galaxy version: {root_version}\n- New Galaxy version: {new_version}\n- Base branch: {base_branch}"
    )
    if not no_confirm:
        click.confirm("Does this look correct?", abort=True)


def load_packages(galaxy_root: Path, package_subset: List[str], last_commit: str) -> List[Package]:
    """Read packages and find prs that affect a package."""
    packages: List[Package] = []
    for package_path in get_sorted_package_paths(galaxy_root):
        if package_subset and package_path.name not in package_subset:
            continue
        package = read_package(package_path)
        packages.append(package)
        package.commits = package.get_commits_since_last_version(last_commit)
    return packages


def update_packages(
    packages: List[Package], new_version: Version, modified_paths: List[Path], is_dev_version: bool = False
) -> None:
    """Update package versions and changelog files."""
    for package in packages:
        bump_package_version(package, new_version)

        if not is_dev_version:
            changelog_item = get_package_history(package, new_version)
        else:
            changelog_item = ChangelogItem(version=new_version, changes=[], date=None)
        package.package_history.insert(0, changelog_item)

        package.write_history()
        modified_paths.extend(package.modified_paths)
        if package.name == "meta" and not is_dev_version:
            build_meta_dependencies(package, packages, new_version)


def build_meta_dependencies(meta_package: Package, packages: List[Package], new_version: Version) -> None:
    """Update meta package dependencies."""
    # Skip tool shed, should not be required at runtime, and skip meta package itself
    meta_deps = [f"galaxy-{p.name}=={new_version}" for p in packages if p.name not in ("meta", "tool_shed")]
    for line in meta_package.pinned_requirements_txt.read_text().splitlines():
        if not line.startswith(("--", "#")):
            meta_deps.append(line)
    meta_deps.sort()
    requirements_txt = meta_package.path.joinpath("requirements.txt")
    requirements_txt.write_text("\n".join(meta_deps))
    meta_package.modified_paths.append(requirements_txt)


def show_modified_paths_and_diff(galaxy_root: Path, modified_paths: List[Path], no_confirm: bool) -> None:
    """Show modified paths, optionally run git diff."""
    modified_paths_str = [str(p) for p in modified_paths]
    pretty_paths = "\n".join(modified_paths_str)
    click.echo(f"The following paths have been modified: \n{pretty_paths}")
    if not no_confirm and click.confirm("show diff ?"):
        cmd = ["git", "diff"]
        cmd.extend(modified_paths_str)
        subprocess.run(cmd, cwd=galaxy_root)


def run_build_packages(build_packages: bool, packages: List[Package]) -> None:
    if build_packages:
        for package in packages:
            build_package(package)


def run_upload_packages(build_packages: bool, upload_packages: bool, no_confirm: bool, packages: List[Package]):
    if build_packages and upload_packages and (no_confirm or click.confirm("Upload packages to ?")):
        for package in packages:
            upload_package(package)


def stage_changes_and_commit(
    galaxy_root: Path,
    new_version: Version,
    modified_paths: List[Path],
    commit_message: str,
    no_confirm: bool,
) -> None:
    """Stage changes and commit."""
    if not no_confirm:
        click.confirm("Stage and commit changes ?", abort=True)

    cmd = ["git", "add"]
    changed_paths = [str(p) for p in modified_paths]
    cmd.extend(changed_paths)
    subprocess.run(cmd, cwd=galaxy_root)

    subprocess.run(["git", "commit", "-m", commit_message], cwd=galaxy_root)


def create_tag(galaxy_root: Path, release_tag: str, no_confirm: bool) -> None:
    if not no_confirm:
        click.confirm(f"Create git tag '{release_tag}'?", abort=True)
    subprocess.run(["git", "tag", release_tag], cwd=galaxy_root)


def merge_changes_into_newer_branches(
    galaxy_root: Path,
    packages: List[Package],
    newer_branches: List[str],
    base_branch: str,
    no_confirm: bool,
) -> None:
    """
    Merge changes into newer branches.
    Special care needs to be taken for changelog files.
    """
    if not no_confirm and newer_branches:
        click.confirm(
            f"Merge branch '{base_branch}' into {', '.join(newer_branches)} ?",
            abort=True,
        )
    current_branch = base_branch
    for new_branch in newer_branches:
        click.echo(f"Merging {base_branch} into {new_branch}")
        merge_and_resolve_branches(galaxy_root, current_branch, new_branch, packages)
        current_branch = new_branch


def push_references(galaxy_root: Path, release_tag: str, branches: List[str], upstream: str, no_confirm: bool) -> None:
    references = [release_tag] + branches
    if no_confirm or click.confirm(f"Push {','.join(references)} to upstream '{upstream}' ?", abort=True):
        for reference in references:
            subprocess.run(["git", "push", upstream, reference], cwd=galaxy_root).check_returncode()


if __name__ == "__main__":
    cli()
