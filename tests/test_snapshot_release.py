from pathlib import Path
from unittest.mock import MagicMock, patch

from packaging.version import Version

from galaxy_release_util.snapshot_release import (
    CANONICAL_OWNER,
    CANONICAL_REPO,
    SNAPSHOT_TAG_PREFIX,
    _url_points_to_canonical,
    find_canonical_upstream,
    find_last_snapshot_tag,
)


class TestFindCanonicalUpstream:
    """find_canonical_upstream enumerates remote names via `git remote` and then
    calls `git remote get-url <name>` for each. These tests simulate that sequence.
    """

    def _mock_sequence(self, remote_map):
        """Create a fake subprocess.run that handles `git remote` and `git remote get-url <name>`.

        remote_map: dict of {remote_name: fetch_url}
        """
        def fake_run(cmd, **kwargs):
            if cmd == ["git", "remote"]:
                output = "\n".join(remote_map.keys()) + "\n" if remote_map else ""
                return MagicMock(stdout=output, returncode=0, check_returncode=lambda: None)
            if len(cmd) >= 4 and cmd[0] == "git" and cmd[1] == "remote" and cmd[2] == "get-url":
                # Could be ["git", "remote", "get-url", name] or ["git", "remote", "get-url", "--push", name]
                name = cmd[-1]
                if name in remote_map:
                    return MagicMock(stdout=remote_map[name] + "\n", returncode=0)
                return MagicMock(stdout="", returncode=1, stderr="no such remote")
            return MagicMock(stdout="", returncode=0, check_returncode=lambda: None)

        return patch("galaxy_release_util.snapshot_release.subprocess.run", side_effect=fake_run)

    def test_ssh_remote(self):
        with self._mock_sequence({
            "origin": "git@github.com:guerler/galaxy.git",
            "upstream": "git@github.com:galaxyproject/galaxy.git",
        }):
            assert find_canonical_upstream(Path("/fake")) == "git@github.com:galaxyproject/galaxy.git"

    def test_https_remote(self):
        with self._mock_sequence({"upstream": "https://github.com/galaxyproject/galaxy.git"}):
            assert find_canonical_upstream(Path("/fake")) == "https://github.com/galaxyproject/galaxy.git"

    def test_https_no_git_suffix(self):
        with self._mock_sequence({"upstream": "https://github.com/galaxyproject/galaxy"}):
            assert find_canonical_upstream(Path("/fake")) == "https://github.com/galaxyproject/galaxy"

    def test_case_insensitive(self):
        with self._mock_sequence({"upstream": "https://github.com/GalaxyProject/Galaxy.git"}):
            assert find_canonical_upstream(Path("/fake")) == "https://github.com/GalaxyProject/Galaxy.git"

    def test_no_match_returns_fallback(self):
        with self._mock_sequence({"origin": "git@github.com:guerler/galaxy.git"}):
            assert find_canonical_upstream(Path("/fake")) == "https://github.com/galaxyproject/galaxy.git"

    def test_no_remotes_returns_fallback(self):
        with self._mock_sequence({}):
            assert find_canonical_upstream(Path("/fake")) == "https://github.com/galaxyproject/galaxy.git"


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


class TestUrlPointsToCanonical:
    def test_ssh_canonical(self):
        assert _url_points_to_canonical("git@github.com:galaxyproject/galaxy.git")

    def test_ssh_canonical_no_suffix(self):
        assert _url_points_to_canonical("git@github.com:galaxyproject/galaxy")

    def test_https_canonical(self):
        assert _url_points_to_canonical("https://github.com/galaxyproject/galaxy.git")

    def test_https_canonical_no_suffix(self):
        assert _url_points_to_canonical("https://github.com/galaxyproject/galaxy")

    def test_https_canonical_trailing_slash(self):
        assert _url_points_to_canonical("https://github.com/galaxyproject/galaxy/")

    def test_case_insensitive(self):
        assert _url_points_to_canonical("git@github.com:GalaxyProject/Galaxy.git")

    def test_fork_not_canonical(self):
        assert not _url_points_to_canonical("git@github.com:guerler/galaxy.git")

    def test_different_repo_not_canonical(self):
        assert not _url_points_to_canonical("git@github.com:galaxyproject/galaxy-hub.git")

    def test_unrelated_url_not_canonical(self):
        assert not _url_points_to_canonical("https://example.com/something/else.git")


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

    def test_refuse_push_remote_pointing_to_canonical(self, monkeypatch, tmp_path):
        """Explicit --push-remote pointing at canonical galaxyproject/galaxy must be refused."""
        from click.testing import CliRunner
        from galaxy_release_util.snapshot_release import cli

        monkeypatch.setattr("galaxy_release_util.snapshot_release.verify_galaxy_root", lambda x: None)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.is_git_clean", lambda x: True)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.get_current_branch", lambda x: "dev")
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.get_root_version",
            lambda x: Version("25.1.2"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.load_repo_owner",
            lambda *a, **kw: ("myuser", "mygalaxy"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release._tag_exists_locally",
            lambda gx, tag: False,
        )
        # Simulate the override path: user explicitly points --push-remote at canonical
        runner = CliRunner()
        result = runner.invoke(cli, [
            "create-release-snapshot",
            "--galaxy-root", str(tmp_path),
            "--push-remote", "git@github.com:galaxyproject/galaxy.git",
        ])
        assert result.exit_code != 0
        assert "resolves to the canonical" in result.output
        assert "galaxyproject/galaxy" in result.output

    def test_refuse_push_remote_name_resolving_to_canonical(self, monkeypatch, tmp_path):
        """--push-remote using a remote name that resolves to canonical must be refused."""
        from click.testing import CliRunner
        from galaxy_release_util.snapshot_release import cli

        monkeypatch.setattr("galaxy_release_util.snapshot_release.verify_galaxy_root", lambda x: None)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.is_git_clean", lambda x: True)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.get_current_branch", lambda x: "dev")
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.get_root_version",
            lambda x: Version("25.1.2"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.load_repo_owner",
            lambda *a, **kw: ("myuser", "mygalaxy"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release._tag_exists_locally",
            lambda gx, tag: False,
        )
        # Simulate `git remote get-url upstream` resolving to canonical
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release._resolve_push_remote_url",
            lambda gx, name: "git@github.com:galaxyproject/galaxy.git",
        )
        runner = CliRunner()
        result = runner.invoke(cli, [
            "create-release-snapshot",
            "--galaxy-root", str(tmp_path),
            "--push-remote", "upstream",
        ])
        assert result.exit_code != 0
        assert "resolves to the canonical" in result.output

    def test_refuse_push_remote_with_divergent_pushurl(self, monkeypatch, tmp_path):
        """A remote whose fetch URL is safe but pushurl points to canonical must be refused.

        This is the dangerous divergence case: `git remote get-url <remote>` (without --push)
        would return the safe fetch URL, but `git push <remote>` would dispatch to the
        canonical push URL. The safety check must use the push URL.
        """
        from click.testing import CliRunner
        from galaxy_release_util.snapshot_release import cli

        monkeypatch.setattr("galaxy_release_util.snapshot_release.verify_galaxy_root", lambda x: None)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.is_git_clean", lambda x: True)
        monkeypatch.setattr("galaxy_release_util.snapshot_release.get_current_branch", lambda x: "dev")
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.get_root_version",
            lambda x: Version("25.1.2"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release.load_repo_owner",
            lambda *a, **kw: ("myuser", "mygalaxy"),
        )
        monkeypatch.setattr(
            "galaxy_release_util.snapshot_release._tag_exists_locally",
            lambda gx, tag: False,
        )

        # Simulate subprocess: `git remote get-url --push origin` returns canonical URL.
        # This is what a remote with `pushurl = git@github.com:galaxyproject/galaxy.git` would produce.
        def fake_run(cmd, **kwargs):
            if cmd[:4] == ["git", "remote", "get-url", "--push"]:
                return MagicMock(
                    returncode=0,
                    stdout="git@github.com:galaxyproject/galaxy.git\n",
                    stderr="",
                )
            return MagicMock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr("galaxy_release_util.snapshot_release.subprocess.run", fake_run)

        runner = CliRunner()
        result = runner.invoke(cli, [
            "create-release-snapshot",
            "--galaxy-root", str(tmp_path),
            "--push-remote", "origin",
        ])
        assert result.exit_code != 0
        assert "resolves to the canonical" in result.output

    def test_resolver_uses_push_url_flag(self, monkeypatch, tmp_path):
        """Verify the resolver calls `git remote get-url --push`, not the bare form.

        This is a regression test for the fetch-vs-push URL safety bug.
        """
        from galaxy_release_util.snapshot_release import _resolve_push_remote_url

        captured_cmds = []

        def fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            return MagicMock(returncode=0, stdout="git@github.com:guerler/galaxy.git\n")

        monkeypatch.setattr("galaxy_release_util.snapshot_release.subprocess.run", fake_run)
        _resolve_push_remote_url(tmp_path, "origin")

        assert len(captured_cmds) == 1
        assert captured_cmds[0] == ["git", "remote", "get-url", "--push", "origin"]

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
