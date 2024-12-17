import os
from pathlib import Path


def version_filepath(galaxy_root: Path) -> Path:
    return Path(galaxy_root / "lib" / "galaxy" / "version.py")


def verify_galaxy_root(galaxy_root: Path):
    if not os.path.exists(version_filepath(galaxy_root)):
        msg = f"Galaxy files not found at `{galaxy_root}`. If you are running this script outside of galaxy root directory, you should specify the '--galaxy-root' argument"
        raise Exception(msg)
