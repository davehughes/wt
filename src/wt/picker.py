"""Interactive selection using simple-term-menu."""

from __future__ import annotations

import sys
from typing import Any, Callable, TypeVar

from simple_term_menu import TerminalMenu

T = TypeVar("T")


class PickerError(Exception):
    """Raised when picker operation fails."""


class PickerUnavailable(PickerError):
    """Raised when interactive picker cannot be used (non-TTY)."""


def is_interactive() -> bool:
    """Check if we're in an interactive terminal environment."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def pick_one(
    items: list[T],
    format_item: Callable[[T], str],
    title: str | None = None,
) -> T:
    """Display an interactive picker and return the selected item.

    Args:
        items: List of items to choose from
        format_item: Function to convert item to display string
        title: Optional title shown above the menu

    Returns:
        The selected item from the list

    Raises:
        PickerUnavailable: If not in a TTY
        PickerError: If user cancels selection (Esc/q/Ctrl-C) or no items
    """
    if not items:
        raise PickerError("No items to select from")

    if not is_interactive():
        raise PickerUnavailable("Not in an interactive terminal")

    # Format items for display
    menu_entries = [format_item(item) for item in items]

    menu = TerminalMenu(
        menu_entries,
        title=title,
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("bg_gray", "fg_black"),
        search_key="/",
        search_highlight_style=("fg_yellow", "bold"),
    )

    selected_index = menu.show()

    if selected_index is None:
        raise PickerError("Selection cancelled")

    return items[selected_index]


def pick_session(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick a backgrounded session from a list.

    Args:
        sessions: List of session dicts from cmd_sessions()

    Returns:
        Selected session dict

    Raises:
        PickerUnavailable: If not in a TTY
        PickerError: If user cancels or no sessions
    """
    if not sessions:
        raise PickerError("No backgrounded sessions")

    def format_session(session: dict[str, Any]) -> str:
        return f"{session['topic']}/{session['wt_name']}"

    return pick_one(
        items=sessions,
        format_item=format_session,
        title="Select a backgrounded session:",
    )


def pick_worktree(worktrees: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick a worktree from a list.

    Args:
        worktrees: List of worktree dicts from cmd_list()

    Returns:
        Selected worktree dict

    Raises:
        PickerUnavailable: If not in a TTY
        PickerError: If user cancels or no worktrees
    """
    if not worktrees:
        raise PickerError("No worktrees found")

    def format_worktree(wt: dict[str, Any]) -> str:
        name = f"{wt['topic']}/{wt['name']}"
        status_parts = []

        if wt.get("is_backgrounded"):
            status_parts.append("bg")
        elif wt.get("has_window"):
            status_parts.append("active")

        if wt.get("branch") and not wt.get("branch_matches"):
            status_parts.append("branch mismatch")
        elif not wt.get("branch_exists"):
            status_parts.append("no branch")

        if status_parts:
            return f"{name:<30} [{', '.join(status_parts)}]"
        return name

    return pick_one(
        items=worktrees,
        format_item=format_worktree,
        title="Select a worktree:",
    )
