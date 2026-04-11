from pathlib import Path
from unittest.mock import MagicMock, patch

from packaging.version import Version

from galaxy_release_util.snapshot_release import (
    CANONICAL_OWNER,
    CANONICAL_REPO,
    SNAPSHOT_TAG_PREFIX,
    find_canonical_upstream,
    find_last_snapshot_tag,
)


class TestFindCanonicalUpstream:
    def _mock_remotes(self, output):
        return patch(
            "galaxy_release_util.snapshot_release.subprocess.run",
            return_value=MagicMock(
                stdout=output, returncode=0, check_returncode=lambda: None,
            ),
        )

    def test_ssh_remote(self):
        remotes = "origin\tgit@github.com:guerler/galaxy.git (fetch)\nupstream\tgit@github.com:galaxyproject/galaxy.git (fetch)\n"
        with self._mock_remotes(remotes):
            assert find_canonical_upstream(Path("/fake")) == "git@github.com:galaxyproject/galaxy.git"

    def test_https_remote(self):
        remotes = "upstream\thttps://github.com/galaxyproject/galaxy.git (fetch)\n"
        with self._mock_remotes(remotes):
            assert find_canonical_upstream(Path("/fake")) == "https://github.com/galaxyproject/galaxy.git"

    def test_https_no_git_suffix(self):
        remotes = "upstream\thttps://github.com/galaxyproject/galaxy (fetch)\n"
        with self._mock_remotes(remotes):
            assert find_canonical_upstream(Path("/fake")) == "https://github.com/galaxyproject/galaxy"

    def test_case_insensitive(self):
        remotes = "upstream\thttps://github.com/GalaxyProject/Galaxy.git (fetch)\n"
        with self._mock_remotes(remotes):
            assert find_canonical_upstream(Path("/fake")) == "https://github.com/GalaxyProject/Galaxy.git"

    def test_no_match_returns_fallback(self):
        remotes = "origin\tgit@github.com:guerler/galaxy.git (fetch)\n"
        with self._mock_remotes(remotes):
            url = find_canonical_upstream(Path("/fake"))
            assert url == "https://github.com/galaxyproject/galaxy.git"

    def test_ignores_push_lines(self):
        remotes = (
            "upstream\tgit@github.com:guerler/galaxy.git (fetch)\n"
            "upstream\tgit@github.com:galaxyproject/galaxy.git (push)\n"
        )
        with self._mock_remotes(remotes):
            # Should not match the push line, should fall back
            url = find_canonical_upstream(Path("/fake"))
            assert url == "https://github.com/galaxyproject/galaxy.git"


class TestFindLastSnapshotTag:
    def _mock_tags(self, output):
        return patch(
            "galaxy_release_util.snapshot_release.subprocess.run",
            return_value=MagicMock(
                stdout=output, returncode=0, check_returncode=lambda: None,
            ),
        )

    def test_finds_latest(self):
        tags = "snapshot-v25.1.dev20260411\nsnapshot-v25.1.dev20260301\n"
        with self._mock_tags(tags):
            result = find_last_snapshot_tag(Path("/fake"), "25.1")
            assert result == "snapshot-v25.1.dev20260411"

    def test_returns_none_when_empty(self):
        with self._mock_tags(""):
            result = find_last_snapshot_tag(Path("/fake"), "25.1")
            assert result is None

    def test_ignores_official_tags(self):
        """Official v* tags should never appear because the --list pattern only matches snapshot-v*."""
        # This test verifies the git command uses the correct prefix pattern.
        # The mock returns only what git would return for "snapshot-v25.1.*"
        with self._mock_tags("") as mock_run:
            find_last_snapshot_tag(Path("/fake"), "25.1")
            call_args = mock_run.call_args[0][0]
            # Verify the --list pattern includes the snapshot prefix
            assert f"{SNAPSHOT_TAG_PREFIX}25.1.*" in call_args
            assert "--merged" in call_args
            assert "HEAD" in call_args


class TestVersionComputation:
    def test_from_point_release(self):
        root = Version("25.1.2")
        major_minor = f"{root.major}.{root.minor}"
        date_str = "20260411"
        snapshot = Version(f"{major_minor}.dev{date_str}")
        assert str(snapshot) == "25.1.dev20260411"
        assert snapshot < Version("25.1.0")

    def test_from_dev_release(self):
        root = Version("26.0.dev0")
        major_minor = f"{root.major}.{root.minor}"
        date_str = "20260411"
        snapshot = Version(f"{major_minor}.dev{date_str}")
        assert str(snapshot) == "26.0.dev20260411"

    def test_from_major_minor_only(self):
        root = Version("26.0")
        major_minor = f"{root.major}.{root.minor}"
        date_str = "20260411"
        snapshot = Version(f"{major_minor}.dev{date_str}")
        assert str(snapshot) == "26.0.dev20260411"

    def test_sorts_before_official(self):
        snapshot = Version("25.1.dev20260411")
        official = Version("25.1.0")
        assert snapshot < official


class TestSafetyChecks:
    """Test safety checks via the CLI command."""

    def test_refuse_galaxyproject_owner(self, monkeypatch, tmp_path):
        from click.testing import CliRunner
        from galaxy_release_util.snapshot_release import cli

        monkeypatch.setattr("galaxy_release_util.snapshot_release.verify_galaxy_root", lambda x: None)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.is_git_clean", lambda x: True)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.get_current_branch", lambda x: "dev")
        monkeypatch.setattr("galaxy_release_util.snapshot_release.get_root_version", lambda x: Version("25.1.2"))
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.load_repo_owner",
            lambda *a, **kw: (CANONICAL_OWNER, CANONICAL_REPO),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["create-release-snapshot", "--galaxy-root", str(tmp_path)])
        assert result.exit_code != 0
        assert "must not target the official galaxyproject/galaxy" in result.output

    def test_refuse_non_dev_branch(self, monkeypatch, tmp_path):
        from click.testing import CliRunner
        from galaxy_release_util.snapshot_release import cli

        monkeypatch.setattr("galaxy_release_util.snapshot_release.verify_galaxy_root", lambda x: None)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.is_git_clean", lambda x: True)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.get_current_branch", lambda x: "release_25.1")

        runner = CliRunner()
        result = runner.invoke(cli, ["create-release-snapshot", "--galaxy-root", str(tmp_path)])
        assert result.exit_code != 0
        assert "must be created on the 'dev' branch" in result.output

    def test_refuse_dirty_tree(self, monkeypatch, tmp_path):
        from click.testing import CliRunner
        from galaxy_release_util.snapshot_release import cli

        monkeypatch.setattr("galaxy_release_util.snapshot_release.verify_galaxy_root", lambda x: None)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.is_git_clean", lambda x: False)

        runner = CliRunner()
        result = runner.invoke(cli, ["create-release-snapshot", "--galaxy-root", str(tmp_path)])
        assert result.exit_code != 0
        assert "not clean" in result.output

    def test_refuse_duplicate_local_tag(self, monkeypatch, tmp_path):
        from click.testing import CliRunner
        from galaxy_release_util.snapshot_release import cli

        monkeypatch.setattr("galaxy_release_util.snapshot_release.verify_galaxy_root", lambda x: None)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.is_git_clean", lambda x: True)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.get_current_branch", lambda x: "dev")
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.load_repo_owner",
            lambda *a, **kw: ("myuser", "mygalaxy"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.get_root_version",
            lambda x: Version("25.1.2"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release._tag_exists_locally",
            lambda gx, tag: True,
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["create-release-snapshot", "--galaxy-root", str(tmp_path)])
        assert result.exit_code != 0
        assert "already exists locally" in result.output

    def test_refuse_duplicate_remote_tag(self, monkeypatch, tmp_path):
        from click.testing import CliRunner
        from galaxy_release_util.snapshot_release import cli

        monkeypatch.setattr("galaxy_release_util.snapshot_release.verify_galaxy_root", lambda x: None)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.is_git_clean", lambda x: True)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.get_current_branch", lambda x: "dev")
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.load_repo_owner",
            lambda *a, **kw: ("myuser", "mygalaxy"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.get_root_version",
            lambda x: Version("25.1.2"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release._tag_exists_locally",
            lambda gx, tag: False,
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release._tag_exists_on_remote",
            lambda gx, remote, tag: True,
        )

        runner = CliRunner()
        result = runner.invoke(cli, [
            "create-release-snapshot", "--galaxy-root", str(tmp_path),
            "--push-remote", "git@github.com:myuser/galaxy.git",
        ])
        assert result.exit_code != 0
        assert "already exists on remote" in result.output
