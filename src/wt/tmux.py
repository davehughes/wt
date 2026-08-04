"""Tmux integration."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
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
    variables = {
        "topic": topic,
        "name": name,
        "worktree_path": str(worktree_path),
    }
    # _render_value rebuilds every container it touches, so the profile is never
    # mutated in place and there is nothing to copy defensively first.
    return _render_value(profile, variables)


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


@dataclass(frozen=True)
class WindowIndex:
    """Every window on the tmux server, captured in a single tmux call.

    Commands that need to answer several "does session X exist / does it hold
    window Y / what is Y's id" questions should load one of these instead of
    issuing a has-session or list-windows call per question.

    Ids are the useful output. Window names can contain '.', which tmux treats
    as the window/pane separator in target specs, so a name-based target like
    "session:topic/a.b" is misparsed. list-windows compares names directly
    (not via target parsing), so it can map a name to a '.'-safe window id.
    """

    # (session_name, window_name, window_id)
    windows: tuple[tuple[str, str, str], ...] = ()

    @classmethod
    def load(cls, socket: str | None = None) -> WindowIndex:
        """Capture the current set of windows across all sessions."""
        result = run_tmux(
            "list-windows", "-a",
            "-F", "#{session_name}\t#{window_name}\t#{window_id}",
            socket=socket, check=False,
        )
        if result.returncode != 0:
            # No server running, or it went away: an empty index is the honest
            # answer, and every query below degrades to "not found".
            return cls()

        rows = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) == 3:
                rows.append((parts[0], parts[1], parts[2]))
        return cls(tuple(rows))

    def has_session(self, session_name: str | None) -> bool:
        """Whether a session exists (a session always has at least one window)."""
        if session_name is None:
            return False
        return any(s == session_name for s, _, _ in self.windows)

    def id_for(self, window_name: str, session_name: str | None) -> str | None:
        """Window id for a window in a session, or None if not found."""
        if session_name is None:
            return None
        for s, n, wid in self.windows:
            if s == session_name and n == window_name:
                return wid
        return None

    def names_in(self, session_name: str | None) -> set[str]:
        """Window names in a session."""
        if session_name is None:
            return set()
        return {n for s, n, _ in self.windows if s == session_name}


def resolve_window_id(
    window_name: str,
    session_name: str,
    socket: str | None = None,
) -> str | None:
    """Resolve a window name to its tmux window id (e.g. "@3").

    Returns None if the window is not found.
    """
    return WindowIndex.load(socket).id_for(window_name, session_name)


def _safe_window_target(target: str, socket: str | None = None) -> str:
    """Convert a "session:window" target into a '.'-safe window-id target.

    A window name containing '.' would be misparsed by tmux (it treats '.' as
    the window/pane separator), so resolve it to the window id. Targets with no
    session prefix, no '.' in the window name, or that don't resolve to a known
    window (e.g. index-based "session:0") are returned unchanged.
    """
    if ":" not in target:
        return target
    session_name, window_name = target.split(":", 1)
    if "." not in window_name:
        return target
    window_id = resolve_window_id(window_name, session_name, socket)
    return window_id if window_id is not None else target


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
) -> tuple[str, str, str]:
    """Create a new window in a session.

    Captures the new window's ids directly from new-window so callers never
    have to look them up afterwards. Window names can contain '.', which tmux
    treats as the window/pane separator in target specs; looking the window up
    by name (or relying on the session's "current" window) is therefore
    ambiguous and racy. Ids (e.g. "@1", "%1") never contain '.'.

    Args:
        window_name: Name for the window
        session_name: Session to create window in (defaults to current)
        start_directory: Starting directory for the window
        socket: Optional socket name

    Returns:
        Tuple of (window_target, window_id, active_pane_id)
    """
    if session_name is None:
        session_name = get_current_session(socket)
        if session_name is None:
            raise TmuxError("Not in a tmux session and no session specified")

    # Ensure WT_CONFIG is set in the session before creating window
    wt_config = os.environ.get("WT_CONFIG")
    if wt_config:
        set_environment("WT_CONFIG", wt_config, session_name, socket)

    args = [
        "new-window", "-a", "-t", session_name, "-n", window_name,
        "-P", "-F", "#{window_id}\t#{pane_id}",
    ]
    if start_directory:
        args.extend(["-c", str(start_directory)])
    result = run_tmux(*args, socket=socket)

    window_id, pane_id = result.stdout.strip().split("\t")
    return f"{session_name}:{window_name}", window_id, pane_id


def escape_keys(keys: str) -> str:
    """Make a key sequence safe to pass to send-keys as one argument.

    tmux reads a ';' at the end of an argument as a command separator, so
    send-keys with "echo one;" would treat the following "Enter" as a command of
    its own ("unknown command: Enter"). Escaping the trailing ';' sends it
    literally.

    Only the trailing ';' may be escaped: mid-string, tmux passes the backslash
    through verbatim, so "a\\; b" would reach the shell with the backslash in it.
    """
    if keys.endswith(";"):
        return keys[:-1] + "\\;"
    return keys


def send_keys(target: str, keys: str, socket: str | None = None) -> None:
    """Send keys to a tmux pane.

    Args:
        target: Pane target (e.g., "session:window.pane")
        keys: Keys to send
        socket: Optional socket name
    """
    run_tmux("send-keys", "-t", target, escape_keys(keys), "Enter", socket=socket)


def select_window(target: str, socket: str | None = None) -> None:
    """Select (switch to) a window.

    Args:
        target: Window target
        socket: Optional socket name
    """
    run_tmux("select-window", "-t", _safe_window_target(target, socket), socket=socket)


def select_pane(target: str, socket: str | None = None) -> None:
    """Select a pane.

    Args:
        target: Pane target
        socket: Optional socket name
    """
    run_tmux("select-pane", "-t", target, socket=socket)


def get_window_ids(target: str, socket: str | None = None) -> tuple[str, str]:
    """Get stable ids for a window target's window and active pane.

    Window names can contain '.', which tmux treats as the window/pane
    separator in target specs, making name-based targets ambiguous. Window
    and pane ids (e.g. "@1", "%1") never contain '.', so they are safe to use.
    Pass an unambiguous target (a session name, or a "session:index" target)
    rather than a name-based one.

    Args:
        target: Window target to inspect (e.g. "session" or "session:0")
        socket: Optional socket name

    Returns:
        Tuple of (window_id, active_pane_id)
    """
    result = run_tmux(
        "display-message", "-t", target, "-p", "#{window_id}\t#{pane_id}",
        socket=socket,
    )
    window_id, pane_id = result.stdout.strip().split("\t")
    return window_id, pane_id


def setup_panes(
    window_id: str,
    first_pane_id: str,
    panes: list[dict[str, Any]],
    layout: str,
    worktree_path: Path,
    socket: str | None = None,
) -> None:
    """Run shell commands and create panes in a window, targeting by id.

    Args:
        window_id: Window id (e.g. "@1") to target for splits/layout
        first_pane_id: Pane id (e.g. "%1") of the window's initial pane
        panes: List of pane configs, each with optional "shell_command" list
        layout: tmux layout to apply when there is more than one pane
        worktree_path: Starting directory for new panes
        socket: Optional socket name
    """
    if not panes:
        return

    # Create every extra pane in one tmux invocation. Chained commands are
    # separated by a standalone ";" argument, and each split's -P prints its new
    # pane id, so stdout comes back as one id per split, in order.
    #
    # The interleaved re-tile keeps panes evenly sized: otherwise repeated
    # top/bottom splits halve the active pane until it runs out of room ("no
    # space for new pane") on shorter windows.
    pane_ids = [first_pane_id]
    if len(panes) > 1:
        args: list[str] = []
        for _ in panes[1:]:
            if args:
                args.append(";")
            args.extend(["split-window", "-t", window_id, "-P", "-F", "#{pane_id}"])
            if worktree_path:
                args.extend(["-c", str(worktree_path)])
            args.extend([";", "select-layout", "-t", window_id, "tiled"])
        result = run_tmux(*args, socket=socket)
        pane_ids.extend(line for line in result.stdout.strip().split("\n") if line)

    # Then one more invocation for every pane's shell commands, plus the final
    # layout and focus. escape_keys keeps a command that ends in ';' from being
    # read as a command separator here.
    args = []
    for pane_id, pane_config in zip(pane_ids, panes):
        # `shell_command:` with nothing after it parses as None, not [].
        for cmd in pane_config.get("shell_command") or []:
            if args:
                args.append(";")
            args.extend(["send-keys", "-t", pane_id, escape_keys(cmd), "Enter"])

    if layout and len(panes) > 1:
        if args:
            args.append(";")
        args.extend(["select-layout", "-t", window_id, layout])

    if args:
        args.append(";")
    args.extend(["select-pane", "-t", first_pane_id])

    run_tmux(*args, socket=socket)


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

    Profile format:
        layout: main-vertical
        panes:
          - shell_command: [cd {{worktree_path}}]
          - shell_command: [cd {{worktree_path}}, claude]

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
    window_name = f"{topic}/{name}"

    layout = rendered.get("layout", "main-vertical")
    panes = rendered.get("panes", [])

    # Create the window, capturing stable ids for the new window/pane. Window
    # names may contain '.', which tmux treats as the window/pane separator in
    # target specs, so we target by id rather than by name.
    window_target, window_id, first_pane_id = create_window(
        window_name, session_name, worktree_path, socket
    )

    setup_panes(window_id, first_pane_id, panes, layout, worktree_path, socket)

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
        "list-panes", "-t", _safe_window_target(target, socket),
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


def is_claude_command(command: str) -> bool:
    """Whether a pane's current command looks like Claude Code.

    Claude Code runs as a node process, so this also matches unrelated node
    processes; it is a heuristic for "worth inspecting", not proof.
    """
    cmd = command.lower()
    return "claude" in cmd or "node" in cmd


def find_claude_panes(target: str, socket: str | None = None) -> list[str]:
    """Find panes running Claude Code.

    Args:
        target: Session or window target
        socket: Optional socket name

    Returns:
        List of pane targets (e.g., "session:0.1")
    """
    return [
        pane["target"]
        for pane in list_panes(target, socket)
        if is_claude_command(pane["command"])
    ]


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


def capture_pane(
    target: str,
    lines: int = 10,
    socket: str | None = None,
) -> str:
    """Capture the content of a tmux pane.

    Args:
        target: Pane target (session:window.pane)
        lines: Number of lines from the end to capture
        socket: Optional socket name

    Returns:
        Captured pane content as string
    """
    result = run_tmux(
        "capture-pane", "-t", target, "-p", "-J",
        socket=socket,
        check=False,
    )
    if result.returncode != 0:
        return ""

    content = result.stdout
    # Return last N lines
    all_lines = content.splitlines()
    return "\n".join(all_lines[-lines:]) if all_lines else ""


def get_claude_status(
    target: str,
    socket: str | None = None,
) -> str:
    """Get the status of Claude Code in a window.

    Inspects pane content to determine if Claude is:
    - "idle": Waiting for user input (shows prompt)
    - "working": Actively processing
    - "permission": Waiting for permission
    - "unknown": Claude not found or status unclear

    Args:
        target: Window target (session:window)
        socket: Optional socket name

    Returns:
        Status string: "idle", "working", "permission", or "unknown"
    """
    claude_panes = find_claude_panes(target, socket)
    if not claude_panes:
        return "unknown"

    # Check the first Claude pane found
    pane_target = claude_panes[0]
    content = capture_pane(pane_target, lines=15, socket=socket)

    if not content:
        return "unknown"

    # Check last few lines for status indicators
    lines = content.splitlines()
    last_lines = lines[-5:] if len(lines) >= 5 else lines
    last_content = "\n".join(last_lines)

    # Check for idle indicators (prompt waiting for input)
    # Claude shows ❯ prompt and "? for shortcuts" when waiting for input
    idle_indicators = [
        "? for shortcuts",  # Help hint shown when idle
        "↵ send",           # Waiting for user to press enter
        "⏵⏵ accept edits",  # Waiting for user to accept/reject edits
    ]
    for indicator in idle_indicators:
        if indicator in last_content:
            return "idle"

    # Check for the input prompt line: "❯" anywhere means waiting for input
    for line in reversed(last_lines):
        stripped = line.strip()
        if stripped.startswith("❯"):
            return "idle"

    # Check for permission prompts
    permission_patterns = ["Allow", "Deny", "allow this", "approve"]
    for pattern in permission_patterns:
        if pattern.lower() in content.lower():
            return "permission"

    # Check for working indicators
    working_patterns = [
        "Thinking",
        "Reading",
        "Writing",
        "Searching",
        "Running",
        "...",
        "━",  # Progress bar character
    ]
    for pattern in working_patterns:
        if pattern in content:
            return "working"

    # Default to working if Claude is present but status unclear
    return "working"


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

    # Move the window (resolve to a '.'-safe id since names may contain '.')
    run_tmux(
        "move-window",
        "-s", _safe_window_target(source_target, socket),
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


def get_current_window_id(socket: str | None = None) -> str | None:
    """Get the current window's id (e.g. "@3").

    Returns:
        Window id, or None if not in tmux
    """
    if not is_inside_tmux():
        return None
    result = run_tmux("display-message", "-p", "#{window_id}", socket=socket, check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def kill_window(target: str, socket: str | None = None) -> None:
    """Kill a tmux window.

    Args:
        target: Window target
        socket: Optional socket name
    """
    run_tmux("kill-window", "-t", _safe_window_target(target, socket), socket=socket, check=False)


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
