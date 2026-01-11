"""Graphite CLI wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GraphiteError(Exception):
    """Raised when a graphite operation fails."""


DEFAULT_TIMEOUT = 10  # seconds

# Cache for is_available result
_available_cache: bool | None = None


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
    # Always run non-interactively to avoid prompts hanging
    cmd = ["gt", "--no-interactive", *args]
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
    """Check if graphite CLI is available (cached).

    Returns:
        True if gt command is available
    """
    global _available_cache
    if _available_cache is not None:
        return _available_cache

    try:
        subprocess.run(
            ["gt", "--version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
        _available_cache = True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        _available_cache = False

    return _available_cache


def is_initialized(cwd: Path | None = None) -> bool:
    """Check if graphite is initialized in the repo.

    Args:
        cwd: Working directory

    Returns:
        True if graphite is initialized (has a trunk configured)
    """
    # gt log will fail if not initialized
    result = run_gt("log", "--short", cwd=cwd, check=False)
    # If it mentions "no trunk" or returns error, not initialized
    if result.returncode != 0:
        return False
    return True


def init_repo(trunk: str = "main", cwd: Path | None = None) -> None:
    """Initialize graphite in the repo.

    Args:
        trunk: Trunk branch name (default: main)
        cwd: Working directory

    Raises:
        GraphiteError: If initialization fails
    """
    run_gt("init", "--trunk", trunk, cwd=cwd)


def ensure_initialized(cwd: Path | None = None, trunk: str | None = None) -> bool:
    """Ensure graphite is initialized, auto-detecting trunk if needed.

    Args:
        cwd: Working directory
        trunk: Trunk branch name (if None, auto-detects main/master)

    Returns:
        True if initialized (or just initialized), False if couldn't initialize

    Raises:
        GraphiteError: If initialization fails
    """
    if is_initialized(cwd):
        return True

    # Use explicit trunk if provided
    if trunk:
        try:
            init_repo(trunk, cwd)
            return True
        except GraphiteError:
            return False

    # Try to auto-detect trunk branch
    import subprocess as sp
    for candidate in ["main", "master"]:
        try:
            result = sp.run(
                ["git", "rev-parse", "--verify", f"refs/heads/{candidate}"],
                cwd=cwd,
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                init_repo(candidate, cwd)
                return True
        except Exception:
            pass

    # Couldn't auto-detect, try main as fallback
    try:
        init_repo("main", cwd)
        return True
    except GraphiteError:
        return False


def branch_track(branch: str, parent: str | None = None, cwd: Path | None = None) -> None:
    """Track an existing git branch with graphite.

    Args:
        branch: Branch name to track
        parent: Parent branch (if None, uses --force to auto-detect)
        cwd: Working directory

    Raises:
        GraphiteError: If tracking fails
    """
    # Use 'gt track' (newer) instead of deprecated 'gt branch track'
    if parent:
        # Explicit parent - use --parent flag
        run_gt("track", "--parent", parent, branch, cwd=cwd)
    else:
        # --force auto-selects the most recent tracked ancestor as parent
        run_gt("track", "--force", branch, cwd=cwd)


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
