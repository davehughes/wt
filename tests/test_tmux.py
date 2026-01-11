"""Tests for tmux module."""

from __future__ import annotations

from pathlib import Path

import pytest

from wt import tmux


class TestProfileRendering:
    """Tests for profile template rendering."""

    def test_render_profile_simple(self) -> None:
        """Test rendering a simple profile dict."""
        profile = {
            "session_name": "{{topic}}-{{name}}",
            "windows": [
                {"panes": [{"shell_command": ["cd {{worktree_path}}"]}]}
            ],
        }
        result = tmux.render_profile(
            profile,
            topic="feature",
            name="auth",
            worktree_path=Path("/projects/worktrees/feature/auth"),
        )

        assert result["session_name"] == "feature-auth"
        assert result["windows"][0]["panes"][0]["shell_command"][0] == "cd /projects/worktrees/feature/auth"

    def test_render_profile_multiple_occurrences(self) -> None:
        """Test rendering with multiple template variables."""
        profile = {
            "name": "{{topic}}/{{name}}",
            "paths": ["{{worktree_path}}", "{{worktree_path}}/src"],
        }
        result = tmux.render_profile(
            profile,
            topic="bug",
            name="fix-123",
            worktree_path=Path("/tmp/wt"),
        )

        assert result["name"] == "bug/fix-123"
        assert result["paths"][0] == "/tmp/wt"
        assert result["paths"][1] == "/tmp/wt/src"

    def test_render_profile_preserves_non_strings(self) -> None:
        """Test that non-string values are preserved."""
        profile = {
            "session_name": "{{topic}}",
            "count": 42,
            "enabled": True,
            "ratio": 3.14,
        }
        result = tmux.render_profile(
            profile,
            topic="test",
            name="name",
            worktree_path=Path("/tmp"),
        )

        assert result["count"] == 42
        assert result["enabled"] is True
        assert result["ratio"] == 3.14


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

    def test_window_exists(self, headless_tmux: str) -> None:
        """Test checking if a window exists."""
        # Create session with a named window
        tmux.run_tmux(
            "new-session", "-d", "-s", "window-test", "-n", "main",
            socket=headless_tmux,
        )

        assert tmux.window_exists("main", "window-test", socket=headless_tmux)
        assert not tmux.window_exists("nonexistent", "window-test", socket=headless_tmux)

    def test_create_window(self, headless_tmux: str, tmp_path: Path) -> None:
        """Test creating a new window."""
        # Create session
        tmux.run_tmux(
            "new-session", "-d", "-s", "create-window-test",
            socket=headless_tmux,
        )

        # Create a new window
        target = tmux.create_window(
            "new-window",
            session_name="create-window-test",
            start_directory=tmp_path,
            socket=headless_tmux,
        )

        assert target == "create-window-test:new-window"
        assert tmux.window_exists("new-window", "create-window-test", socket=headless_tmux)

    def test_kill_window(self, headless_tmux: str) -> None:
        """Test killing a window."""
        # Create session with multiple windows
        tmux.run_tmux(
            "new-session", "-d", "-s", "kill-window-test", "-n", "keep",
            socket=headless_tmux,
        )
        tmux.create_window("delete", session_name="kill-window-test", socket=headless_tmux)

        assert tmux.window_exists("delete", "kill-window-test", socket=headless_tmux)

        # Kill the window
        tmux.kill_window("kill-window-test:delete", socket=headless_tmux)
        assert not tmux.window_exists("delete", "kill-window-test", socket=headless_tmux)
        # Session should still exist
        assert tmux.session_exists("kill-window-test", socket=headless_tmux)
