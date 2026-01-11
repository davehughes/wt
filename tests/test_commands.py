"""Tests for commands module."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from wt import commands, git
from wt.config import Config, ConfigError


class TestEnsureWorktree:
    """Tests for ensure_worktree function."""

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
            path, was_created = commands.ensure_worktree(config, "feature/auth")

            assert was_created
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

            path, was_created = commands.ensure_worktree(config, "feature/from-develop", from_branch="develop")
            assert was_created
            assert path.exists()
        finally:
            os.chdir(old_cwd)

    def test_existing_worktree_not_recreated(
        self,
        temp_config: tuple[Path, Config],
        temp_git_repo: Path,
    ) -> None:
        """Test that existing worktree is not recreated."""
        config_path, config = temp_config

        old_cwd = os.getcwd()
        os.chdir(temp_git_repo)

        try:
            # Create worktree first time
            path1, was_created1 = commands.ensure_worktree(config, "feature/existing")
            assert was_created1

            # Try to create again - should return existing
            path2, was_created2 = commands.ensure_worktree(config, "feature/existing")
            assert not was_created2
            assert path1 == path2
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
            commands.ensure_worktree(config, "feature/one")
            commands.ensure_worktree(config, "feature/two")
            commands.ensure_worktree(config, "bugfix/issue-123")

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
            path, _ = commands.ensure_worktree(config, "test/detection")

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


class TestLinkTemplate:
    """Tests for link_template and cmd_link."""

    def test_link_template_creates_symlinks(
        self,
        temp_config: tuple[Path, Config],
        temp_git_repo: Path,
    ) -> None:
        """Test that template contents are symlinked into worktree."""
        config_path, config = temp_config

        # Create template directory with some files
        config.template_dir.mkdir(parents=True, exist_ok=True)
        (config.template_dir / ".claude").mkdir()
        (config.template_dir / ".claude" / "settings.json").write_text('{"test": true}')
        (config.template_dir / ".editorconfig").write_text("root = true")

        old_cwd = os.getcwd()
        os.chdir(temp_git_repo)

        try:
            # Create a worktree (link_template is called automatically)
            path, _ = commands.ensure_worktree(config, "feature/linked")

            # Verify symlinks were created
            assert (path / ".claude").is_symlink()
            assert (path / ".editorconfig").is_symlink()

            # Verify they point to the right place
            assert (path / ".claude").resolve() == (config.template_dir / ".claude").resolve()
            assert (path / ".editorconfig").resolve() == (config.template_dir / ".editorconfig").resolve()

            # Verify content is accessible
            assert (path / ".claude" / "settings.json").read_text() == '{"test": true}'
        finally:
            os.chdir(old_cwd)

    def test_cmd_link_relinks(
        self,
        temp_config: tuple[Path, Config],
        temp_git_repo: Path,
    ) -> None:
        """Test that cmd_link can re-link template contents."""
        config_path, config = temp_config

        # Create template directory
        config.template_dir.mkdir(parents=True, exist_ok=True)
        (config.template_dir / ".config").write_text("original")

        old_cwd = os.getcwd()
        os.chdir(temp_git_repo)

        try:
            # Create a worktree
            path, _ = commands.ensure_worktree(config, "feature/relink")

            # Remove the symlink
            (path / ".config").unlink()
            assert not (path / ".config").exists()

            # Re-link
            os.chdir(path)
            actions = commands.cmd_link(config)

            assert any("Linked: .config" in a for a in actions)
            assert (path / ".config").is_symlink()
        finally:
            os.chdir(old_cwd)

    def test_link_skips_existing_files(
        self,
        temp_config: tuple[Path, Config],
        temp_git_repo: Path,
    ) -> None:
        """Test that existing non-symlink files are not overwritten."""
        config_path, config = temp_config

        # Create template directory
        config.template_dir.mkdir(parents=True, exist_ok=True)
        (config.template_dir / "existing").write_text("template")

        old_cwd = os.getcwd()
        os.chdir(temp_git_repo)

        try:
            # Create a worktree
            path, _ = commands.ensure_worktree(config, "feature/existing")

            # Remove symlink and create a real file
            (path / "existing").unlink()
            (path / "existing").write_text("local content")

            # Try to link - should skip
            os.chdir(path)
            actions = commands.cmd_link(config)

            assert any("Skipped (exists): existing" in a for a in actions)
            assert (path / "existing").read_text() == "local content"
        finally:
            os.chdir(old_cwd)


class TestCmdStatus:
    """Tests for cmd_status command."""

    def test_status_not_in_worktree(
        self,
        temp_config: tuple[Path, Config],
        tmp_path: Path,
    ) -> None:
        """Test status when not in a managed worktree."""
        config_path, config = temp_config

        old_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            status = commands.cmd_status(config)

            assert status.branch_prefix == "test"
            assert status.default_profile == "default"
            assert "default" in status.available_profiles
            assert not status.in_managed_worktree
            assert status.topic is None
            assert status.name is None
        finally:
            os.chdir(old_cwd)

    def test_status_in_worktree(
        self,
        temp_config: tuple[Path, Config],
        temp_git_repo: Path,
    ) -> None:
        """Test status when in a managed worktree."""
        config_path, config = temp_config

        old_cwd = os.getcwd()
        os.chdir(temp_git_repo)

        try:
            # Create a worktree
            path, _ = commands.ensure_worktree(config, "feature/status-test")

            # Change to the worktree
            os.chdir(path)

            status = commands.cmd_status(config)

            assert status.in_managed_worktree
            assert status.topic == "feature"
            assert status.name == "status-test"
            assert status.worktree_path == path
            assert status.expected_branch == "test/feature/status-test"
            assert status.current_branch == "test/feature/status-test"
            assert not status.has_tmux_window
        finally:
            os.chdir(old_cwd)
