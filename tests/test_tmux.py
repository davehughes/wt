"""Tests for tmux module."""

from __future__ import annotations

from pathlib import Path

import pytest

from wt import tmux


class TestProfileRendering:
    """Tests for profile template rendering."""

    def test_render_profile_simple(self) -> None:
        """Test rendering a simple profile template."""
        template = """session_name: "{{topic}}-{{name}}"
windows:
  - panes:
      - cd {{worktree_path}}
"""
        result = tmux.render_profile(
            template,
            topic="feature",
            name="auth",
            worktree_path=Path("/projects/worktrees/feature/auth"),
        )

        assert "feature-auth" in result
        assert "/projects/worktrees/feature/auth" in result

    def test_render_profile_multiple_occurrences(self) -> None:
        """Test rendering with multiple template variables."""
        template = """name: {{topic}}/{{name}}
path: {{worktree_path}}
another_path: {{worktree_path}}
"""
        result = tmux.render_profile(
            template,
            topic="bug",
            name="fix-123",
            worktree_path=Path("/tmp/wt"),
        )

        assert "bug/fix-123" in result
        assert result.count("/tmp/wt") == 2


class TestTmuxOperations:
    """Tests for tmux operations using headless server."""

    def test_session_exists_false(self, headless_tmux: str) -> None:
        """Test that session_exists returns False for non-existent session."""
        assert not tmux.session_exists("nonexistent", socket=headless_tmux)

    def test_create_and_check_session(self, headless_tmux: str, tmp_path: Path) -> None:
        """Test creating a session and checking it exists."""
        # Create a simple session directly
        tmux.run_tmux(
            "new-session", "-d", "-s", "test-session",
            socket=headless_tmux,
        )

        assert tmux.session_exists("test-session", socket=headless_tmux)

    def test_list_panes(self, headless_tmux: str) -> None:
        """Test listing panes in a session."""
        # Create session
        tmux.run_tmux(
            "new-session", "-d", "-s", "pane-test",
            socket=headless_tmux,
        )

        panes = tmux.list_panes("pane-test", socket=headless_tmux)
        assert len(panes) >= 1

    def test_send_keys(self, headless_tmux: str) -> None:
        """Test sending keys to a pane."""
        # Create session
        tmux.run_tmux(
            "new-session", "-d", "-s", "keys-test",
            socket=headless_tmux,
        )

        # This should not raise
        tmux.send_keys("keys-test:0.0", "echo hello", socket=headless_tmux)

    def test_kill_session(self, headless_tmux: str) -> None:
        """Test killing a session."""
        # Create session
        tmux.run_tmux(
            "new-session", "-d", "-s", "kill-test",
            socket=headless_tmux,
        )
        assert tmux.session_exists("kill-test", socket=headless_tmux)

        # Kill it
        tmux.kill_session("kill-test", socket=headless_tmux)
        assert not tmux.session_exists("kill-test", socket=headless_tmux)


class TestLoadProfile:
    """Tests for profile loading."""

    def test_load_profile_success(self, tmp_path: Path) -> None:
        """Test loading an existing profile."""
        profile_path = tmp_path / "test.yaml"
        profile_path.write_text("session_name: test")

        content = tmux.load_profile(profile_path)
        assert content == "session_name: test"

    def test_load_profile_not_found(self, tmp_path: Path) -> None:
        """Test error when profile doesn't exist."""
        with pytest.raises(tmux.TmuxError, match="Profile not found"):
            tmux.load_profile(tmp_path / "nonexistent.yaml")
