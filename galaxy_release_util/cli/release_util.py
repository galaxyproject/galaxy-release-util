import click

from ..bootstrap_history import cli as boostrap_cli
from ..point_release import cli as point_release_cli

cli = click.CommandCollection(
    sources=[boostrap_cli, point_release_cli],
    help="Perform various tasks around creating Galaxy releases and point releases",
)
