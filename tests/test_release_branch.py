import subprocess

import click
import pytest
from click.testing import CliRunner
from conftest import (
    client_version,
    commit_all,
    git,
    locked_versions,
    package_versions,
    root_version,
    uv_lock,
    write_versions,
)
from packaging.version import Version

from galaxy_release_util import release_branch
from galaxy_release_util.release_branch import create_release_branch


@pytest.fixture(autouse=True)
def milestones(monkeypatch):
    """Upstream milestones as they were when 26.2 was branched: the release after 26.2 is 27.0."""
    due_dates = {Version("26.1"): None, Version("26.2"): None, Version("27.0"): None, Version("27.1"): None}
    monkeypatch.setattr(release_branch, "milestone_due_dates", lambda owner, repo: due_dates)
    return due_dates


def run(galaxy_clone, *args, input=None):
    return CliRunner().invoke(
        create_release_branch, ["--galaxy-root", str(galaxy_clone), *args], input=input, catch_exceptions=False
    )


def remote_branches(repo):
    return set(git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split())


class TestInitialReleaseCandidate:
    def test_creates_release_branch_and_version_branches(self, galaxy_clone, upstream_repo, fork_repo):
        dev = git(upstream_repo, "rev-parse", "dev")
        # an untracked file must not end up in a commit
        (galaxy_clone / "packages" / "untracked.txt").write_text("")

        result = run(galaxy_clone, "26.2", "--no-confirm")

        assert result.exit_code == 0, result.output
        assert git(upstream_repo, "rev-parse", "release_26.2") == dev
        assert remote_branches(fork_repo) == {"version-26.2.rc1", "version-27.0.dev"}
        assert git(galaxy_clone, "branch", "--show-current") == "dev"
        assert "untracked.txt" in git(galaxy_clone, "status", "--porcelain")

        rc_versions = {"galaxy-util": "26.2.0rc1", "galaxy-app": "26.2.0rc1"}
        git(galaxy_clone, "fetch", "--quiet", str(fork_repo), "version-26.2.rc1")
        rc = "FETCH_HEAD"
        assert git(galaxy_clone, "log", "-1", "--format=%s", rc) == "Update version to 26.2.rc1"
        assert git(galaxy_clone, "rev-parse", f"{rc}^") == dev
        assert root_version(galaxy_clone, rc) == "26.2.rc1"
        assert package_versions(galaxy_clone, rc) == rc_versions
        assert locked_versions(galaxy_clone, rc) == rc_versions
        assert client_version(galaxy_clone, rc) == "26.2.0rc1"
        assert set(git(galaxy_clone, "diff", "--name-only", f"{rc}^", rc).split()) == {
            "client/package.json",
            "lib/galaxy/version/__init__.py",
            "packages/app/pyproject.toml",
            "packages/util/pyproject.toml",
            "uv.lock",
        }
        rc_commit = git(galaxy_clone, "rev-parse", rc)

        git(galaxy_clone, "fetch", "--quiet", str(fork_repo), "version-27.0.dev")
        next_dev = "FETCH_HEAD"
        next_versions = {"galaxy-util": "27.0.dev0", "galaxy-app": "27.0.dev0"}
        assert git(galaxy_clone, "log", "-1", "--format=%s", next_dev) == "Merge branch 'release_26.2' into 'dev'"
        assert git(galaxy_clone, "rev-parse", f"{next_dev}^2") == rc_commit
        assert git(galaxy_clone, "log", "-1", "--format=%s", f"{next_dev}^") == "Update version to 27.0.dev0"
        assert git(galaxy_clone, "rev-parse", f"{next_dev}^^") == dev
        # merging the release candidate keeps dev's versions
        assert git(galaxy_clone, "diff", f"{next_dev}^", next_dev) == ""
        assert root_version(galaxy_clone, next_dev) == "27.0.dev0"
        assert package_versions(galaxy_clone, next_dev) == next_versions
        assert locked_versions(galaxy_clone, next_dev) == next_versions
        assert client_version(galaxy_clone, next_dev) == "27.0.dev0"
        assert "RELEASE_CURR:=27.0\n" in git(galaxy_clone, "show", f"{next_dev}:Makefile") + "\n"

        git(galaxy_clone, "checkout", "--quiet", "version-27.0.dev")
        subprocess.run(["uv", "lock", "--check"], cwd=galaxy_clone, check=True)

    def test_prints_pull_request_urls(self, galaxy_clone):
        git(galaxy_clone, "remote", "set-url", "origin", "git@github.com:someone/galaxy.git")

        result = run(galaxy_clone, "26.2", "--next-version", "27.0", "--dry-run")

        assert result.exit_code == 0, result.output
        assert (
            "https://github.com/galaxyproject/galaxy/compare/release_26.2...someone:version-26.2.rc1" in result.output
        )
        assert "https://github.com/galaxyproject/galaxy/compare/dev...someone:version-27.0.dev" in result.output

    def test_dry_run_pushes_nothing(self, galaxy_clone, upstream_repo, fork_repo):
        result = run(galaxy_clone, "26.2", "--dry-run")

        assert result.exit_code == 0, result.output
        assert "Dry run, not running: git push origin version-26.2.rc1:version-26.2.rc1" in result.output
        assert (
            "Dry run, not running: git push --force-with-lease=refs/heads/release_26.2: upstream "
            "refs/remotes/upstream/dev:refs/heads/release_26.2" in result.output
        )
        assert remote_branches(upstream_repo) == {"dev"}
        assert remote_branches(fork_repo) == set()
        assert root_version(galaxy_clone, "version-26.2.rc1") == "26.2.rc1"
        assert root_version(galaxy_clone, "version-27.0.dev") == "27.0.dev0"
        assert "git branch -D version-26.2.rc1 version-27.0.dev" in result.output

    def test_run_after_dry_run_names_branches_to_delete(self, galaxy_clone):
        run(galaxy_clone, "26.2", "--dry-run")
        tips = git(galaxy_clone, "rev-parse", "version-26.2.rc1", "version-27.0.dev")

        result = run(galaxy_clone, "26.2", "--no-confirm")

        assert result.exit_code == 1
        assert "delete them with 'git branch -D version-26.2.rc1 version-27.0.dev'" in result.output
        assert git(galaxy_clone, "rev-parse", "version-26.2.rc1", "version-27.0.dev") == tips
        assert git(galaxy_clone, "branch", "--show-current") == "dev"

    def test_declining_to_push_release_branch(self, galaxy_clone, upstream_repo, fork_repo):
        result = run(galaxy_clone, "26.2", input="y\ny\nn\n")

        assert result.exit_code == 1
        assert remote_branches(fork_repo) == {"version-26.2.rc1", "version-27.0.dev"}
        assert remote_branches(upstream_repo) == {"dev"}
        assert (
            "To finish, run:\n  git push --force-with-lease=refs/heads/release_26.2: upstream "
            "refs/remotes/upstream/dev:refs/heads/release_26.2\n" in result.output
        )
        assert git(galaxy_clone, "branch", "--show-current") == "dev"

    def test_does_not_move_release_branch_created_meanwhile(self, galaxy_clone, upstream_repo, monkeypatch):
        other_commit = git(upstream_repo, "commit-tree", "-m", "Elsewhere", "dev^{tree}")
        resolve_next_version = release_branch.resolve_next_version

        def create_release_branch_upstream(*args):
            git(upstream_repo, "branch", "release_26.2", other_commit)
            return resolve_next_version(*args)

        monkeypatch.setattr(release_branch, "resolve_next_version", create_release_branch_upstream)

        result = CliRunner().invoke(create_release_branch, ["--galaxy-root", str(galaxy_clone), "26.2", "--no-confirm"])

        assert result.exit_code == 1
        assert "release_26.2" in result.output and "failed" in result.output
        assert git(upstream_repo, "rev-parse", "release_26.2") == other_commit

    def test_failure_removes_created_branches(self, galaxy_clone, monkeypatch):
        def fail(*args):
            raise click.ClickException("Makefile is broken")

        monkeypatch.setattr(release_branch, "set_makefile_release", fail)

        result = run(galaxy_clone, "26.2", "--dry-run")

        assert result.exit_code == 1
        assert "Makefile is broken" in result.output
        assert git(galaxy_clone, "branch", "--list", "version-*") == ""
        assert git(galaxy_clone, "branch", "--show-current") == "dev"
        assert git(galaxy_clone, "status", "--porcelain") == ""

    def test_returns_to_detached_head(self, galaxy_clone):
        git(galaxy_clone, "checkout", "--quiet", "--detach", "dev")
        start = git(galaxy_clone, "rev-parse", "HEAD")

        result = run(galaxy_clone, "26.2", "--dry-run")

        assert result.exit_code == 0, result.output
        assert git(galaxy_clone, "branch", "--show-current") == ""
        assert git(galaxy_clone, "rev-parse", "HEAD") == start

    def test_next_version_option_wins_over_milestones(self, galaxy_clone):
        result = run(galaxy_clone, "26.2", "--next-version", "26.3", "--dry-run")

        assert result.exit_code == 0, result.output
        assert root_version(galaxy_clone, "version-26.3.dev") == "26.3.dev0"

    @pytest.mark.parametrize("next_version", ["27", "26.3.0", "27.0rc1"])
    def test_rejects_next_version_that_is_not_major_minor(self, galaxy_clone, next_version):
        result = run(galaxy_clone, "26.2", "--next-version", next_version, "--dry-run")

        assert result.exit_code == 2
        assert "Expected a next version like 27.0" in result.output
        assert git(galaxy_clone, "branch", "--list", "version-*") == ""

    def test_next_version_ignores_point_release_milestones(self, galaxy_clone, milestones):
        milestones[Version("26.2.1")] = None

        result = run(galaxy_clone, "26.2", "--dry-run")

        assert result.exit_code == 0, result.output
        assert root_version(galaxy_clone, "version-27.0.dev") == "27.0.dev0"

    def test_next_version_required_without_milestones(self, galaxy_clone, milestones):
        milestones.clear()

        result = run(galaxy_clone, "26.2", "--dry-run")

        assert result.exit_code == 2
        assert "Could not determine --next-version" in result.output

    def test_rejects_release_not_in_development(self, galaxy_clone):
        result = run(galaxy_clone, "26.1", "--next-version", "26.2", "--dry-run")

        assert result.exit_code == 1
        assert "upstream/dev is at version 26.2.dev0, expected 26.1" in result.output
        assert git(galaxy_clone, "branch", "--show-current") == "dev"


class TestNextReleaseCandidate:
    @pytest.fixture
    def release_branch_at_rc1(self, galaxy_clone):
        git(galaxy_clone, "checkout", "--quiet", "-b", "release_26.2")
        write_versions(galaxy_clone, "26.2", "rc1", "26.2.0rc1", "26.2.0rc1")
        uv_lock(galaxy_clone)
        commit_all(galaxy_clone, "Update version to 26.2.rc1")
        git(galaxy_clone, "push", "--quiet", "upstream", "release_26.2")
        git(galaxy_clone, "checkout", "--quiet", "dev")
        return git(galaxy_clone, "rev-parse", "release_26.2")

    def test_bumps_release_candidate(self, galaxy_clone, fork_repo, milestones, release_branch_at_rc1):
        milestones.clear()  # the next version is not needed

        result = run(galaxy_clone, "26.2", "--no-confirm")

        assert result.exit_code == 0, result.output
        assert remote_branches(fork_repo) == {"version-26.2.rc2"}
        git(galaxy_clone, "fetch", "--quiet", str(fork_repo), "version-26.2.rc2")
        rc2 = "FETCH_HEAD"
        rc2_versions = {"galaxy-util": "26.2.0rc2", "galaxy-app": "26.2.0rc2"}
        assert git(galaxy_clone, "log", "-1", "--format=%s", rc2) == "Update version to 26.2.rc2"
        assert git(galaxy_clone, "rev-parse", f"{rc2}^") == release_branch_at_rc1
        assert root_version(galaxy_clone, rc2) == "26.2.rc2"
        assert package_versions(galaxy_clone, rc2) == rc2_versions
        assert locked_versions(galaxy_clone, rc2) == rc2_versions
        assert client_version(galaxy_clone, rc2) == "26.2.0rc2"

    def test_rejects_release_branch_past_release_candidates(self, galaxy_clone, fork_repo):
        git(galaxy_clone, "checkout", "--quiet", "-b", "release_26.2")
        write_versions(galaxy_clone, "26.2", "1.dev0", "26.2.1.dev0", "26.2.1.dev0")
        commit_all(galaxy_clone, "Start work on 26.2.1.dev0")
        git(galaxy_clone, "push", "--quiet", "upstream", "release_26.2")

        result = run(galaxy_clone, "26.2", "--no-confirm")

        assert result.exit_code == 1
        assert "which is not a release candidate of 26.2" in result.output
        assert remote_branches(fork_repo) == set()


def test_rejects_uncommitted_changes(galaxy_clone):
    (galaxy_clone / "Makefile").write_text("")

    result = run(galaxy_clone, "26.2", "--dry-run")

    assert result.exit_code == 1
    assert "has uncommitted changes" in result.output


def test_rejects_version_with_micro_part(galaxy_clone):
    result = run(galaxy_clone, "26.2.0", "--dry-run")

    assert result.exit_code == 2
    assert "Expected a release version like 26.2" in result.output
