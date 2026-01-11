"""Tmux integration."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any


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


def _render_value(value: Any, variables: dict[str, str]) -> Any:
    """Recursively render template variables in a value.

    Args:
        value: Value to render (can be str, list, dict, or other)
        variables: Dict of variable names to values

    Returns:
        Rendered value with variables substituted
    """
    if isinstance(value, str):
        result = value
        for var_name, var_value in variables.items():
            result = result.replace(f"{{{{{var_name}}}}}", var_value)
        return result
    elif isinstance(value, dict):
        return {k: _render_value(v, variables) for k, v in value.items()}
    elif isinstance(value, list):
        return [_render_value(item, variables) for item in value]
    else:
        return value


def render_profile(
    profile: dict[str, Any],
    topic: str,
    name: str,
    worktree_path: Path,
) -> dict[str, Any]:
    """Render a profile with variables.

    Args:
        profile: Profile configuration dict
        topic: Worktree topic
        name: Worktree name
        worktree_path: Path to the worktree

    Returns:
        Rendered profile dict
    """
    import copy
    variables = {
        "topic": topic,
        "name": name,
        "worktree_path": str(worktree_path),
    }
    return _render_value(copy.deepcopy(profile), variables)


def get_current_window_info(socket: str | None = None) -> dict[str, Any] | None:
    """Get info about the current tmux window.

    Returns:
        Dict with session_name, window_name, window_index, panes (list of commands)
        or None if not inside tmux.
    """
    if not is_inside_tmux():
        return None

    # Get session and window info
    result = run_tmux(
        "display-message", "-p",
        "#{session_name}\t#{window_name}\t#{window_index}",
        socket=socket,
        check=False,
    )
    if result.returncode != 0:
        return None

    parts = result.stdout.strip().split("\t")
    if len(parts) < 3:
        return None

    session_name, window_name, window_index = parts

    # Get pane commands
    panes_result = run_tmux(
        "list-panes", "-F", "#{pane_current_command}",
        socket=socket,
        check=False,
    )
    panes = []
    if panes_result.returncode == 0:
        panes = [p for p in panes_result.stdout.strip().split("\n") if p]

    return {
        "session_name": session_name,
        "window_name": window_name,
        "window_index": window_index,
        "panes": panes,
    }


def is_inside_tmux() -> bool:
    """Check if currently running inside a tmux session."""
    return bool(os.environ.get("TMUX"))


def get_current_session(socket: str | None = None) -> str | None:
    """Get the name of the current tmux session.

    Returns:
        Session name or None if not in tmux
    """
    if not is_inside_tmux():
        return None
    result = run_tmux("display-message", "-p", "#{session_name}", socket=socket, check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


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


def window_exists(
    window_name: str,
    session_name: str | None = None,
    socket: str | None = None,
) -> bool:
    """Check if a window exists in a session.

    Args:
        window_name: Name of the window
        session_name: Session to check (defaults to current)
        socket: Optional socket name

    Returns:
        True if window exists
    """
    if session_name is None:
        session_name = get_current_session(socket)
        if session_name is None:
            return False

    result = run_tmux(
        "list-windows", "-t", session_name,
        "-F", "#{window_name}",
        socket=socket, check=False,
    )
    if result.returncode != 0:
        return False

    windows = result.stdout.strip().split("\n")
    return window_name in windows


def set_environment(
    name: str,
    value: str,
    session_name: str | None = None,
    socket: str | None = None,
) -> None:
    """Set an environment variable in a tmux session.

    Args:
        name: Environment variable name
        value: Environment variable value
        session_name: Session to set in (defaults to current)
        socket: Optional socket name
    """
    args = ["set-environment"]
    if session_name:
        args.extend(["-t", session_name])
    args.extend([name, value])
    run_tmux(*args, socket=socket)


def create_session(
    session_name: str,
    start_directory: Path | None = None,
    socket: str | None = None,
) -> None:
    """Create a new detached tmux session.

    Args:
        session_name: Name for the session
        start_directory: Starting directory
        socket: Optional socket name
    """
    args = ["new-session", "-d", "-s", session_name]
    if start_directory:
        args.extend(["-c", str(start_directory)])
    run_tmux(*args, socket=socket)

    # Propagate WT_CONFIG to the new session
    wt_config = os.environ.get("WT_CONFIG")
    if wt_config:
        set_environment("WT_CONFIG", wt_config, session_name, socket)


def create_window(
    window_name: str,
    session_name: str | None = None,
    start_directory: Path | None = None,
    socket: str | None = None,
) -> str:
    """Create a new window in a session.

    Args:
        window_name: Name for the window
        session_name: Session to create window in (defaults to current)
        start_directory: Starting directory for the window
        socket: Optional socket name

    Returns:
        Window target (session:window)
    """
    if session_name is None:
        session_name = get_current_session(socket)
        if session_name is None:
            raise TmuxError("Not in a tmux session and no session specified")

    # Ensure WT_CONFIG is set in the session before creating window
    wt_config = os.environ.get("WT_CONFIG")
    if wt_config:
        set_environment("WT_CONFIG", wt_config, session_name, socket)

    args = ["new-window", "-t", session_name, "-n", window_name]
    if start_directory:
        args.extend(["-c", str(start_directory)])
    run_tmux(*args, socket=socket)

    return f"{session_name}:{window_name}"


def split_window(
    target: str,
    horizontal: bool = False,
    start_directory: Path | None = None,
    socket: str | None = None,
) -> str:
    """Split a window/pane to create a new pane.

    Args:
        target: Window or pane target
        horizontal: If True, split horizontally (side by side)
        start_directory: Starting directory for new pane
        socket: Optional socket name

    Returns:
        New pane target
    """
    args = ["split-window", "-t", target]
    if horizontal:
        args.append("-h")
    if start_directory:
        args.extend(["-c", str(start_directory)])
    run_tmux(*args, socket=socket)

    # Get the new pane id
    result = run_tmux(
        "display-message", "-t", target, "-p", "#{pane_id}",
        socket=socket,
    )
    return result.stdout.strip()


def select_layout(target: str, layout: str, socket: str | None = None) -> None:
    """Set the layout for a window.

    Args:
        target: Window target
        layout: Layout name (main-horizontal, main-vertical, tiled, even-horizontal, even-vertical)
        socket: Optional socket name
    """
    run_tmux("select-layout", "-t", target, layout, socket=socket)


def send_keys(target: str, keys: str, socket: str | None = None) -> None:
    """Send keys to a tmux pane.

    Args:
        target: Pane target (e.g., "session:window.pane")
        keys: Keys to send
        socket: Optional socket name
    """
    run_tmux("send-keys", "-t", target, keys, "Enter", socket=socket)


def select_window(target: str, socket: str | None = None) -> None:
    """Select (switch to) a window.

    Args:
        target: Window target
        socket: Optional socket name
    """
    run_tmux("select-window", "-t", target, socket=socket)


def select_pane(target: str, socket: str | None = None) -> None:
    """Select a pane.

    Args:
        target: Pane target
        socket: Optional socket name
    """
    run_tmux("select-pane", "-t", target, socket=socket)


def launch_window(
    profile: dict[str, Any],
    topic: str,
    name: str,
    worktree_path: Path,
    session_name: str | None = None,
    socket: str | None = None,
) -> str:
    """Launch a window from a profile configuration.

    Creates a new window with panes according to the profile.
    Uses the first window definition from the profile.

    Args:
        profile: Profile configuration dict
        topic: Worktree topic
        name: Worktree name
        worktree_path: Path to the worktree
        session_name: Session to create window in (defaults to current)
        socket: Optional socket name

    Returns:
        Window target (session:window)
    """
    rendered = render_profile(profile, topic, name, worktree_path)
    window_name = f"{topic}-{name}"

    # Get the first window definition from profile
    windows = rendered.get("windows", [])
    if not windows:
        # Simple case: just create an empty window
        return create_window(window_name, session_name, worktree_path, socket)

    window_config = windows[0]
    layout = window_config.get("layout", "main-vertical")
    panes = window_config.get("panes", [])

    # Create the window
    window_target = create_window(window_name, session_name, worktree_path, socket)

    # Run commands in first pane if specified
    if panes:
        first_pane = panes[0]
        commands = first_pane.get("shell_command", [])
        for cmd in commands:
            send_keys(window_target, cmd, socket)

    # Create additional panes
    for i, pane_config in enumerate(panes[1:], start=1):
        # Split to create new pane
        split_window(window_target, horizontal=False, start_directory=worktree_path, socket=socket)
        pane_target = f"{window_target}.{i}"

        # Run commands in the new pane
        commands = pane_config.get("shell_command", [])
        for cmd in commands:
            send_keys(pane_target, cmd, socket)

    # Apply layout
    if layout and len(panes) > 1:
        select_layout(window_target, layout, socket)

    # Select first pane
    select_pane(f"{window_target}.0", socket)

    return window_target


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


def list_panes(target: str, socket: str | None = None) -> list[dict[str, str]]:
    """List panes in a session or window.

    Args:
        target: Session or window target
        socket: Optional socket name

    Returns:
        List of pane info dicts with keys: target, command
    """
    result = run_tmux(
        "list-panes", "-t", target, "-a",
        "-F", "#{session_name}:#{window_index}.#{pane_index}:#{pane_current_command}",
        socket=socket,
        check=False,
    )

    panes = []
    if result.returncode != 0:
        return panes

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


def find_claude_panes(target: str, socket: str | None = None) -> list[str]:
    """Find panes running Claude Code.

    Args:
        target: Session or window target
        socket: Optional socket name

    Returns:
        List of pane targets (e.g., "session:0.1")
    """
    panes = list_panes(target, socket)
    claude_panes = []
    for pane in panes:
        # Claude Code typically runs as 'claude' or 'node' process
        cmd = pane["command"].lower()
        if "claude" in cmd or "node" in cmd:
            claude_panes.append(pane["target"])
    return claude_panes


def close_claude_gracefully(
    target: str,
    socket: str | None = None,
    timeout: float = 5.0,
) -> None:
    """Gracefully close Claude Code by sending /exit.

    Args:
        target: Session or window target
        socket: Optional socket name
        timeout: Seconds to wait for Claude to exit
    """
    claude_panes = find_claude_panes(target, socket)

    for pane_target in claude_panes:
        send_keys(pane_target, "/exit", socket)

    # Wait for Claude to exit
    start = time.time()
    while time.time() - start < timeout:
        remaining = find_claude_panes(target, socket)
        if not remaining:
            break
        time.sleep(0.5)


def move_window(
    source_target: str,
    dest_session: str,
    socket: str | None = None,
) -> str:
    """Move a window from one session to another.

    Args:
        source_target: Source window target (session:window)
        dest_session: Destination session name
        socket: Optional socket name

    Returns:
        New window target in destination session
    """
    # Extract window name from source target
    parts = source_target.split(":")
    window_name = parts[1] if len(parts) > 1 else parts[0]

    # Move the window
    run_tmux(
        "move-window",
        "-s", source_target,
        "-t", dest_session,
        socket=socket,
    )

    return f"{dest_session}:{window_name}"


def list_windows(session_name: str, socket: str | None = None) -> list[dict[str, str]]:
    """List windows in a session.

    Args:
        session_name: Session to list windows from
        socket: Optional socket name

    Returns:
        List of window info dicts with keys: name, index, active
    """
    result = run_tmux(
        "list-windows",
        "-t", session_name,
        "-F", "#{window_index}:#{window_name}:#{window_active}",
        socket=socket,
        check=False,
    )

    windows = []
    if result.returncode != 0:
        return windows

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(":", 2)
        if len(parts) >= 3:
            windows.append({
                "index": parts[0],
                "name": parts[1],
                "active": parts[2] == "1",
            })

    return windows


def get_current_window(socket: str | None = None) -> str | None:
    """Get the current window target.

    Returns:
        Window target (session:window) or None if not in tmux
    """
    if not is_inside_tmux():
        return None
    result = run_tmux(
        "display-message", "-p", "#{session_name}:#{window_name}",
        socket=socket, check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def kill_window(target: str, socket: str | None = None) -> None:
    """Kill a tmux window.

    Args:
        target: Window target
        socket: Optional socket name
    """
    run_tmux("kill-window", "-t", target, socket=socket, check=False)


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
