import calendar
import datetime
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
    ClickVersion,
    freeze_date_option,
    galaxy_root_option,
    group_options,
    next_version_option,
    owner_option,
    previous_version_option,
    release_date_option,
    repo_option,
)
from .github_client import github_client
from .metadata import (
    PROJECT_NAME,
    PROJECT_OWNER,
    _pr_to_labels,
    _pr_to_str,
    get_project_url,
    get_repo_name,
    strip_release,
)
from .release_config import (
    ReleaseConfig,
    load_release_config,
)
from .util import (
    escape_rst_inline,
    verify_galaxy_root,
)

OLDER_RELEASES_FILENAME = "older_releases.rst"

ANNOUNCE_TEMPLATE = string.Template(
    """
===========================================================
${release} Galaxy Release (${month_name} ${year})
===========================================================

.. include:: _header.rst

Please see the `${release} user release notes <${release}_announce_user.html>`__ for a summary of new user features.
The `GitHub Release Notes <https://github.com/galaxyproject/galaxy/releases/tag/v${release}.0>`__ provide a comprehensive overview of all changes.

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
Run ``python scripts/release-diff.py release_<previous_version>`` in the Galaxy root directory
to get a diff of configuration changes between releases.
Add any more content or drop section if it's empty.

Deprecation Notices
===========================================================
Add content or drop section.

Developer Notes
===========================================================
Add content or drop section.

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

Please see the full `release notes <https://github.com/galaxyproject/galaxy/releases/tag/v${release}.0>`__ for more details.

Highlights
===========================================================

Discover some of the exciting new features, enhancements, and improvements in Galaxy ${release}.

Feature1
--------

A description of the feature and its main highlights. Include screenshots/videos if applicable.

Feature2
--------

A description of the feature and its main highlights. Include screenshots/videos if applicable.

Feature3
--------

A description of the feature and its main highlights. Include screenshots/videos if applicable.


----

Visualizations Updates
===========================================================

.. visualizations

Datatypes Updates
===========================================================

.. datatypes

Builtin Tool Updates
===========================================================

.. tools

Please see the full `release notes <https://github.com/galaxyproject/galaxy/releases/tag/v${release}.0>`__ for more details.
The admin-facing release notes are available :doc:`here <${release}_announce>`.

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

- [ ] **Freeze Release (on or around ${freeze_date})**

    - [ ] Verify that your installed version of `galaxy-release-util` is up-to-date.
    - [ ] [Create milestone](https://github.com/galaxyproject/galaxy/milestones) `${next_version}` for next release and **set its due date** to the planned release date. `galaxy-release-util` reads that due date as the release date for `${next_version}`, so leaving it empty will block the next release's changelog. Note the milestone number from the URL (`https://github.com/galaxyproject/galaxy/milestone/<NUMBER>`).
    - [ ] Update ``MILESTONE_NUMBER`` in the [maintenance bot](https://github.com/galaxyproject/galaxy/blob/dev/.github/workflows/maintenance_bot.yaml) to reference `${next_version}` so it properly tags new pull requests. Open a pull request to apply the change.
    - [ ] Hold the Freeze Meeting (one week before freeze, usually during a weekly dev meeting). Review [open milestone pull requests](https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+milestone%3A${version}+-label%3Akind%2Fbug+-is%3Adraft), decide what will be included in `${version}`, and assign reviewers to ensure merges complete before the freeze.
    - [ ] Audit milestone labels. Ensure all open pull requests in the milestone have appropriate `kind/*` labels and correct milestone assignment. [Find unlabeled PRs](https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+milestone%3A${version}+-label%3A%22kind%2Ffeature%22+-label%3A%22kind%2Fbug%22+-label%3A%22kind%2Fenhancement%22+-label%3A%22kind%2Frefactoring%22+-label%3Adependencies).
    - [ ] Ensure all [freeze blocking milestone pull requests](https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+milestone%3A${version}+-label%3A"kind%2Fbug"+-is%3Adraft) have been merged, closed, or postponed until the next release.
    - [ ] Announce the freeze on the following channels:
        - [ ] https://matrix.to/#/#galaxyproject_ui-ux:gitter.im
        - [ ] https://matrix.to/#/#galaxyproject_backend:gitter.im

      Use the following message:

      > As of today, we are officially frozen for ${version}. No new features or enhancements should be added to the ${version} milestone after this point. Reviews are appreciated so we can proceed with branching. Remaining PRs: https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+-label%3A%22kind%2Fbug%22+-is%3Adraft+milestone%3A${version}

- [ ] **Review Merged Pull Requests**

    - [ ] Identify merged pull requests [missing a milestone](https://github.com/galaxyproject/galaxy/pulls?utf8=%E2%9C%93&q=is%3Apr+is%3Amerged+no%3Amilestone+-label%3Amerge+sort%3Amerged+) merged since `release_${previous_version}` and assign the correct milestone.
    - [ ] Review titles of all pull requests in the `${version}` milestone. Adjust them conservatively to match Galaxy contribution guidelines.

- [ ] **Branch Release**

    - [ ] Add latest database revision identifier to ``REVISION_TAGS`` in ``lib/galaxy/model/migrations/dbrevisions.py``. To obtain the identifier, ensure `dev` is up to date and run:

          git pull upstream dev
          ./manage_db.sh version

      Note the revision identifier marked as head. Add the mapping for ``${version}`` and open a pull request.

    - [ ] Merge the latest release into dev and push upstream.

          make release-merge-stable-to-next RELEASE_PREVIOUS=release_${previous_version}
          make release-push-dev

    - [ ] Create and push release branch:

          make release-create-rc

      This creates two branches:

        - ``version-${next_version}.dev``: Open a pull request against `dev`. Verify the future version number and remove any generated client hash build artifacts if present.
        - ``version-${version}.rc1``: Open a pull request against `release_${version}`.

      Note: These steps may silently fail without producing any branches. Inspect ``cat packages/app/make-dist.log`` if branches were not created.

    - [ ] Create a new GitHub label `release-testing-${version}` at https://github.com/galaxyproject/galaxy/labels to tag all release testing PRs.

    - [ ] Announce branching on the following channels:
        - [ ] https://matrix.to/#/#galaxyproject_ui-ux:gitter.im
        - [ ] https://matrix.to/#/#galaxyproject_backend:gitter.im

      Use the following message:

      > The ${version} release branch has been created.

- [ ] **Assemble Testing Team**

    - [ ] Reach out per email to assemble the testing team for `${version}`. Use the following template:

      > **Galaxy ${version} Release Testing**
      >
      > Hi,
      >
      > I am organizing testing for the upcoming Galaxy release and would like to ask whether you would be available to participate.
      >
      > **Testing window:**
      > <START_DATE> through <END_DATE>
      >
      > **Kick off Meeting:**
      > <KICK_OFF_DATE_TIME>
      > Video call link: <MEETING_LINK>
      >
      > **Time commitment:**
      > Approximately 1-2 hours per day. Testing consists of working through as many assigned PRs as time permits. There will be one short kick off meeting at the start of the testing window.
      >
      > **What release testing involves:**
      > Release testing focuses on validating Galaxy GitHub pull requests. Each PR represents either a new feature, an enhancement, or a bug fix. Testing means exercising the changes as a user would and verifying that they behave correctly and do not introduce regressions. A curated list of PRs will be provided, and detailed guidance on the testing workflow and PR selection will be covered in the kick off meeting.
      >
      > I will be available throughout the testing period, and the galaxyproject/release-testing Matrix room at https://matrix.to/#/%23galaxyproject_release-testing:gitter.im will be used for coordination and questions.
      >
      > If you are able to participate, I can follow up with more details.
      >
      > Thanks!

- [ ] **Run tool and workflow tests:**

    - [ ] IUC:
        - [ ] Open an issue "Test release ${version}" on the iuc repo: https://github.com/galaxyproject/tools-iuc/
        - [ ] Post this comment to that issue: `/run-all-tool-tests branch=release_${version}`. This will trigger the "Weekly global Tool Linting and Tests" github workflow that lints and tests all IUC tools.
        - [ ] Wait for the workflow to complete, after which a brief summary will be automatically posted to the issue with a link to the workflow results.
        - [ ] Examine workflow results, comparing them with the results of a [previous run of the same workflow](https://github.com/galaxyproject/tools-iuc/actions?query=workflow%3A%22Weekly+global+Tool+Linting+and+Tests%22) on the previous release (${previous_version}).
              For each failed test:
              - Does it occur under ${version} but not under ${previous_version}? If so:
                - Check if there's an issue open. If not, open a new issue.
        - [ ] Add/Update tests against IUC.
            e.g.: https://github.com/galaxyproject/tools-iuc/pull/6995

    - [ ] IWC:
        - [ ] Open an issue "Test release ${version}" on the iwc repo: https://github.com/galaxyproject/iwc/
        - [ ] Post this comment to that issue: `/run-all-workflow-tests branch=release_${version}`. This will trigger the "Weekly global Workflow Linting and Tests" github workflow that lints and tests all IWC workflows.
        - [ ] Wait for the workflow to complete, after which a brief summary will be automatically posted to the issue with a link to the workflow results.
        - [ ] Examine workflow results, comparing them with the results of a [previous run of the same workflow](https://github.com/galaxyproject/iwc/actions?query=workflow%3A%22Weekly+global+Workflow+Linting+and+Tests%22) on the previous release (${previous_version}).
              For each failed test:
              - Does it occur under ${version} but not under ${previous_version}? If so:
                - Check if there's an issue open. If not, open a new issue.
        - [ ] Add/Update tests against IWC.
          e.g.: https://github.com/galaxyproject/iwc/pull/867

- [ ] **Issue Review Timeline Notes**

    - [ ] Ensure any security fixes will be ready prior to ${freeze_date} + 2 weeks, to allow time for notification prior to release.
    - [ ] Ensure ownership of outstanding bugfixes and track progress during freeze.

- [ ] **Deploy and Test Release on galaxy-test**

    - [ ] Update test.galaxyproject.org to ensure it is running the ``release_${version}`` branch.
    - [ ] Request that testtoolshed.g2.bx.psu.edu is updated to ``${version}``.
    - [ ] Conduct formal release testing on test.galaxyproject.org (see ${version} release testing plan).
    - [ ] Ensure all critical bugs detected during release testing have been fixed.

- [ ] **Create Release Notes**

    - [ ] Review pull requests merged since `release_${previous_version}`, ensure their titles are properly formatted and they all have a `${version}` or `${next_version}` milestone attached. [Link](https://github.com/galaxyproject/galaxy/pulls?utf8=%E2%9C%93&q=is%3Apr+is%3Amerged+no%3Amilestone+-label%3Amerge+)
    - [ ] Switch to release branch and create a new branch for release notes

          git checkout release_${version} -b ${version}_release_notes
    - [ ] Bootstrap the release notes

          galaxy-release-util create-changelog ${version}

      Run this from the Galaxy root. The release date and `${next_version}` are read from the milestones; pass `--release-date` or `--next-version` to override either.

      Note: each run rewrites ``${version}_announce.rst`` from the template. ``${version}_announce_user.rst``, ``${version}_prs.rst`` and the ``${next_version}`` stub are preserved and only gain newly merged pull requests, so re-running to pick up new pull requests costs you only the admin-facing file.
    - [ ] Open newly created files and manually curate major topics and release notes. Leave the admin notes in ``${version}_announce.rst`` until after the final re-run below, or keep them elsewhere until then.
    - [ ] Run ``python scripts/release-diff.py release_${previous_version}`` and add configuration changes to release notes.
    - [ ] Add new release to doc/source/releases/index.rst
    - [ ] Open a pull request for the release notes branch.
    - [ ] Merge release notes pull request.

- [ ] **Deploy and Test Release on galaxy-main**
    - [ ] Update usegalaxy.org to ensure it is running the ``release_${version}`` branch.
    - [ ] Request that toolshed.g2.bx.psu.edu is updated to ``${version}``.
    - [ ] Conduct second stage of release testing on usegalaxy.org.
        - [ ] Verify weekly, ideally before or during a developer's meeting, by checking the Slack admin channel and asking for any new release related issues.
        - [ ] Verify that there have not been any new release related issues in sentry.galaxyproject.org.
    - [ ] [Update BioBlend CI testing](https://github.com/galaxyproject/bioblend/blob/main/.github/workflows/test.yaml) to include a ``release_${version}`` target: add ``- release_${version}`` to the ``galaxy_version`` list in ``.github/workflows/test.yaml`` .
    - [ ] Update GALAXY_RELEASE in IUC and devteam github workflows
        - [ ] https://github.com/galaxyproject/tools-iuc/blob/master/.github/workflows/
        - [ ] https://github.com/galaxyproject/tools-devteam/blob/master/.github/workflows/

- [ ] **Do Release**

    - [ ] Ensure all [blocking milestone issues](https://github.com/galaxyproject/galaxy/issues?q=is%3Aopen+is%3Aissue+milestone%3A${version}) have been resolved.

          galaxy-release-util check-blocking-issues ${version}
    - [ ] Ensure all [blocking milestone pull requests](https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+milestone%3A${version}) have been merged, closed, or postponed until the next release.

          galaxy-release-util check-blocking-prs ${version}
    - [ ] Ensure all pull requests merged into the pre-release branch during the freeze have [milestones attached](https://github.com/galaxyproject/galaxy/pulls?q=is%3Apr+is%3Aclosed+base%3Arelease_${version}+is%3Amerged+no%3Amilestone)
    - [ ] Ensure all pull requests merged into the pre-release branch during the freeze are not in the [${next_version} milestone](https://github.com/galaxyproject/galaxy/pulls?q=is%3Apr+is%3Aclosed+base%3Arelease_${version}+is%3Amerged+milestone%3A${next_version})
    - [ ] Ensure release notes include all pull requests added during the freeze by re-running the release note bootstrapping:

          galaxy-release-util create-changelog ${version}

      This rewrites ``${version}_announce.rst`` from the template again, so re-apply the admin notes afterwards.
    - [ ] Ensure previous release is merged into current. [GitHub branch comparison](https://github.com/galaxyproject/galaxy/compare/release_${version}...release_${previous_version})
    - [ ] Create the first point release (v${version}.0) using the instructions at https://docs.galaxyproject.org/en/master/dev/create_release.html#creating-galaxy-point-releases

          galaxy-release-util create-release --new-version ${version}.0 --last-commit <LAST_RELEASE_TAG>

    - [ ] Open PR against planemo with a pin to the new packages

    - [ ] Ensure the latest release is merged into the `master` branch, not via the Github UI but rather via the `--ff-only` merge command. The branches can be compared here: https://github.com/galaxyproject/galaxy/compare/master...release_${version}

- [ ] **Announce Release**

    - [ ] Verify release included in https://docs.galaxyproject.org/en/master/releases/index.html.
    - [ ] Review announcement in https://github.com/galaxyproject/galaxy/blob/dev/doc/source/releases/${version}_announce.rst.
    - [ ] Adjust http://getgalaxy.org text and links to match current master branch by opening a PR at https://github.com/galaxyproject/galaxy-hub/
    - [ ] Add gxy.io link to notes (e.g.: https://github.com/galaxyproject/gxy.io/pull/76)
    - [ ] Announce release on [Galaxy Hub](https://galaxyproject.org/) not as a full news content item, but rather as a `external_url` link to the user facing release notes.
    - [ ] Post announcement to [Galaxy Help](https://help.galaxyproject.org/). [An example](https://help.galaxyproject.org/t/release-of-galaxy-23-2/11675).
    - [ ] Announce release on Galaxy's social media accounts ([Bluesky](https://bsky.app/profile/galaxyproject.bsky.social), [Mastodon](https://mstdn.science/@galaxyproject), [LinkedIn](https://linkedin.com/company/galaxy-project)).
    - [ ] Email announcement to [galaxy-dev](http://dev.list.galaxyproject.org/) and [galaxy-announce](http://announce.list.galaxyproject.org/) @lists.galaxyproject.org. [An example](https://lists.galaxyproject.org/archives/list/galaxy-announce@lists.galaxyproject.org/thread/ISB7ZNBDY3LQMC2KALGPVQ3DEJTH657Q/).

- [ ] **Complete release**

    - [ ] Close milestone ``${version}`` and ensure milestone ``${next_version}`` exists with its due date set. Closing ``${version}`` is safe: milestones are read regardless of state, so the ``${version}`` release notes can still be regenerated afterwards.
    - [ ] Close this issue.
"""  # noqa: E501
)

release_version_argument = click.argument("release-version", type=ClickVersion())

dry_run_option = click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print what would happen instead of opening issues or collecting pull requests.",
)


def _resolve_config(*required: str, **kwargs) -> ReleaseConfig:
    """Resolve the release config and assert that the values this command needs are known."""
    try:
        config = load_release_config(**kwargs)
        config.require(*required)
    except (ValueError, FileNotFoundError) as e:
        raise click.UsageError(str(e)) from e
    return config


@click.group(help="Subcommands of this script can perform various tasks around creating Galaxy releases")
def cli():
    pass


@cli.command(help="Create release checklist issue on GitHub")
@group_options(
    release_version_argument,
    galaxy_root_option,
    owner_option,
    repo_option,
    previous_version_option,
    next_version_option,
    release_date_option,
    freeze_date_option,
    dry_run_option,
)
def create_release_issue(
    release_version: Version,
    galaxy_root: Path,
    owner: str,
    repo: str,
    previous_version: Optional[Version],
    next_version: Optional[Version],
    release_date: Optional[datetime.date],
    freeze_date: Optional[datetime.date],
    dry_run: bool,
):
    verify_galaxy_root(galaxy_root)
    config = _resolve_config(
        "previous_version",
        "next_version",
        "release_date",
        "freeze_date",
        galaxy_root=galaxy_root,
        release_version=release_version,
        owner=owner,
        repo=repo,
        previous_version=previous_version,
        next_version=next_version,
        release_date=release_date,
        freeze_date=freeze_date,
    )
    assert config.next_version
    if config.next_version <= config.current_version:
        raise click.UsageError(
            f"--next-version ({config.next_version}) must be greater than release version ({config.current_version})"
        )

    issue_template_params = dict(
        version=release_version,
        next_version=config.next_version,
        previous_version=config.previous_version,
        freeze_date=config.freeze_date,
        release_date=config.release_date,
    )
    issue_contents = RELEASE_ISSUE_TEMPLATE.substitute(**issue_template_params)
    issue_title = f"Publication of Galaxy Release v {release_version}"

    if dry_run:
        click.echo(issue_title)
        click.echo(issue_contents)
        return None
    try:
        github = github_client()
        github_repo = github.get_repo(get_repo_name(config.owner, config.repo))
        release_issue = github_repo.create_issue(
            title=issue_title,
            body=issue_contents,
        )
        return release_issue
    except GithubException as e:
        raise click.ClickException(
            f"Failed to create release issue on GitHub: {e}. "
            "Ensure GITHUB_AUTH is set to a valid personal access token."
        ) from e


@cli.command(help="Create or update release changelog")
@group_options(
    release_version_argument,
    galaxy_root_option,
    owner_option,
    repo_option,
    next_version_option,
    release_date_option,
    dry_run_option,
)
def create_changelog(
    release_version: Version,
    galaxy_root: Path,
    owner: str,
    repo: str,
    next_version: Optional[Version],
    release_date: Optional[datetime.date],
    dry_run: bool,
):
    verify_galaxy_root(galaxy_root)
    config = _resolve_config(
        "release_date",
        "next_version",
        galaxy_root=galaxy_root,
        release_version=release_version,
        owner=owner,
        repo=repo,
        next_version=next_version,
        release_date=release_date,
    )
    assert config.release_date and config.next_version
    release_date = config.release_date
    next_version = config.next_version

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

    create_announcement_file()
    create_user_announcement_file()
    create_prs_file()
    create_next_release_announcement_file()
    if dry_run:
        click.echo("Dry run: skipping GitHub API call to load PRs")
    else:
        _load_prs(galaxy_root, release_version, release_date, config.owner, config.repo)


@cli.command(help="List release blocking PRs")
@group_options(
    release_version_argument,
    galaxy_root_option,
    owner_option,
    repo_option,
    release_date_option,
    dry_run_option,
)
def check_blocking_prs(
    release_version: Version,
    galaxy_root: Path,
    owner: str,
    repo: str,
    release_date: Optional[datetime.date],
    dry_run: bool,
):
    verify_galaxy_root(galaxy_root)
    config = _resolve_config(
        "release_date",
        galaxy_root=galaxy_root,
        release_version=release_version,
        owner=owner,
        repo=repo,
        release_date=release_date,
    )
    assert config.release_date
    if dry_run:
        click.echo(
            f"Dry run: would check blocking PRs for milestone {release_version} "
            f"(release date {config.release_date})"
        )
        sys.exit(0)
    block = 0
    for pr in _get_prs(release_version, config.release_date, config.owner, config.repo, state="open"):
        click.echo(f"Blocking PR| {_pr_to_str(pr)}", err=True)
        block = 1
    sys.exit(block)


@cli.command(help="List release blocking issues")
@group_options(
    release_version_argument,
    galaxy_root_option,
    owner_option,
    repo_option,
    dry_run_option,
)
def check_blocking_issues(
    release_version: Version,
    galaxy_root: Path,
    owner: str,
    repo: str,
    dry_run: bool,
):
    verify_galaxy_root(galaxy_root)
    # Issues are selected by milestone alone, so no dates need resolving here.
    if dry_run:
        click.echo(f"Dry run: would check blocking issues for milestone {release_version}")
        sys.exit(0)
    block = 0
    github = github_client()
    github_repo = github.get_repo(get_repo_name(owner, repo))
    issues = github_repo.get_issues(state="open")
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


def _load_prs(
    galaxy_root: Path,
    release_version: Version,
    release_date: datetime.date,
    owner: str = PROJECT_OWNER,
    repo: str = PROJECT_NAME,
) -> None:

    def get_prs_from_prs_file() -> Set[int]:
        with open(_get_prs_file(galaxy_root, release_version)) as fh:
            return set(map(int, re.findall(r"\.\. _Pull Request (\d+): https", fh.read())))

    seen_prs = get_prs_from_prs_file()
    prs = _get_prs(release_version, release_date, owner, repo)
    n_prs = len(prs)
    for i, pr in enumerate(prs):
        if pr.number not in seen_prs:
            click.echo(f"Processing PR {i + 1} of {n_prs}")
            _pr_to_doc(
                galaxy_root=galaxy_root,
                release_version=release_version,
                pr=pr,
                owner=owner,
                repo=repo,
            )
        else:
            click.echo(f"Skipping PR {i + 1} of {n_prs} (previously processed)")


def _get_prs(
    release_version: Version,
    release_date: datetime.date,
    owner: str = PROJECT_OWNER,
    repo_name: str = PROJECT_NAME,
    state: str = "closed",
) -> List[PullRequest]:
    github = github_client()
    repo = github.get_repo(get_repo_name(owner, repo_name))

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
    click.echo("Collecting relevant pull requests...")
    for pr in repo.get_pulls(state=state, sort="updated", direction="desc"):
        if pr.updated_at is None:
            continue
        if pr.updated_at.replace(tzinfo=None) < cutoff_time:
            break
        counter += 1
        if counter % 100 == 0:
            click.echo(
                f"Examined {counter} PRs; collected {len(prs)} (currently on #{pr.number} updated on {pr.updated_at.date()})"
            )
        # Select PRs that are merged + have correct milestone + have not been previously collected and added to the prs file
        proper_state = state != "closed" or pr.merged_at  # open PRs or PRs that have been merged
        if proper_state and pr.milestone and pr.milestone.title == str(release_version):
            prs.append(pr)

    click.echo(f"Collected {len(prs)} pull requests")
    return prs


def _pr_to_doc(
    galaxy_root: Path,
    release_version: Version,
    pr: PullRequest,
    owner: str = PROJECT_OWNER,
    repo: str = PROJECT_NAME,
) -> None:
    project_url = get_project_url(owner, repo)

    def extend_target(target: str, line: str, source: str) -> str:
        from_str = f".. {target}\n"
        if target not in source:
            raise Exception(f"Failed to find target [{target}] in source [{source}]")
        return source.replace(from_str, f"{from_str}{line}\n")

    def extend_prs_file_content(filename: Path) -> None:
        content = _read_file(filename)
        text = f".. _Pull Request {pr.number}: {project_url}/pull/{pr.number}"
        content = extend_target("github_links", text, content)
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
        to_doc = escape_rst_inline(pr.title).rstrip(".") + " "
        to_doc += f"\n(thanks to `@{pr.user.login} <https://github.com/{pr.user.login}>`__)."
        to_doc += f"\n`Pull Request {pr.number}`_"
        return wrap(to_doc, owner, repo)

    to_doc = make_pr_to_doc()

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


def _release_file(galaxy_root: Path, filename: Optional[str]) -> Path:
    """Construct and return path to a release documentation file."""
    filename = filename or OLDER_RELEASES_FILENAME
    return galaxy_root / "doc" / "source" / "releases" / filename


def _process_sentence(message: str, owner: str = PROJECT_OWNER, repo: str = PROJECT_NAME) -> str:
    # Strip tags like [15.07].
    message = strip_release(message=message)
    # Link issues and pull requests...
    issue_url = f"https://github.com/{owner}/{repo}/issues"
    message = re.sub(r"#(\d+)", rf"`#\1 <{issue_url}/\1>`__", message)
    return message


def wrap(message: str, owner: str = PROJECT_OWNER, repo: str = PROJECT_NAME) -> str:
    message = _process_sentence(message, owner, repo)
    wrapper = textwrap.TextWrapper(initial_indent="* ")
    wrapper.subsequent_indent = "  "
    wrapper.width = 160
    message_lines = message.splitlines()
    first_lines = "\n".join(wrapper.wrap(message_lines[0]))
    wrapper.initial_indent = "  "
    rest_lines = "\n".join("\n".join(wrapper.wrap(m)) for m in message_lines[1:])
    return first_lines + ("\n" + rest_lines if rest_lines else "")


def _issue_to_str(issue: Issue) -> str:
    return f"Issue #{issue.number} ({issue.title}) {issue.html_url}"
