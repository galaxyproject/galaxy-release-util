import os
import re
from pathlib import Path

_RST_INLINE_MARKUP_RE = re.compile(r"([`*|\\])")


def escape_rst_inline(text: str) -> str:
    """Escape characters that have special meaning in RST inline markup."""
    return _RST_INLINE_MARKUP_RE.sub(r"\\\1", text)


def version_filepath(galaxy_root: Path) -> Path:
    package_init = Path(galaxy_root / "lib" / "galaxy" / "version" / "__init__.py")
    if package_init.exists():
        return package_init
    return Path(galaxy_root / "lib" / "galaxy" / "version.py")


def verify_galaxy_root(galaxy_root: Path):
    if not os.path.exists(version_filepath(galaxy_root)):
        msg = f"Galaxy files not found at `{galaxy_root}`. If you are running this script outside of galaxy root directory, you should specify the '--galaxy-root' argument"
        raise Exception(msg)
