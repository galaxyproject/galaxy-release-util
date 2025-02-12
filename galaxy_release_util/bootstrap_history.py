import calendar
import datetime
import logging
import os
import re
import string
import sys
import textwrap
from pathlib import Path
from typing import (
    List,
    Optional,
    Set,
)

import click
from github import GithubException
from github.Issue import Issue
from github.PullRequest import PullRequest
from packaging.version import Version

from .cli.options import (
    ClickDate,
    ClickVersion,
    galaxy_root_option,
    group_options,
)
from .github_client import github_client
from .metadata import (
    _pr_to_labels,
    _pr_to_str,
    _text_target,
    GROUPED_TAGS,
    PROJECT_NAME,
    PROJECT_OWNER,
    PROJECT_URL,
    strip_release,
)
from .util import verify_galaxy_root

OLDER_RELEASES_FILENAME = "older_releases.rst"


TEMPLATE = """
.. to_doc

${release}
===============================

.. announce_start

Enhancements
-------------------------------

.. major_feature


.. feature

.. enhancement

.. small_enhancement



Fixes
-------------------------------

.. major_bug


.. bug


.. include:: ${release}_prs.rst

"""

ANNOUNCE_TEMPLATE = string.Template(
    """
===========================================================
${release} Galaxy Release (${month_name} ${year})
===========================================================

.. include:: _header.rst

Highlights
===========================================================

Feature1
--------

Feature description.

Feature2
--------

Feature description.

Feature3
--------

Feature description.

Please see the `${release} user release notes <${release}_announce_user.html>`__ for a summary of new user features.

Get Galaxy
===========================================================

The code lives at `GitHub <https://github.com/galaxyproject/galaxy>`__ and you should have `Git <https://git-scm.com/>`__ to obtain it.

To get a new Galaxy repository run:
  .. code-block:: shell

      $$ git clone -b release_${release} https://github.com/galaxyproject/galaxy.git

To update an existing Galaxy repository run:
  .. code-block:: shell

      $$ git fetch origin && git checkout release_${release} && git pull --ff-only origin release_${release}

See the `community hub <https://galaxyproject.org/develop/source-code/>`__ for additional details on source code locations.


Admin Notes
===========================================================
Add content or drop section.

Configuration Changes
===========================================================
Add content or drop section.

Deprecation Notices
===========================================================
Add content or drop section.

Developer Notes
===========================================================
Add content or drop section.

Release Notes
===========================================================

.. include:: ${release}.rst
   :start-after: announce_start

Release Team
===========================================================

Release manager:  `[NAME] <https://github.com/[GITHUB-USERNAME]>`__

Release testing:

* `[NAME] <https://github.com/[GITHUB-USERNAME]>`__
* ...

Communications:

* `[NAME] <https://github.com/[GITHUB-USERNAME]>`__

A special thank you goes to everyone who helped test the new release after its deployment on usegalaxy.org.

----

.. include:: _thanks.rst
"""  # noqa: E501
)

ANNOUNCE_USER_TEMPLATE = string.Template(
    """
===========================================================
${release} Galaxy Release (${month_name} ${year})
===========================================================

.. include:: _header.rst

Please see the full :doc:`${release} release notes <${release}_announce>` for more details.

Highlights
===========================================================

Feature1
--------

Feature description.

Feature2
--------

Feature description.

Feature3
--------

Feature description.


Visualizations
===========================================================

.. visualizations

Datatypes
===========================================================

.. datatypes

Builtin Tool Updates
===========================================================

.. tools

Please see the full :doc:`${release} release notes <${release}_announce>` for more details.

.. include:: ${release}_prs.rst

----

.. include:: _thanks.rst
"""  # noqa: E501
)

NEXT_TEMPLATE = string.Template(
    """
:orphan:

===========================================================
${release} Galaxy Release
===========================================================
"""
)

PRS_TEMPLATE = """
.. github_links
"""

RELEASE_ISSUE_TEMPLATE = string.Template(
    """

- [ ] **Branch Release (on or around ${freeze_date})**

    - [ ] Verify that your installed version of `galaxy-release-util` is up-to-date.
    - [ ] Ensure all [blocking milestone pull requests](https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+milestone%3A${version}) have been merged, closed, or postponed until the next release.

          galaxy-release-util check-blocking-prs ${version} --release-date ${release_date}

    - [ ] Add latest database revision identifier (for ``release_${version}`` and ``${version}``) to ``REVISION_TAGS`` in ``galaxy/model/migrations/dbscript.py``.

    - [ ] Merge the latest release into dev and push upstream.

          make release-merge-stable-to-next RELEASE_PREVIOUS=release_${previous_version}
          make release-push-dev

    - [ ] Create and push release branch:

          make release-create-rc

    - [ ] Open pull requests from your fork of branch ``version-${version}`` to upstream ``release_${version}`` and of ``version-${next_version}.dev`` to ``dev``.
    - [ ] [Create milestone](https://github.com/galaxyproject/galaxy/milestones) `${next_version}` for next release.
    - [ ] Update ``MILESTONE_NUMBER`` in the [maintenance bot](https://github.com/galaxyproject/galaxy/blob/dev/.github/workflows/maintenance_bot.yaml) to reference `${next_version}` so it properly tags new pull requests.

- [ ] **Issue Review Timeline Notes**

    - [ ] Ensure any security fixes will be ready prior to ${freeze_date} + 1 week, to allow time for notification prior to release.
    - [ ] Ensure ownership of outstanding bugfixes and track progress during freeze.

- [ ] **Deploy and Test Release on galaxy-test**

    - [ ] Update test.galaxyproject.org to ensure it is running the ``release_${version}`` branch.
    - [ ] Conduct formal release testing on test.galaxyproject.org (see ${version} release testing plan).
    - [ ] Ensure all critical bugs detected during release testing have been fixed.


- [ ] **Run tool and workflow tests:**

    - [ ] IUC:
        - [ ] Open an issue "Test release ${version}" on the iuc repo: https://github.com/galaxyproject/tools-iuc/
        - [ ] Post this comment to that issue: `/run-all-tool-tests branch=release_${version}`. This will trigger the "Weekly global Tool Linting and Tests" github workflow that lints and tests all IUC tools.
        - [ ] Wait for the workflow to complete, after which a brief summary will be automatically posted to the issue with a link to the workflow results.
        - [ ] Examine workflow results, comparing them with the results of a [previous run of the same workflow](https://github.com/galaxyproject/tools-iuc/actions?query=workflow%3A%22Weekly+global+Tool+Linting+and+Tests%22) on the previous release (${previous_version}).
              For each failed test:
              - Does it occur under ${version} but not under ${previous_version}? If so:
                - Check if there's an issue open. If not, open a new issue.

    - [ ] IWC:
        - [ ] Open an issue "Test release ${version}" on the iwc repo: https://github.com/galaxyproject/iwc/
        - [ ] Post this comment to that issue: `/run-all-workflow-tests branch=release_${version}`. This will trigger the "Weekly global Workflow Linting and Tests" github workflow that lints and tests all IWC workflows.
        - [ ] Wait for the workflow to complete, after which a brief summary will be automatically posted to the issue with a link to the workflow results.
        - [ ] Examine workflow results, comparing them with the results of a [previous run of the same workflow](https://github.com/galaxyproject/iwc/actions?query=workflow%3A%22Weekly+global+Workflow+Linting+and+Tests%22) on the previous release (${previous_version}).
              For each failed test:
              - Does it occur under ${version} but not under ${previous_version}? If so:
                - Check if there's an issue open. If not, open a new issue.

- [ ] **Create Release Notes**

    - [ ] Review pull requests merged since `release_${previous_version}`, ensure their titles are properly formatted and they all have a `${version}` or `${next_version}` milestone attached. [Link](https://github.com/galaxyproject/galaxy/pulls?utf8=%E2%9C%93&q=is%3Apr+is%3Amerged+no%3Amilestone+-label%3Amerge+)
    - [ ] Switch to release branch and create a new branch for release notes

          git checkout release_${version} -b ${version}_release_notes
    - [ ] Bootstrap the release notes

          galaxy-release-util create-changelog ${version} --release-date ${release_date} --next-version ${next_version}
    - [ ] Open newly created files and manually curate major topics and release notes.
    - [ ] Run ``python scripts/release-diff.py release_${previous_version}`` and add configuration changes to release notes.
    - [ ] Add new release to doc/source/releases/index.rst
    - [ ] Open a pull request for the release notes branch.
    - [ ] Merge release notes pull request.

- [ ] **Deploy and Test Release on galaxy-main**
    - [ ] Update usegalaxy.org to ensure it is running the ``release_${version}`` branch.
    - [ ] Conduct second stage of release testing on usegalaxy.org.
    - [ ] [Update BioBlend CI testing](https://github.com/galaxyproject/bioblend/blob/main/.github/workflows/test.yaml) to include a ``release_${version}`` target: add ``- release_${version}`` to the ``galaxy_version`` list in ``.github/workflows/test.yaml`` .
    - [ ] Update GALAXY_RELEASE in IUC and devteam github workflows
        - [ ] https://github.com/galaxyproject/tools-iuc/blob/master/.github/workflows/
        - [ ] https://github.com/galaxyproject/tools-devteam/blob/master/.github/workflows/

- [ ] **Do Release**

    - [ ] Ensure all [blocking milestone issues](https://github.com/galaxyproject/galaxy/issues?q=is%3Aopen+is%3Aissue+milestone%3A${version}) have been resolved.

          galaxy-release-util check-blocking-issues ${version}
    - [ ] Ensure all [blocking milestone pull requests](https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+milestone%3A${version}) have been merged, closed, or postponed until the next release.

          galaxy-release-util check-blocking-prs ${version} --release-date ${release_date}
    - [ ] Ensure all pull requests merged into the pre-release branch during the freeze have [milestones attached](https://github.com/galaxyproject/galaxy/pulls?q=is%3Apr+is%3Aclosed+base%3Arelease_${version}+is%3Amerged+no%3Amilestone)
    - [ ] Ensure all pull requests merged into the pre-release branch during the freeze are the not [${next_version} milestones](https://github.com/galaxyproject/galaxy/pulls?q=is%3Apr+is%3Aclosed+base%3Arelease_${version}+is%3Amerged+milestone%3A${next_version})
    - [ ] Ensure release notes include all pull requests added during the freeze by re-running the release note bootstrapping:

          galaxy-release-util create-changelog ${version} --release-date ${release_date} --next-version ${next_version}
    - [ ] Ensure previous release is merged into current. [GitHub branch comparison](https://github.com/galaxyproject/galaxy/compare/release_${version}...release_${previous_version})
    - [ ] Create the first point release (v${version}.0) using the instructions at https://docs.galaxyproject.org/en/master/dev/create_release.html#creating-galaxy-point-releases

          galaxy-release-util create-release --new-version ${version}.0 --last-commit [insert latest tag, e.g. v24.1.4]

    - [ ] Open PR against planemo with a pin to the new packages

- [ ] **Announce Release**

    - [ ] Verify release included in https://docs.galaxyproject.org/en/master/releases/index.html.
    - [ ] Review announcement in https://github.com/galaxyproject/galaxy/blob/dev/doc/source/releases/${version}_announce.rst.
    - [ ] Announce release on [Galaxy Hub](https://galaxyproject.org/) as a news content item. [An example](https://galaxyproject.org/news/2024-02-07-galaxy-release-23-2/).
    - [ ] Post announcement to [Galaxy Help](https://help.galaxyproject.org/). [An example](https://help.galaxyproject.org/t/release-of-galaxy-23-2/11675).
    - [ ] Announce release on Galaxy's social media accounts ([Bluesky](https://bsky.app/profile/galaxyproject.bsky.social), [Mastodon](https://mstdn.science/@galaxyproject), [LinkedIn](https://linkedin.com/company/galaxy-project)).
    - [ ] Email announcement to [galaxy-dev](http://dev.list.galaxyproject.org/) and [galaxy-announce](http://announce.list.galaxyproject.org/) @lists.galaxyproject.org. [An example](https://lists.galaxyproject.org/archives/list/galaxy-announce@lists.galaxyproject.org/thread/ISB7ZNBDY3LQMC2KALGPVQ3DEJTH657Q/).
    - [ ] Adjust http://getgalaxy.org text and links to match current master branch by opening a PR at https://github.com/galaxyproject/galaxy-hub/

- [ ] **Complete release**

    - [ ] Close milestone ``${version}`` and ensure milestone ``${next_version}`` exists.
    - [ ] Close this issue.
"""  # noqa: E501
)

release_version_argument = click.argument("release-version", type=ClickVersion())

next_version_option = click.option(
    "--next-version",
    type=ClickVersion(),
    help="Next release version",
)

freeze_date_option = click.option(
    "--freeze-date",
    type=ClickDate(),
    required=True,
)

release_date_option = click.option(
    "--release-date",
    type=ClickDate(),
    required=True,
)

dry_run_option = click.option(
    "--dry-run", type=bool, default=False, help="Do not connect to GitHub's API, print out output"
)

log = logging.getLogger(__name__)


@click.group(help="Subcommands of this script can perform various tasks around creating Galaxy releases")
def cli():
    pass


@cli.command(help="Create release checklist issue on GitHub")
@group_options(
    release_version_argument,
    next_version_option,
    freeze_date_option,
    galaxy_root_option,
    release_date_option,
    dry_run_option,
)
def create_release_issue(
    release_version: Version,
    next_version: Version,
    freeze_date: datetime.date,
    galaxy_root: Path,
    release_date: datetime.date,
    dry_run: bool,
):
    verify_galaxy_root(galaxy_root)
    previous_version = _get_previous_release_version(galaxy_root, release_version)
    next_version = next_version or _get_next_release_version(release_version)
    assert next_version > release_version, "Next release version should be greater than release version"

    issue_template_params = dict(
        version=release_version,
        next_version=next_version,
        previous_version=previous_version,
        freeze_date=freeze_date,
        release_date=release_date,
    )
    issue_contents = RELEASE_ISSUE_TEMPLATE.substitute(**issue_template_params)
    issue_title = f"Publication of Galaxy Release v {release_version}"

    if dry_run:
        print(issue_title)
        print(issue_contents)
        return None
    try:
        github = github_client()
        repo = github.get_repo(f"{PROJECT_OWNER}/{PROJECT_NAME}")
        release_issue = repo.create_issue(
            title=issue_title,
            body=issue_contents,
        )
        return release_issue
    except GithubException:
        log.exception(
            "Failed to create an issue on GitHub. You need to be authenticated to use GitHub API."
            "\nSee galaxy_release_util/github_client.py"
        )


@cli.command(help="Create or update release changelog")
@group_options(release_version_argument, next_version_option, galaxy_root_option, release_date_option)
def create_changelog(release_version: Version, next_version: Version, galaxy_root: Path, release_date: datetime.date):

    def create_release_file() -> None:
        enhancement_targets = "\n\n".join(f".. enhancement_tag_{value}" for value in GROUPED_TAGS.values())
        bug_targets = "\n\n".join(f".. bug_tag_{value}" for value in GROUPED_TAGS.values())

        content = string.Template(TEMPLATE).substitute(release=release_version)
        content = content.replace(".. enhancement", f"{enhancement_targets}\n\n.. enhancement")
        content = content.replace(".. bug", f"{bug_targets}\n\n.. bug")
        filename = _release_file(galaxy_root, f"{release_version}.rst")
        _write_file(filename, content, skip_if_exists=True)

    def create_announcement_file() -> None:
        month = calendar.month_name[release_date.month]
        year = release_date.year
        content = ANNOUNCE_TEMPLATE.substitute(month_name=month, year=year, release=release_version)
        filename = _release_file(galaxy_root, f"{release_version}_announce.rst")
        _write_file(filename, content, skip_if_exists=False)

    def create_user_announcement_file() -> None:
        month = calendar.month_name[release_date.month]
        year = release_date.year
        content = ANNOUNCE_USER_TEMPLATE.substitute(month_name=month, year=year, release=release_version)
        filename = _release_file(galaxy_root, f"{release_version}_announce_user.rst")
        _write_file(filename, content, skip_if_exists=True)

    def create_prs_file() -> None:
        _write_file(_get_prs_file(galaxy_root, release_version), PRS_TEMPLATE, skip_if_exists=True)

    def create_next_release_announcement_file() -> None:
        content = NEXT_TEMPLATE.substitute(release=next_version)
        filename = _release_file(galaxy_root, f"{next_version}_announce.rst")
        _write_file(filename, content, skip_if_exists=True)

    verify_galaxy_root(galaxy_root)
    next_version = next_version or _get_next_release_version(release_version)
    create_release_file()
    create_announcement_file()
    create_user_announcement_file()
    create_prs_file()
    create_next_release_announcement_file()
    _load_prs(galaxy_root, release_version, release_date)


@cli.command(help="List release blocking PRs")
@group_options(release_version_argument, release_date_option)
def check_blocking_prs(release_version: Version, release_date: datetime.date):
    block = 0
    for pr in _get_prs(release_version, release_date, state="open"):
        click.echo(f"Blocking PR| {_pr_to_str(pr)}", err=True)
        block = 1
    sys.exit(block)


@cli.command(help="List release blocking issues")
@group_options(release_version_argument)
def check_blocking_issues(release_version: Version):
    block = 0
    github = github_client()
    repo = github.get_repo(f"{PROJECT_OWNER}/{PROJECT_NAME}")
    issues = repo.get_issues(state="open")
    for issue in issues:
        if (
            issue.milestone
            and issue.milestone.title == str(release_version)
            and "Publication of Galaxy Release" not in issue.title
            and not issue.pull_request
        ):
            click.echo(f"Blocking issue| {_issue_to_str(issue)}", err=True)
            block = 1
    sys.exit(block)


def _get_prs_file(galaxy_root: Path, release_version: Version) -> Path:
    return _release_file(galaxy_root, f"{release_version}_prs.rst")


def _load_prs(galaxy_root: Path, release_version: Version, release_date: datetime.date) -> None:

    def get_prs_from_prs_file() -> Set[int]:
        with open(_get_prs_file(galaxy_root, release_version)) as fh:
            return set(map(int, re.findall(r"\.\. _Pull Request (\d+): https", fh.read())))

    seen_prs = get_prs_from_prs_file()
    prs = _get_prs(release_version, release_date)
    n_prs = len(prs)
    for i, pr in enumerate(prs):
        if pr.number not in seen_prs:
            print(f"Processing PR {i + 1} of {n_prs}")
            _pr_to_doc(
                galaxy_root=galaxy_root,
                release_version=release_version,
                pr=pr,
            )
        else:
            print(f"Skipping PR {i + 1} of {n_prs} (previously processed)")


def _get_prs(release_version: Version, release_date: datetime.date, state: str = "closed") -> List[PullRequest]:
    github = github_client()
    repo = github.get_repo(f"{PROJECT_OWNER}/{PROJECT_NAME}")

    # A pull request that was last updated before the previous release branch was created cannot be part of this release:
    # the value of `updated_at` is updated on merge, so it had to be merged before the branch existed and, therefore, included in the previous release.
    # Given that we can't reliably determine when the previous release branch was created, we subtract a year from
    # the planned release date of the current release and use that as a cutoff date. For example, if the planned release date is August 1, 2025,
    # we will not consider pull requests that were last updated before August 1, 2024. This is based on the assumption that
    # there have to be at least two release branches created within a year: the previous release + the current release.
    _cutoff_date = release_date.replace(year=release_date.year - 1)
    cutoff_time = datetime.datetime.combine(_cutoff_date, datetime.time.min)

    prs: List[PullRequest] = []
    counter = 0
    print("Collecting relevant pull requests...")
    for pr in repo.get_pulls(state=state, sort="updated", direction="desc"):
        assert pr.updated_at
        if pr.updated_at.replace(tzinfo=None) < cutoff_time:
            break
        counter += 1
        if counter % 100 == 0:
            print(
                f"Examined {counter} PRs; collected {len(prs)} (currently on #{pr.number} updated on {pr.updated_at.date()})"
            )
        # Select PRs that are merged + have correct milestone + have not been previously collected and added to the prs file
        proper_state = state != "closed" or pr.merged_at  # open PRs or PRs that have been merged
        if proper_state and pr.milestone and pr.milestone.title == str(release_version):
            prs.append(pr)

    print(f"Collected {len(prs)} pull requests")
    return prs


def _pr_to_doc(galaxy_root: Path, release_version: Version, pr: PullRequest) -> None:

    def extend_target(target: str, line: str, source: str) -> str:
        from_str = f".. {target}\n"
        if target not in source:
            raise Exception(f"Failed to find target [{target}] in source [{source}]")
        return source.replace(from_str, f"{from_str}{line}\n")

    def extend_prs_file_content(filename: Path) -> None:
        content = _read_file(filename)
        text = f".. _Pull Request {pr.number}: {PROJECT_URL}/pull/{pr.number}"
        content = extend_target("github_links", text, content)
        _write_file(filename, content)

    def extend_release_file_content(filename: Path) -> None:
        content = _read_file(filename)
        text_target = _text_target(pr)
        if text_target is not None:
            content = extend_target(text_target, to_doc, content)
        _write_file(filename, content)

    def extend_user_announce_file_content(filename: Path) -> None:
        content = _read_file(filename)
        labels = _pr_to_labels(pr)
        if "area/datatypes" in labels:
            content = extend_target("datatypes", to_doc, content)
        if "area/visualizations" in labels:
            content = extend_target("visualizations", to_doc, content)
        if "area/tools" in labels:
            content = extend_target("tools", to_doc, content)
        _write_file(filename, content)

    def make_pr_to_doc() -> str:
        to_doc = pr.title.rstrip(".") + " "
        to_doc += f"\n(thanks to `@{pr.user.login} <https://github.com/{pr.user.login}>`__)."
        to_doc += f"\n`Pull Request {pr.number}`_"
        return wrap(to_doc)

    to_doc = make_pr_to_doc()

    filename = _release_file(galaxy_root, f"{release_version}.rst")
    extend_release_file_content(filename)

    filename = _release_file(galaxy_root, f"{release_version}_announce_user.rst")
    extend_user_announce_file_content(filename)

    filename = _release_file(galaxy_root, f"{release_version}_prs.rst")
    extend_prs_file_content(filename)


def _read_file(path: Path) -> str:
    with open(path) as f:
        return f.read()


def _write_file(path: Path, contents: str, skip_if_exists: bool = False) -> None:
    if skip_if_exists and os.path.exists(path):
        return
    with open(path, "w") as f:
        f.write(contents)


def _get_next_release_version(version: Version) -> Version:
    return Version(f"{version.major}.{version.minor + 1}")


def _get_previous_release_version(galaxy_root: Path, version: Version) -> Optional[Version]:
    """Return previous release version if it exists."""
    # NOTE: We convert strings to Version objects to compare apples to apples:
    # str(Version(foo)) is not the same as the string foo: str(Version("22.05")) == "22.5"
    prev = None
    for release in _get_release_version_strings(galaxy_root):
        release_version = Version(release)
        if release_version >= version:
            return prev
        prev = release_version
    return prev


def _get_release_version_strings(galaxy_root: Path) -> List[str]:
    """Return sorted list of release version strings."""
    all_files = _get_release_documentation_filenames(galaxy_root)
    release_notes_file_pattern = re.compile(r"\d+\.\d+.rst")
    filenames = [f.rstrip(".rst") for f in all_files if release_notes_file_pattern.match(f)]
    return sorted(filenames)


def _get_release_documentation_filenames(galaxy_root: Path) -> List[str]:
    """Return contents of release documentation directory."""
    releases_path = galaxy_root / "doc" / "source" / "releases"
    if not os.path.exists(releases_path):
        msg = f"Path to releases documentation not found: {releases_path}"
        raise Exception(msg)
    return sorted(os.listdir(releases_path))


def _release_file(galaxy_root: Path, filename: Optional[str]) -> Path:
    """Construct and return path to a release documentation file."""
    filename = filename or OLDER_RELEASES_FILENAME
    return galaxy_root / "doc" / "source" / "releases" / filename


def _process_sentence(message: str) -> str:
    # Strip tags like [15.07].
    message = strip_release(message=message)
    # Link issues and pull requests...
    issue_url = f"https://github.com/{PROJECT_OWNER}/{PROJECT_NAME}/issues"
    message = re.sub(r"#(\d+)", rf"`#\1 <{issue_url}/\1>`__", message)
    return message


def wrap(message: str) -> str:
    message = _process_sentence(message)
    wrapper = textwrap.TextWrapper(initial_indent="* ")
    wrapper.subsequent_indent = "  "
    wrapper.width = 160
    message_lines = message.splitlines()
    first_lines = "\n".join(wrapper.wrap(message_lines[0]))
    wrapper.initial_indent = "  "
    rest_lines = "\n".join("\n".join(wrapper.wrap(m)) for m in message_lines[1:])
    return first_lines + ("\n" + rest_lines if rest_lines else "")


def _issue_to_str(issue: Issue) -> str:
    if isinstance(issue, str):
        return issue
    return f"Issue #{issue.number} ({issue.title}) {issue.html_url}"
