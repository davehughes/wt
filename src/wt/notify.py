"""Notification functions for Claude hook events."""

from __future__ import annotations

import os
import subprocess
import sys


def notify(
    title: str,
    message: str,
    urgency: str = "normal",
    worktree: str | None = None,
) -> None:
    """Send notification via all channels.

    Args:
        title: Notification title
        message: Notification message
        urgency: "normal" or "critical"
        worktree: Optional worktree name (topic/name) for context
    """
    if worktree:
        message = f"[{worktree}] {message}"

    # Run desktop notification (fast, async via osascript)
    desktop_notify(title, message, urgency)

    # tmux notification (only if in tmux)
    if os.environ.get("TMUX"):
        tmux_notify(title, message, urgency)

    if urgency == "critical":
        sound_notify()


def desktop_notify(title: str, message: str, urgency: str = "normal") -> None:
    """Send macOS notification center alert.

    Args:
        title: Notification title
        message: Notification message
        urgency: "normal" or "critical" (critical uses different sound)
    """
    if sys.platform != "darwin":
        return

    # Escape quotes in message and title
    escaped_title = title.replace('"', '\\"')
    escaped_message = message.replace('"', '\\"')

    script = f'display notification "{escaped_message}" with title "{escaped_title}"'
    if urgency == "critical":
        script += ' sound name "Ping"'

    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pass  # osascript not available


def tmux_notify(title: str, message: str, urgency: str = "normal") -> None:
    """Send tmux notification via display-message.

    Args:
        title: Notification title
        message: Notification message
        urgency: "normal" or "critical"
    """
    display_msg = f"{title}: {message}"

    try:
        cmd = ["tmux", "display-message", display_msg]
        subprocess.run(cmd, check=False, capture_output=True)
    except FileNotFoundError:
        pass  # tmux not available


def sound_notify() -> None:
    """Play alert sound (macOS only)."""
    if sys.platform != "darwin":
        # Fall back to terminal bell
        print("\a", end="", flush=True)
        return

    try:
        # Use system alert sound
        subprocess.run(
            ["afplay", "/System/Library/Sounds/Ping.aiff"],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        # Fall back to terminal bell
        print("\a", end="", flush=True)
