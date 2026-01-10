"""Tests for commands module."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from wt import commands, git
from wt.config import Config, ConfigError


class TestCmdNew:
    """Tests for cmd_new command."""

    def test_create_worktree(
        self,
        temp_config: tuple[Path, Config],
        temp_git_repo: Path,
    ) -> None:
        """Test creating a new worktree."""
        config_path, config = temp_config

        # Change to the git repo so git commands work
        old_cwd = os.getcwd()
        os.chdir(temp_git_repo)

        try:
            path = commands.cmd_new(config, "feature/auth")

            assert path.exists()
            assert path == config.worktree_path("feature", "auth")
            assert git.branch_exists(config.branch_name("feature", "auth"), temp_git_repo)
        finally:
            os.chdir(old_cwd)

    def test_create_worktree_from_branch(
        self,
        temp_config: tuple[Path, Config],
        temp_git_repo: Path,
    ) -> None:
        """Test creating a worktree from a specific branch."""
        config_path, config = temp_config

        old_cwd = os.getcwd()
        os.chdir(temp_git_repo)

        try:
            # Create a branch to use as base
            git.create_branch("develop", path=temp_git_repo)

            path = commands.cmd_new(config, "feature/from-develop", from_branch="develop")
            assert path.exists()
        finally:
            os.chdir(old_cwd)


class TestCmdList:
    """Tests for cmd_list command."""

    def test_list_empty(self, temp_config: tuple[Path, Config]) -> None:
        """Test listing when no worktrees exist."""
        config_path, config = temp_config
        result = commands.cmd_list(config)
        assert result == []

    def test_list_worktrees(
        self,
        temp_config: tuple[Path, Config],
        temp_git_repo: Path,
    ) -> None:
        """Test listing existing worktrees."""
        config_path, config = temp_config

        old_cwd = os.getcwd()
        os.chdir(temp_git_repo)

        try:
            # Create some worktrees
            commands.cmd_new(config, "feature/one")
            commands.cmd_new(config, "feature/two")
            commands.cmd_new(config, "bugfix/issue-123")

            result = commands.cmd_list(config)

            assert len(result) == 3

            names = [(wt["topic"], wt["name"]) for wt in result]
            assert ("feature", "one") in names
            assert ("feature", "two") in names
            assert ("bugfix", "issue-123") in names
        finally:
            os.chdir(old_cwd)


class TestCmdSync:
    """Tests for cmd_sync command."""

    def test_sync_current_not_in_worktree(
        self,
        temp_config: tuple[Path, Config],
        tmp_path: Path,
    ) -> None:
        """Test sync error when not in a managed worktree."""
        config_path, config = temp_config

        old_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            with pytest.raises(ConfigError, match="Not in a managed worktree"):
                commands.cmd_sync(config)
        finally:
            os.chdir(old_cwd)

    def test_sync_all_empty(self, temp_config: tuple[Path, Config]) -> None:
        """Test sync --all with no worktrees."""
        config_path, config = temp_config
        result = commands.cmd_sync(config, sync_all=True)
        assert result == []


class TestGetCurrentWorktreeInfo:
    """Tests for get_current_worktree_info helper."""

    def test_in_managed_worktree(
        self,
        temp_config: tuple[Path, Config],
        temp_git_repo: Path,
    ) -> None:
        """Test detection when in a managed worktree."""
        config_path, config = temp_config

        old_cwd = os.getcwd()
        os.chdir(temp_git_repo)

        try:
            # Create a worktree
            path = commands.cmd_new(config, "test/detection")

            # Change to the worktree
            os.chdir(path)

            result = commands.get_current_worktree_info(config)
            assert result == ("test", "detection")
        finally:
            os.chdir(old_cwd)

    def test_not_in_managed_worktree(
        self,
        temp_config: tuple[Path, Config],
        tmp_path: Path,
    ) -> None:
        """Test None returned when not in managed worktree."""
        config_path, config = temp_config

        old_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            result = commands.get_current_worktree_info(config)
            assert result is None
        finally:
            os.chdir(old_cwd)
