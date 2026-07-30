import datetime
import pathlib
from typing import (
    Any,
    Optional,
)

import click
from click.core import (
    Context,
    Parameter,
)
from packaging.version import Version

galaxy_root_option = click.option(
    "--galaxy-root",
    type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=pathlib.Path),
    default=".",
    help="Path to galaxy root.",
)


def group_options(*options):
    def wrapper(function):
        for option in reversed(options):
            function = option(function)
        return function

    return wrapper


class ClickVersion(click.ParamType):
    name = "pep440 version"

    def convert(self, value: Any, param: Optional[Parameter], ctx: Optional[Context]) -> Version:
        try:
            return Version(value)
        except ValueError as e:
            self.fail(f"{value!r} is not a valid PEP440 version number: {str(e)}", param, ctx)


class ClickDate(click.ParamType):
    name = "date"

    def convert(self, value: Any, param: Optional[Parameter], ctx: Optional[Context]) -> datetime.date:
        try:
            return datetime.datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as e:
            self.fail(f"{value!r} is not a valid date: {str(e)}", param, ctx)


owner_option = click.option(
    "--owner",
    default="galaxyproject",
    show_default=True,
    help="GitHub organization or user owning the repository. Set when working against a fork.",
)

repo_option = click.option(
    "--repo",
    default="galaxy",
    show_default=True,
    help="GitHub repository name. Set when working against a fork.",
)

previous_version_option = click.option(
    "--previous-version",
    type=ClickVersion(),
    default=None,
    help="Previous release version. Defaults to the newest milestone preceding the release version.",
)

next_version_option = click.option(
    "--next-version",
    type=ClickVersion(),
    default=None,
    help="Next planned release version. Defaults to the oldest milestone following the release version.",
)

release_date_option = click.option(
    "--release-date",
    type=ClickDate(),
    default=None,
    help="Release date in YYYY-MM-DD format. Defaults to the due date of the release version's milestone.",
)

freeze_date_option = click.option(
    "--freeze-date",
    type=ClickDate(),
    default=None,
    help="Freeze date in YYYY-MM-DD format. Not derivable from milestones, so it must be supplied.",
)
