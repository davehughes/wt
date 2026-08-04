"""Graphite CLI wrapper."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from wt import git


class GraphiteError(Exception):
    """Raised when a graphite operation fails."""


DEFAULT_TIMEOUT = 10  # seconds

# Graphite stores its per-repo state in the *common* git directory, so it is
# shared by every worktree of a repo.
REPO_CONFIG_NAME = ".graphite_repo_config"


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


def run_gt_detached(*args: str, cwd: Path | None = None) -> None:
    """Start a graphite command and do not wait for it.

    Used for bookkeeping that is already best-effort (see branch_track), where
    blocking the caller buys nothing: the alternative to a backgrounded failure
    is a silently swallowed one.
    """
    try:
        subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            ["gt", "--no-interactive", *args],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, FileNotFoundError):
        pass


def is_available() -> bool:
    """Check if graphite CLI is available.

    Returns:
        True if gt command is on PATH
    """
    # A PATH lookup, not `gt --version`: spawning node to print a version
    # string costs ~0.6s, and this is called on nearly every command.
    return shutil.which("gt") is not None


def is_initialized(cwd: Path | None = None) -> bool:
    """Check if graphite is initialized in the repo.

    Args:
        cwd: Working directory

    Returns:
        True if graphite is initialized (has a trunk configured)
    """
    # Read graphite's own state file rather than shelling out: `gt log` costs
    # ~2s on a large repo, and this answers the same question exactly.
    try:
        config_path = git.get_git_common_dir(cwd) / REPO_CONFIG_NAME
        data = json.loads(config_path.read_text())
    except (OSError, ValueError, git.GitError):
        return False
    return bool(data.get("trunk"))


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


def branch_track(
    branch: str,
    parent: str | None = None,
    cwd: Path | None = None,
    detach: bool = False,
) -> None:
    """Track an existing git branch with graphite.

    Args:
        branch: Branch name to track
        parent: Parent branch (if None, uses --force to auto-detect)
        cwd: Working directory
        detach: Don't wait for gt to finish (fire-and-forget)

    Raises:
        GraphiteError: If tracking fails and detach is False
    """
    # Use 'gt track' (newer) instead of deprecated 'gt branch track'
    if parent:
        # Explicit parent - use --parent flag
        args = ("track", "--parent", parent, branch)
    else:
        # --force auto-selects the most recent tracked ancestor as parent
        args = ("track", "--force", branch)

    if detach:
        run_gt_detached(*args, cwd=cwd)
    else:
        run_gt(*args, cwd=cwd)


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
