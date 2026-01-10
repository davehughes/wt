"""Graphite CLI wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GraphiteError(Exception):
    """Raised when a graphite operation fails."""


DEFAULT_TIMEOUT = 10  # seconds


def run_gt(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
    capture_output: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """Run a graphite (gt) command.

    Args:
        *args: gt command and arguments
        cwd: Working directory for the command
        check: Whether to raise on non-zero exit
        capture_output: Whether to capture stdout/stderr
        timeout: Timeout in seconds (default 10)

    Returns:
        Completed process result

    Raises:
        GraphiteError: If command fails and check=True
    """
    cmd = ["gt", *args]
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
        return result
    except subprocess.CalledProcessError as e:
        raise GraphiteError(f"Graphite command failed: {' '.join(cmd)}\n{e.stderr}") from e
    except subprocess.TimeoutExpired:
        raise GraphiteError(f"Graphite command timed out: {' '.join(cmd)}") from None
    except FileNotFoundError:
        raise GraphiteError("Graphite CLI (gt) not found. Install from https://graphite.dev") from None


def is_available() -> bool:
    """Check if graphite CLI is available.

    Returns:
        True if gt command is available
    """
    try:
        subprocess.run(
            ["gt", "--version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def branch_track(branch: str, cwd: Path | None = None) -> None:
    """Track an existing git branch with graphite.

    Args:
        branch: Branch name to track
        cwd: Working directory

    Raises:
        GraphiteError: If tracking fails
    """
    run_gt("branch", "track", branch, cwd=cwd)


def branch_create(branch: str, cwd: Path | None = None) -> None:
    """Create a new branch with graphite.

    Args:
        branch: Branch name to create
        cwd: Working directory

    Raises:
        GraphiteError: If creation fails
    """
    run_gt("branch", "create", branch, cwd=cwd)


def branch_checkout(branch: str, cwd: Path | None = None) -> None:
    """Check out a branch using graphite.

    Args:
        branch: Branch name to check out
        cwd: Working directory

    Raises:
        GraphiteError: If checkout fails
    """
    run_gt("branch", "checkout", branch, cwd=cwd)


def is_tracked(branch: str, cwd: Path | None = None) -> bool:
    """Check if a branch is tracked by graphite.

    Args:
        branch: Branch name to check
        cwd: Working directory

    Returns:
        True if branch is tracked
    """
    # gt branch info returns non-zero if branch is not tracked
    result = run_gt("branch", "info", branch, cwd=cwd, check=False)
    return result.returncode == 0
