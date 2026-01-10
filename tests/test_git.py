"""Tests for git module."""

from __future__ import annotations

from pathlib import Path

import pytest

from wt import git


class TestGitBasics:
    """Tests for basic git operations."""

    def test_get_repo_root(self, temp_git_repo: Path) -> None:
        """Test getting repository root."""
        root = git.get_repo_root(temp_git_repo)
        assert root == temp_git_repo

    def test_get_repo_root_from_subdir(self, temp_git_repo: Path) -> None:
        """Test getting repository root from subdirectory."""
        subdir = temp_git_repo / "subdir"
        subdir.mkdir()

        root = git.get_repo_root(subdir)
        assert root == temp_git_repo

    def test_get_current_branch(self, temp_git_repo: Path) -> None:
        """Test getting current branch."""
        # Default branch could be main or master
        branch = git.get_current_branch(temp_git_repo)
        assert branch in ("main", "master")

    def test_branch_exists(self, temp_git_repo: Path) -> None:
        """Test checking if branch exists."""
        current = git.get_current_branch(temp_git_repo)
        assert current is not None

        assert git.branch_exists(current, temp_git_repo)
        assert not git.branch_exists("nonexistent-branch", temp_git_repo)

    def test_create_branch(self, temp_git_repo: Path) -> None:
        """Test creating a new branch."""
        git.create_branch("test-branch", path=temp_git_repo)
        assert git.branch_exists("test-branch", temp_git_repo)

    def test_create_branch_from_base(self, temp_git_repo: Path) -> None:
        """Test creating a branch from a base."""
        current = git.get_current_branch(temp_git_repo)
        git.create_branch("new-branch", base=current, path=temp_git_repo)
        assert git.branch_exists("new-branch", temp_git_repo)


class TestWorktrees:
    """Tests for worktree operations."""

    def test_list_worktrees(self, temp_git_repo: Path) -> None:
        """Test listing worktrees."""
        worktrees = git.list_worktrees(temp_git_repo)
        assert len(worktrees) >= 1
        assert worktrees[0].path == temp_git_repo

    def test_add_worktree_existing_branch(self, temp_git_repo: Path) -> None:
        """Test adding a worktree for an existing branch."""
        # Create branch first
        git.create_branch("feature-branch", path=temp_git_repo)

        # Add worktree
        wt_path = temp_git_repo.parent / "feature-worktree"
        git.add_worktree(wt_path, "feature-branch", repo_path=temp_git_repo)

        assert wt_path.exists()
        assert (wt_path / ".git").exists()

        # Verify it shows up in list
        worktrees = git.list_worktrees(temp_git_repo)
        paths = [wt.path for wt in worktrees]
        assert wt_path in paths

    def test_add_worktree_new_branch(self, temp_git_repo: Path) -> None:
        """Test adding a worktree with a new branch."""
        wt_path = temp_git_repo.parent / "new-feature"
        git.add_worktree(
            wt_path,
            "new-feature-branch",
            create_branch=True,
            repo_path=temp_git_repo,
        )

        assert wt_path.exists()
        assert git.branch_exists("new-feature-branch", temp_git_repo)

    def test_remove_worktree(self, temp_git_repo: Path) -> None:
        """Test removing a worktree."""
        # Create worktree
        git.create_branch("to-remove", path=temp_git_repo)
        wt_path = temp_git_repo.parent / "to-remove-wt"
        git.add_worktree(wt_path, "to-remove", repo_path=temp_git_repo)
        assert wt_path.exists()

        # Remove it
        git.remove_worktree(wt_path, repo_path=temp_git_repo)
        assert not wt_path.exists()

    def test_worktree_path_for_branch(self, temp_git_repo: Path) -> None:
        """Test finding worktree path for a branch."""
        # Create worktree
        git.create_branch("find-me", path=temp_git_repo)
        wt_path = temp_git_repo.parent / "find-me-wt"
        git.add_worktree(wt_path, "find-me", repo_path=temp_git_repo)

        found = git.worktree_path_for_branch("find-me", temp_git_repo)
        assert found == wt_path

    def test_worktree_path_for_nonexistent_branch(self, temp_git_repo: Path) -> None:
        """Test that None is returned for branch without worktree."""
        found = git.worktree_path_for_branch("no-such-branch", temp_git_repo)
        assert found is None


class TestWorktreeFromPorcelain:
    """Tests for Worktree.from_porcelain_line."""

    def test_parse_normal_worktree(self) -> None:
        """Test parsing a normal worktree entry."""
        lines = [
            "worktree /path/to/worktree",
            "HEAD abc123def456",
            "branch refs/heads/main",
        ]
        wt = git.Worktree.from_porcelain_line(lines)

        assert wt.path == Path("/path/to/worktree")
        assert wt.head == "abc123def456"
        assert wt.branch == "refs/heads/main"
        assert not wt.is_bare
        assert not wt.is_detached

    def test_parse_bare_worktree(self) -> None:
        """Test parsing a bare repository entry."""
        lines = [
            "worktree /path/to/bare.git",
            "bare",
        ]
        wt = git.Worktree.from_porcelain_line(lines)

        assert wt.is_bare
        assert wt.branch is None

    def test_parse_detached_worktree(self) -> None:
        """Test parsing a detached HEAD worktree."""
        lines = [
            "worktree /path/to/worktree",
            "HEAD abc123",
            "detached",
        ]
        wt = git.Worktree.from_porcelain_line(lines)

        assert wt.is_detached
        assert wt.branch is None
