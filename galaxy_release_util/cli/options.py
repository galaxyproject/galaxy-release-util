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
        except Exception as e:
            self.fail(f"{value!r} is not a valid PEP440 version number: {str(e)}", param, ctx)
