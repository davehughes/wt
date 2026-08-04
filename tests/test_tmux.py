"""Tests for tmux module."""

from __future__ import annotations

import time
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
        target, window_id, pane_id = tmux.create_window(
            "new-window",
            session_name="create-window-test",
            start_directory=tmp_path,
            socket=headless_tmux,
        )

        assert target == "create-window-test:new-window"
        assert window_id.startswith("@")
        assert pane_id.startswith("%")
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


class TestWindowIndex:
    """Tests for the batched window snapshot."""

    def test_empty_when_no_server(self) -> None:
        """A missing server yields an empty index rather than an error."""
        index = tmux.WindowIndex.load(socket="wt-test-no-such-server")

        assert index.windows == ()
        assert not index.has_session("anything")
        assert index.id_for("a/b", "anything") is None
        assert index.names_in("anything") == set()

    def test_indexes_windows_across_sessions(self, headless_tmux: str) -> None:
        """One load covers every session on the server."""
        tmux.run_tmux("new-session", "-d", "-s", "s1", "-n", "w1", socket=headless_tmux)
        tmux.run_tmux("new-session", "-d", "-s", "s2", "-n", "w2", socket=headless_tmux)

        index = tmux.WindowIndex.load(socket=headless_tmux)

        assert index.has_session("s1")
        assert index.has_session("s2")
        assert not index.has_session("s3")
        assert index.names_in("s1") == {"w1"}
        assert index.names_in("s2") == {"w2"}
        assert index.id_for("w1", "s1").startswith("@")
        # Same name in the wrong session must not match
        assert index.id_for("w1", "s2") is None

    def test_id_for_dotted_window_name(self, headless_tmux: str) -> None:
        """Names containing '.' resolve to ids, which are safe as targets.

        tmux reads '.' as the window/pane separator in a target spec, so
        "session:topic/a.b" is misparsed; "@1" never is.
        """
        tmux.run_tmux("new-session", "-d", "-s", "dotted", "-n", "topic/a.b", socket=headless_tmux)

        index = tmux.WindowIndex.load(socket=headless_tmux)
        window_id = index.id_for("topic/a.b", "dotted")

        assert window_id is not None and window_id.startswith("@")
        # The id works as a target where the name would not
        result = tmux.run_tmux(
            "display-message", "-t", window_id, "-p", "#{window_name}",
            socket=headless_tmux,
        )
        assert result.stdout.strip() == "topic/a.b"

    def test_has_session_and_id_for_tolerate_none(self, headless_tmux: str) -> None:
        """Callers pass an unknown current session as None."""
        tmux.run_tmux("new-session", "-d", "-s", "s1", socket=headless_tmux)
        index = tmux.WindowIndex.load(socket=headless_tmux)

        assert not index.has_session(None)
        assert index.id_for("w1", None) is None
        assert index.names_in(None) == set()


class TestSetupPanes:
    """Tests for batched pane setup."""

    def _window(self, socket: str, name: str) -> tuple[str, str]:
        tmux.run_tmux(
            "new-session", "-d", "-s", name, "-x", "200", "-y", "50",
            socket=socket,
        )
        return tmux.get_window_ids(f"{name}:0", socket=socket)

    def test_creates_one_pane_per_config(self, headless_tmux: str, tmp_path: Path) -> None:
        """Four pane configs produce four panes."""
        window_id, first_pane = self._window(headless_tmux, "panes4")

        tmux.setup_panes(
            window_id,
            first_pane,
            panes=[{"shell_command": []} for _ in range(4)],
            layout="tiled",
            worktree_path=tmp_path,
            socket=headless_tmux,
        )

        panes = tmux.run_tmux(
            "list-panes", "-t", window_id, "-F", "#{pane_id}", socket=headless_tmux
        )
        assert len(panes.stdout.strip().split("\n")) == 4

    def test_new_panes_start_in_worktree(self, headless_tmux: str, tmp_path: Path) -> None:
        """Panes get their cwd from tmux -c, so profiles need no explicit cd."""
        window_id, first_pane = self._window(headless_tmux, "panescwd")
        worktree = tmp_path / "tree"
        worktree.mkdir()

        tmux.setup_panes(
            window_id, first_pane,
            panes=[{"shell_command": []}, {"shell_command": []}],
            layout="tiled", worktree_path=worktree, socket=headless_tmux,
        )

        result = tmux.run_tmux(
            "list-panes", "-t", window_id, "-F", "#{pane_current_path}",
            socket=headless_tmux,
        )
        # The first pane predates setup_panes; the split ones must honour -c.
        assert str(worktree) in result.stdout

    def test_first_pane_left_active(self, headless_tmux: str, tmp_path: Path) -> None:
        """Focus returns to the first pane after splitting."""
        window_id, first_pane = self._window(headless_tmux, "panesactive")

        tmux.setup_panes(
            window_id, first_pane,
            panes=[{"shell_command": []} for _ in range(3)],
            layout="tiled", worktree_path=tmp_path, socket=headless_tmux,
        )

        result = tmux.run_tmux(
            "list-panes", "-t", window_id, "-F", "#{pane_id}:#{pane_active}",
            socket=headless_tmux,
        )
        assert f"{first_pane}:1" in result.stdout

    def test_no_panes_is_a_noop(self, headless_tmux: str, tmp_path: Path) -> None:
        """An empty pane list must not touch the window."""
        window_id, first_pane = self._window(headless_tmux, "panesnone")

        tmux.setup_panes(
            window_id, first_pane, panes=[], layout="tiled",
            worktree_path=tmp_path, socket=headless_tmux,
        )

        panes = tmux.run_tmux(
            "list-panes", "-t", window_id, "-F", "#{pane_id}", socket=headless_tmux
        )
        assert len(panes.stdout.strip().split("\n")) == 1

    def test_command_ending_in_semicolon(self, headless_tmux: str, tmp_path: Path) -> None:
        """A shell_command ending in ';' must not be parsed as a separator.

        tmux treats a trailing ';' on an argument as a command separator, which
        would otherwise turn the following "Enter" into a bogus command.
        """
        window_id, first_pane = self._window(headless_tmux, "panessemi")

        # Would raise TmuxError ("unknown command: Enter") if chained blindly.
        tmux.setup_panes(
            window_id, first_pane,
            panes=[{"shell_command": ["echo one;"]}, {"shell_command": ["echo two"]}],
            layout="tiled", worktree_path=tmp_path, socket=headless_tmux,
        )

        panes = tmux.run_tmux(
            "list-panes", "-t", window_id, "-F", "#{pane_id}", socket=headless_tmux
        )
        assert len(panes.stdout.strip().split("\n")) == 2


class TestEscapeKeys:
    """Tests for send-keys argument escaping."""

    def test_escapes_only_trailing_semicolon(self) -> None:
        """Trailing ';' is escaped; interior ones must be left alone."""
        assert tmux.escape_keys("echo one;") == "echo one\\;"
        assert tmux.escape_keys("echo one") == "echo one"
        # Mid-string: tmux passes a backslash through literally, so don't add one
        assert tmux.escape_keys("for i in 1 2; do echo $i; done") == (
            "for i in 1 2; do echo $i; done"
        )

    def test_trailing_semicolon_reaches_shell_intact(
        self, headless_tmux: str, tmp_path: Path
    ) -> None:
        """The escape must send a real ';', not a backslash."""
        marker = tmp_path / "marker"
        tmux.run_tmux(
            "new-session", "-d", "-s", "esc", "-x", "80", "-y", "24",
            socket=headless_tmux,
        )
        time.sleep(1.0)

        tmux.send_keys("esc:0.0", f"touch {marker};", socket=headless_tmux)

        for _ in range(40):
            if marker.exists():
                break
            time.sleep(0.25)
        assert marker.exists(), "command with trailing ';' did not run"
