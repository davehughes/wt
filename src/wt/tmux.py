"""Tmux and tmuxp integration."""

from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from string import Template


class TmuxError(Exception):
    """Raised when a tmux operation fails."""


def run_tmux(
    *args: str,
    socket: str | None = None,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a tmux command.

    Args:
        *args: tmux command and arguments
        socket: Optional socket name for isolated sessions
        check: Whether to raise on non-zero exit
        capture_output: Whether to capture stdout/stderr

    Returns:
        Completed process result

    Raises:
        TmuxError: If command fails and check=True
    """
    cmd = ["tmux"]
    if socket:
        cmd.extend(["-L", socket])
    cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
        )
        return result
    except subprocess.CalledProcessError as e:
        raise TmuxError(f"Tmux command failed: {' '.join(cmd)}\n{e.stderr}") from e


def load_profile(profile_path: Path) -> str:
    """Load a tmuxp profile template.

    Args:
        profile_path: Path to the YAML profile

    Returns:
        Profile contents as string

    Raises:
        TmuxError: If profile cannot be read
    """
    if not profile_path.exists():
        raise TmuxError(f"Profile not found: {profile_path}")

    return profile_path.read_text()


def render_profile(
    template: str,
    topic: str,
    name: str,
    worktree_path: Path,
) -> str:
    """Render a tmuxp profile template with variables.

    Args:
        template: Profile template string
        topic: Worktree topic
        name: Worktree name
        worktree_path: Path to the worktree

    Returns:
        Rendered profile YAML
    """
    # Use simple string replacement for mustache-style templates
    result = template.replace("{{topic}}", topic)
    result = result.replace("{{name}}", name)
    result = result.replace("{{worktree_path}}", str(worktree_path))
    return result


def launch_session(
    profile_path: Path,
    topic: str,
    name: str,
    worktree_path: Path,
    socket: str | None = None,
) -> str:
    """Launch a tmux session from a profile.

    Args:
        profile_path: Path to the tmuxp profile
        topic: Worktree topic
        name: Worktree name
        worktree_path: Path to the worktree
        socket: Optional socket name for isolated sessions

    Returns:
        Session name

    Raises:
        TmuxError: If session launch fails
    """
    template = load_profile(profile_path)
    rendered = render_profile(template, topic, name, worktree_path)

    # Write rendered profile to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(rendered)
        temp_path = f.name

    try:
        cmd = ["tmuxp", "load", "-d", temp_path]
        if socket:
            cmd.extend(["-L", socket])

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise TmuxError(f"Failed to launch session: {e.stderr}") from e
    finally:
        Path(temp_path).unlink()

    session_name = f"{topic}-{name}"
    return session_name


def session_exists(session_name: str, socket: str | None = None) -> bool:
    """Check if a tmux session exists.

    Args:
        session_name: Name of the session
        socket: Optional socket name

    Returns:
        True if session exists
    """
    result = run_tmux("has-session", "-t", session_name, socket=socket, check=False)
    return result.returncode == 0


def attach_session(session_name: str, socket: str | None = None) -> None:
    """Attach to an existing tmux session.

    Args:
        session_name: Name of the session
        socket: Optional socket name

    Raises:
        TmuxError: If attach fails
    """
    run_tmux("attach-session", "-t", session_name, socket=socket, capture_output=False)


def switch_client(session_name: str, socket: str | None = None) -> None:
    """Switch the current tmux client to a session.

    Args:
        session_name: Name of the session
        socket: Optional socket name

    Raises:
        TmuxError: If switch fails
    """
    run_tmux("switch-client", "-t", session_name, socket=socket)


def list_panes(session_name: str, socket: str | None = None) -> list[dict[str, str]]:
    """List panes in a session.

    Args:
        session_name: Name of the session
        socket: Optional socket name

    Returns:
        List of pane info dicts with keys: session, window, pane, command
    """
    result = run_tmux(
        "list-panes", "-t", session_name, "-a",
        "-F", "#{session_name}:#{window_index}.#{pane_index}:#{pane_current_command}",
        socket=socket,
    )

    panes = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(":", 2)
        if len(parts) >= 3:
            panes.append({
                "target": f"{parts[0]}:{parts[1]}",
                "command": parts[2],
            })
    return panes


def find_claude_panes(session_name: str, socket: str | None = None) -> list[str]:
    """Find panes running Claude Code in a session.

    Args:
        session_name: Name of the session
        socket: Optional socket name

    Returns:
        List of pane targets (e.g., "session:0.1")
    """
    panes = list_panes(session_name, socket)
    claude_panes = []
    for pane in panes:
        # Claude Code typically runs as 'claude' or 'node' process
        cmd = pane["command"].lower()
        if "claude" in cmd or "node" in cmd:
            claude_panes.append(pane["target"])
    return claude_panes


def send_keys(target: str, keys: str, socket: str | None = None) -> None:
    """Send keys to a tmux pane.

    Args:
        target: Pane target (e.g., "session:0.1")
        keys: Keys to send
        socket: Optional socket name
    """
    run_tmux("send-keys", "-t", target, keys, "Enter", socket=socket)


def close_claude_gracefully(
    session_name: str,
    socket: str | None = None,
    timeout: float = 5.0,
) -> None:
    """Gracefully close Claude Code sessions by sending /exit.

    Args:
        session_name: Name of the session
        socket: Optional socket name
        timeout: Seconds to wait for Claude to exit
    """
    claude_panes = find_claude_panes(session_name, socket)

    for target in claude_panes:
        send_keys(target, "/exit", socket)

    # Wait for Claude to exit
    start = time.time()
    while time.time() - start < timeout:
        remaining = find_claude_panes(session_name, socket)
        if not remaining:
            break
        time.sleep(0.5)


def kill_session(session_name: str, socket: str | None = None) -> None:
    """Kill a tmux session.

    Args:
        session_name: Name of the session
        socket: Optional socket name
    """
    run_tmux("kill-session", "-t", session_name, socket=socket, check=False)


def kill_server(socket: str | None = None) -> None:
    """Kill the tmux server.

    Args:
        socket: Optional socket name
    """
    run_tmux("kill-server", socket=socket, check=False)
