import os
import pathlib


def verify_galaxy_root(galaxy_root: pathlib.Path):
    version_file = pathlib.Path(galaxy_root / "lib" / "galaxy" / "version.py")
    if not os.path.exists(version_file):
        msg = f"Galaxy files not found at `{galaxy_root}`. If you are running this script outside of galaxy root directory, you should specify the '--galaxy-root' argument"
        raise Exception(msg)
