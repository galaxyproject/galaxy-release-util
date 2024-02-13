# Little script to make HISTORY.rst more easy to format properly, lots TODO
# pull message down and embed, handle multiple, etc...

import calendar
import datetime
import os
import re
import string
import sys
import textwrap
from pathlib import Path
from typing import Optional

import click
from github.PullRequest import PullRequest
from packaging.version import Version

from .cli.options import (
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

RELEASE_DELTA_MONTHS = 4  # Number of months between releases.
MINOR_TO_MONTH = {0: 2, 1: 6, 2: 10}


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
${month_name} 20${year} Galaxy Release (v ${release})
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

Also check out the `${release} user release notes <${release}_announce_user.html>`__

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


Administration Notes
===========================================================
Add content or drop section.

Configuration Changes
===========================================================
Add content or drop section.

Deprecation Notices
===========================================================
Add content or drop section.

Release Notes
===========================================================

.. include:: ${release}.rst
   :start-after: announce_start

.. include:: _thanks.rst
"""  # noqa: E501
)

ANNOUNCE_USER_TEMPLATE = string.Template(
    """
===========================================================
${month_name} 20${year} Galaxy Release (v ${release})
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


Visualizations
===========================================================

.. visualizations

Datatypes
===========================================================

.. datatypes

Builtin Tool Updates
===========================================================

.. tools

Release Testing Team
===========================================================

A special thanks to the release testing team for testing many of the new features and reporting many bugs:

<team members go here>

Release Notes
===========================================================

Please see the :doc:`full release notes <${release}_announce>` for more details.

.. include:: ${release}_prs.rst

.. include:: _thanks.rst
"""  # noqa: E501
)

NEXT_TEMPLATE = string.Template(
    """
:orphan:

===========================================================
${month_name} 20${year} Galaxy Release (v ${version})
===========================================================


Schedule
===========================================================
 * Planned Freeze Date: ${freeze_date}
 * Planned Release Date: ${release_date}
"""
)

PRS_TEMPLATE = """
.. github_links
"""

RELEASE_ISSUE_TEMPLATE = string.Template(
    """

- [X] **Prep**

    - [X] ~~Create this release issue ``make release-issue``.~~
    - [X] ~~Set freeze date (${freeze_date}).~~

- [ ] **Branch Release (on or around ${freeze_date})**

    - [ ] Ensure all [blocking milestone PRs](https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+milestone%3A${version}) have been merged, delayed, or closed.

          make release-check-blocking-prs

    - [ ] Add latest database revision identifier (for ``release_${version}`` and ``${version}``) to ``REVISION_TAGS`` in ``galaxy/model/migrations/dbscript.py``.

    - [ ] Merge the latest release into dev and push upstream.

          make release-merge-stable-to-next RELEASE_PREVIOUS=release_${previous_version}
          make release-push-dev

    - [ ] Create and push release branch:

          make release-create-rc

    - [ ] Open PRs from your fork of branch ``version-${version}`` to upstream ``release_${version}`` and of ``version-${next_version}.dev`` to ``dev``.
    - [ ] Update ``MILESTONE_NUMBER`` in the [maintenance bot](https://github.com/galaxyproject/galaxy/blob/dev/.github/workflows/maintenance_bot.yaml) to `${next_version}` so it properly tags new PRs.

- [ ] **Issue Review Timeline Notes**

    - [ ] Ensure any security fixes will be ready prior to ${freeze_date} + 1 week, to allow time for notification prior to release.
    - [ ] Ensure ownership of outstanding bugfixes and track progress during freeze.

- [ ] **Deploy and Test Release**

    - [ ] Update test.galaxyproject.org to ensure it is running a dev at or past branch point (${freeze_date} + 1 day).
    - [ ] Update testtoolshed.g2.bx.psu.edu to ensure it is running a dev at or past branch point (${freeze_date} + 1 day).
    - [ ] Deploy to usegalaxy.org (${freeze_date} + 1 week).
    - [ ] Deploy to toolshed.g2.bx.psu.edu (${freeze_date} + 1 week).
    - [ ] [Update BioBlend CI testing](https://github.com/galaxyproject/bioblend/blob/main/.github/workflows/test.yaml) to include a ``release_${version}`` target: add ``- release_${version}`` to the ``galaxy_version`` list in ``.github/workflows/test.yaml`` .
    - [ ] Update GALAXY_RELEASE in IUC and devteam github workflows
        - [ ] https://github.com/galaxyproject/tools-iuc/blob/master/.github/workflows/
        - [ ] https://github.com/galaxyproject/tools-devteam/blob/master/.github/workflows/

- [ ] **Create Release Notes**

    - [ ] Review merged PRs and ensure they all have a milestones attached. [Link](https://github.com/galaxyproject/galaxy/pulls?utf8=%E2%9C%93&q=is%3Apr+is%3Amerged+no%3Amilestone+-label%3Amerge+)
    - [ ] Checkout release branch

          git checkout release_${version} -b ${version}_release_notes
    - [ ] Bootstrap the release notes

          make release-bootstrap-history RELEASE_CURR=${version}
    - [ ] Open newly created files and manually curate major topics and release notes.
    - [ ] Run ``python scripts/release-diff.py release_${previous_version}`` and add configuration changes to release notes.
    - [ ] Add new release to doc/source/releases/index.rst
    - [ ] Commit release notes.

          git add docs/; git commit -m "Release notes for $version"; git push upstream ${version}_release_notes
    - [ ] Open a pull request for new release note branch.
    - [ ] Merge release note pull request.

- [ ] **Do Release**

    - [ ] Ensure all [blocking milestone issues](https://github.com/galaxyproject/galaxy/issues?q=is%3Aopen+is%3Aissue+milestone%3A${version}) have been resolved.

          make release-check-blocking-issues RELEASE_CURR=${version}
    - [ ] Ensure all [blocking milestone PRs](https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+milestone%3A${version}) have been merged or closed.

          make release-check-blocking-prs RELEASE_CURR=${version}
    - [ ] Ensure all PRs merged into the pre-release branch during the freeze have [milestones attached](https://github.com/galaxyproject/galaxy/pulls?q=is%3Apr+is%3Aclosed+base%3Arelease_${version}+is%3Amerged+no%3Amilestone) and that they are the not [${next_version} milestones](https://github.com/galaxyproject/galaxy/pulls?q=is%3Apr+is%3Aclosed+base%3Arelease_${version}+is%3Amerged+milestone%3A${next_version})
    - [ ] Ensure release notes include all PRs added during the freeze by re-running the release note bootstrapping:

          make release-bootstrap-history
    - [ ] Ensure previous release is merged into current. [GitHub branch comparison](https://github.com/galaxyproject/galaxy/compare/release_${version}...release_${previous_version})
    - [ ] Create and push release tag:

          make release-create

    - [ ] Create dev packages:

          cd packages && ./build_packages.sh

    - [ ] Create the first point release (v${version}.0) using the instructions at https://docs.galaxyproject.org/en/master/dev/create_release.html
    - [ ] Open PR against planemo with a pin to the new packages

- [ ] **Do Docker Release**

    - [ ] Change the [dev branch](https://github.com/bgruening/docker-galaxy-stable/tree/dev) of the Galaxy Docker container to ${next_version}
    - [ ] Merge dev into master

- [ ] **Announce Release**

    - [ ] Verify release included in https://docs.galaxyproject.org/en/master/releases/index.html
    - [ ] Review announcement in https://github.com/galaxyproject/galaxy/blob/dev/doc/source/releases/${version}_announce.rst
    - [ ] Stage announcement content (Hub, Galaxy Help, etc.) on announce date to capture date tags. Note: all final content does not need to be completed to do this.
    - [ ] Create hub *highlights* and post as a new "news" content item. [An example](https://galaxyproject.org/news/2018-9-galaxy-release/).
    - [ ] Tweet docs news *highlights* link as @galaxyproject on twitter. [An example](https://twitter.com/galaxyproject/status/973646125633695744).
    - [ ] Post *highlights* with tags `news` and `release` to [Galaxy Help](https://help.galaxyproject.org/). [An example](https://help.galaxyproject.org/t/galaxy-release-19-01/712).
    - [ ] Email *highlights* to [galaxy-dev](http://dev.list.galaxyproject.org/) and [galaxy-announce](http://announce.list.galaxyproject.org/) @lists.galaxyproject.org. [An example](http://dev.list.galaxyproject.org/The-Galaxy-release-16-04-is-out-tp4669419.html)
    - [ ] Adjust http://getgalaxy.org text and links to match current master branch by opening a PR at https://github.com/galaxyproject/galaxy-hub/

- [ ] **Prepare for next release**

    - [ ] Close milestone ``${version}`` and ensure milestone ``${next_version}`` exists.
    - [ ] Create release issue for next version ``make release-issue``.
    - [ ] Schedule committer meeting to discuss re-alignment of priorities.
    - [ ] Close this issue.
"""  # noqa: E501
)

release_version_argument = click.argument("release-version", type=ClickVersion())


@click.group(help="Subcommands of this script can perform various tasks around creating Galaxy releases")
def cli():
    pass


@cli.command(help="Create release checklist issue on GitHub")
@group_options(release_version_argument, galaxy_root_option)
def create_release_issue(release_version: Version, galaxy_root: Path):
    previous_release = _previous_release(galaxy_root, release_version)
    new_version_params = _next_version_params(release_version)
    next_version = new_version_params["version"]
    freeze_date, _ = _release_dates(release_version)
    release_issue_template_params = dict(
        version=release_version,
        next_version=next_version,
        previous_version=previous_release,
        freeze_date=freeze_date,
    )
    release_issue_contents = RELEASE_ISSUE_TEMPLATE.safe_substitute(**release_issue_template_params)
    github = github_client()
    repo = github.get_repo(f"{PROJECT_OWNER}/{PROJECT_NAME}")
    release_issue = repo.create_issue(
        title=f"Publication of Galaxy Release v {release_version}",
        body=release_issue_contents,
    )
    return release_issue


@cli.command(help="Create or update release changelog")
@group_options(release_version_argument, galaxy_root_option)
def create_changelog(release_version: Version, galaxy_root: Path):
    release_file = _release_file(galaxy_root, str(release_version) + ".rst")
    enhancement_targets = "\n\n".join(f".. enhancement_tag_{a}" for a in GROUPED_TAGS.values())
    bug_targets = "\n\n".join(f".. bug_tag_{a}" for a in GROUPED_TAGS.values())
    template = TEMPLATE
    template = template.replace(".. enhancement", f"{enhancement_targets}\n\n.. enhancement")
    template = template.replace(".. bug", f"{bug_targets}\n\n.. bug")
    release_info = string.Template(template).safe_substitute(release=release_version)
    _write_file(release_file, release_info, skip_if_exists=True)
    month = MINOR_TO_MONTH[release_version.minor]
    month_name = calendar.month_name[month]
    year = release_version.major

    announce_info = ANNOUNCE_TEMPLATE.substitute(month_name=month_name, year=year, release=release_version)
    announce_file = _release_file(galaxy_root, str(release_version) + "_announce.rst")
    _write_file(announce_file, announce_info, skip_if_exists=True)

    announce_user_info = ANNOUNCE_USER_TEMPLATE.substitute(month_name=month_name, year=year, release=release_version)
    announce_user_file = _release_file(galaxy_root, str(release_version) + "_announce_user.rst")
    _write_file(announce_user_file, announce_user_info, skip_if_exists=True)

    prs_file = _release_file(galaxy_root, str(release_version) + "_prs.rst")
    seen_prs = set()
    try:
        with open(prs_file) as fh:
            seen_prs = set(map(int, re.findall(r"\.\. _Pull Request (\d+): https", fh.read())))
    except FileNotFoundError:
        pass
    _write_file(prs_file, PRS_TEMPLATE, skip_if_exists=True)

    next_version_params = _next_version_params(release_version)
    next_version = next_version_params["version"]
    next_release_file = _release_file(galaxy_root, str(next_version) + "_announce.rst")

    next_announce = NEXT_TEMPLATE.substitute(**next_version_params)
    with open(next_release_file, "w") as fh:
        fh.write(next_announce)
    releases_index = _release_file(galaxy_root, "index.rst")
    releases_index_contents = _read_file(releases_index)
    releases_index_contents = releases_index_contents.replace(
        ".. announcements\n",
        ".. announcements\n   " + str(next_version) + "_announce\n",
    )
    _write_file(releases_index, releases_index_contents, skip_if_exists=True)

    for pr in _get_prs(str(release_version)):
        if pr.number not in seen_prs:
            pr_to_doc(
                galaxy_root=galaxy_root,
                release_version=release_version,
                pr=pr,
            )


@cli.command(help="List release blocking PRs")
@group_options(release_version_argument)
def check_blocking_prs(release_version: Version):
    block = False
    for pr in _get_prs(str(release_version), state="open"):
        click.echo(f"Blocking PR| {_pr_to_str(pr)}", err=True)
        block = True
    if block:
        sys.exit(1)


@cli.command(help="List release blocking issues")
@group_options(release_version_argument)
def check_blocking_issues(release_version: Version):
    block = 0
    github = github_client()
    repo = github.get_repo(f"{PROJECT_OWNER}/{PROJECT_NAME}")
    issues = repo.get_issues(state="open")
    for issue in issues:
        # issue can also be a pull request, which could be filtered out with `not issue.pull_request`
        if (
            issue.milestone
            and issue.milestone.title == str(release_version)
            and "Publication of Galaxy Release" not in issue.title
        ):
            click.echo(f"Blocking issue| {_issue_to_str(issue)}", err=True)
            block = 1

    sys.exit(block)


def _issue_to_str(pr):
    if isinstance(pr, str):
        return pr
    return f"Issue #{pr.number} ({pr.title}) {pr.html_url}"


def _next_version_params(release_version: Version):
    # we'll just hardcode this to 3 "minor" versions per year
    if release_version.minor < 2:
        next_major = release_version.major
        next_minor = release_version.minor + 1
    else:
        next_major = release_version.major + 1
        next_minor = 0
    next_month_name = calendar.month_name[MINOR_TO_MONTH[next_minor]]
    next_version = Version(f"{next_major}.{next_minor}")
    freeze_date, release_date = _release_dates(next_version)
    return dict(
        version=next_version,
        year=next_major,
        month_name=next_month_name,
        freeze_date=freeze_date,
        release_date=release_date,
    )


def _release_dates(version: Version):
    # hardcoded to 3 releases a year, freeze dates kind of random
    year = version.major
    month = MINOR_TO_MONTH[version.minor]
    first_of_month = datetime.date(year + 2000, month, 1)
    freeze_date = next_weekday(first_of_month, 0)
    release_date = next_weekday(first_of_month, 0) + datetime.timedelta(21)
    return freeze_date, release_date


def _get_prs(release_version: str, state="closed"):
    github = github_client()
    repo = github.get_repo(f"{PROJECT_OWNER}/{PROJECT_NAME}")
    pull_requests = repo.get_pulls(state=state)
    reached_old_prs = False

    for pr in pull_requests:
        if reached_old_prs:
            break

        if pr.created_at.replace(tzinfo=None) < datetime.datetime(2020, 5, 1, 0, 0):
            reached_old_prs = True
            pass
        merged_at = pr.merged_at
        milestone = pr.milestone
        proper_state = state != "closed" or merged_at
        if not proper_state or not milestone or milestone.title != release_version:
            continue
        yield pr


def pr_to_doc(galaxy_root: Path, release_version: Version, pr: PullRequest):
    history_path = _release_file(galaxy_root, str(release_version)) + ".rst"
    user_announce_path = history_path[0 : -len(".rst")] + "_announce_user.rst"
    prs_path = history_path[0 : -len(".rst")] + "_prs.rst"

    history = _read_file(history_path)
    user_announce = _read_file(user_announce_path)
    prs_content = _read_file(prs_path)

    def extend_target(target, line, source=history):
        from_str = f".. {target}\n"
        if target not in source:
            raise Exception(f"Failed to find target [{target}] in source [{source}]")
        return source.replace(from_str, from_str + line + "\n")

    text_target = "to_doc"
    to_doc = pr.title.rstrip(".") + " "

    owner = None
    user = pr.user
    owner = user.login
    text = f".. _Pull Request {pr.number}: {PROJECT_URL}/pull/{pr.number}"
    prs_content = extend_target("github_links", text, prs_content)
    to_doc += f"\n(thanks to `@{owner} <https://github.com/{owner}>`__)."
    to_doc += f"\n`Pull Request {pr.number}`_"
    labels = _pr_to_labels(pr)
    text_target = _text_target(pr)

    to_doc = wrap(to_doc)
    if text_target is not None:
        history = extend_target(text_target, to_doc, history)
    if "area/datatypes" in labels:
        user_announce = extend_target("datatypes", to_doc, user_announce)
    if "area/visualizations" in labels:
        user_announce = extend_target("visualizations", to_doc, user_announce)
    if "area/tools" in labels:
        user_announce = extend_target("tools", to_doc, user_announce)
    _write_file(history_path, history)
    _write_file(prs_path, prs_content)
    _write_file(user_announce_path, user_announce)


def _read_file(path):
    with open(path) as f:
        return f.read()


def _write_file(path, contents, skip_if_exists=False):
    if skip_if_exists and os.path.exists(path):
        return
    with open(path, "w") as f:
        f.write(contents)


def _previous_release(galaxy_root, to: Version):
    previous_release = None
    for release in _releases(galaxy_root):
        if release == str(to):
            break

        previous_release = release

    return previous_release


def _releases(galaxy_root):
    releases_path = galaxy_root / "doc" / "source" / "releases"
    all_files = sorted(os.listdir(releases_path))
    release_note_file_pattern = re.compile(r"\d+\.\d+.rst")
    release_note_files = [f for f in all_files if release_note_file_pattern.match(f)]
    return sorted(f.rstrip(".rst") for f in release_note_files)


def _release_file(galaxy_root: Path, release: Optional[str]) -> str:
    releases_path = galaxy_root / "doc" / "source" / "releases"
    if release is None:
        release = sorted(os.listdir(releases_path))[-1]
    history_path = os.path.join(releases_path, release)
    return history_path


def get_first_sentence(message: str) -> str:
    first_line = message.split("\n")[0]
    return first_line


def process_sentence(message):
    # Strip tags like [15.07].
    message = strip_release(message=message)
    # Link issues and pull requests...
    issue_url = f"https://github.com/{PROJECT_OWNER}/{PROJECT_NAME}/issues"
    message = re.sub(r"#(\d+)", rf"`#\1 <{issue_url}/\1>`__", message)
    return message


def wrap(message):
    message = process_sentence(message)
    wrapper = textwrap.TextWrapper(initial_indent="* ")
    wrapper.subsequent_indent = "  "
    wrapper.width = 160
    message_lines = message.splitlines()
    first_lines = "\n".join(wrapper.wrap(message_lines[0]))
    wrapper.initial_indent = "  "
    rest_lines = "\n".join("\n".join(wrapper.wrap(m)) for m in message_lines[1:])
    return first_lines + ("\n" + rest_lines if rest_lines else "")


def next_weekday(d, weekday):
    """Return the next week day (0 for Monday, 6 for Sunday) starting from ``d``."""
    days_ahead = weekday - d.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return d + datetime.timedelta(days_ahead)
