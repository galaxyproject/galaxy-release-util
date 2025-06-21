import subprocess
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from galaxy_release_util.point_release import (
    build,
    get_sorted_package_paths,
)


@pytest.fixture(scope="module")
def galaxy_repo():
    """Clone the Galaxy repository to a temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Clone Galaxy repository (shallow clone to save time)
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/galaxyproject/galaxy.git", str(temp_path)], check=True
        )

        # Make sure the expected structure exists
        packages_dir = temp_path / "packages"
        assert packages_dir.exists(), "Galaxy packages directory not found"

        yield temp_path


def test_build_integration(galaxy_repo):
    """Integration test for building all packages using a real Galaxy repository.

    This test:
    1. Clones the Galaxy repository
    2. Builds all packages
    3. Verifies that build artifacts are created for each package
    """
    galaxy_root = galaxy_repo

    # Get all package paths
    package_paths = get_sorted_package_paths(galaxy_root)
    assert len(package_paths) > 0, "No packages found"
    result = CliRunner().invoke(build, ["--galaxy-root", str(galaxy_root)])
    assert result.exit_code == 0, f"Build command failed: {result.output}"

    # Build all packages
    for package_path in package_paths:
        dist_dir = package_path / "dist"
        # Verify that build artifacts were created
        assert dist_dir.exists()

        # Verify that at least one build artifact was created (either .tar.gz or .whl)
        assert dist_dir.glob("*.whl")
        assert dist_dir.glob("*.tar.gz")
