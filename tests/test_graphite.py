"""Tests for graphite module."""

from __future__ import annotations

import json
from pathlib import Path

from wt import git, graphite


class TestIsInitialized:
    """Tests for the initialized check.

    This reads graphite's own state file rather than shelling out: the previous
    `gt log --short` used a flag gt does not accept, so it always reported "not
    initialized" and every caller then ran a slow, state-rewriting `gt init`.
    """

    def _write_repo_config(self, repo: Path, payload: dict) -> None:
        common_dir = git.get_git_common_dir(repo)
        (common_dir / graphite.REPO_CONFIG_NAME).write_text(json.dumps(payload))

    def test_false_without_state_file(self, temp_git_repo: Path) -> None:
        """A repo graphite has never touched is not initialized."""
        assert not graphite.is_initialized(cwd=temp_git_repo)

    def test_true_with_trunk(self, temp_git_repo: Path) -> None:
        """A trunk in the state file means initialized."""
        self._write_repo_config(temp_git_repo, {"trunk": "main"})

        assert graphite.is_initialized(cwd=temp_git_repo)

    def test_false_when_trunk_missing(self, temp_git_repo: Path) -> None:
        """State file present but no trunk is not initialized."""
        self._write_repo_config(temp_git_repo, {"lastFetchedPRInfoMs": 1})

        assert not graphite.is_initialized(cwd=temp_git_repo)

    def test_false_on_malformed_state_file(self, temp_git_repo: Path) -> None:
        """Unparseable state must not raise."""
        common_dir = git.get_git_common_dir(temp_git_repo)
        (common_dir / graphite.REPO_CONFIG_NAME).write_text("{not json")

        assert not graphite.is_initialized(cwd=temp_git_repo)

    def test_false_outside_a_repo(self, tmp_path: Path) -> None:
        """Outside a git repo there is no common dir to inspect."""
        assert not graphite.is_initialized(cwd=tmp_path)

    def test_shared_across_worktrees(self, temp_git_repo: Path, tmp_path: Path) -> None:
        """State lives in the common dir, so worktrees see the same answer.

        This is why graphite commands may run from any worktree -- and why they
        must not run from a bare main repo, which has no working tree at all.
        """
        self._write_repo_config(temp_git_repo, {"trunk": "main"})
        wt_path = tmp_path / "wt-gt"
        git.add_worktree(wt_path, "gt-branch", create_branch=True, repo_path=temp_git_repo)

        assert graphite.is_initialized(cwd=wt_path)


class TestIsAvailable:
    """Tests for the availability check."""

    def test_is_a_path_lookup(self, monkeypatch) -> None:
        """Availability is resolved from PATH, not by spawning gt."""
        monkeypatch.setattr(graphite.shutil, "which", lambda _: "/usr/bin/gt")
        assert graphite.is_available()

        monkeypatch.setattr(graphite.shutil, "which", lambda _: None)
        assert not graphite.is_available()

    def test_does_not_spawn_a_subprocess(self, monkeypatch) -> None:
        """Regression: this used to cost ~0.6s per wt invocation."""
        def fail(*a, **kw):
            raise AssertionError("is_available must not run a subprocess")

        monkeypatch.setattr(graphite.subprocess, "run", fail)
        monkeypatch.setattr(graphite.subprocess, "Popen", fail)

        graphite.is_available()
