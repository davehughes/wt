"""Git and worktree operations."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """Raised when a git operation fails."""


@dataclass
class Worktree:
    """Represents a git worktree."""

    path: Path
    branch: str | None
    head: str
    is_bare: bool = False
    is_detached: bool = False

    @classmethod
    def from_porcelain_line(cls, lines: list[str]) -> Worktree:
        """Parse a worktree from git worktree list --porcelain output.

        Args:
            lines: Lines for a single worktree entry

        Returns:
            Parsed Worktree instance
        """
        path = Path()
        head = ""
        branch: str | None = None
        is_bare = False
        is_detached = False

        for line in lines:
            if line.startswith("worktree "):
                path = Path(line[9:])
            elif line.startswith("HEAD "):
                head = line[5:]
            elif line.startswith("branch "):
                branch = line[7:]
            elif line == "bare":
                is_bare = True
            elif line == "detached":
                is_detached = True

        return cls(
            path=path,
            branch=branch,
            head=head,
            is_bare=is_bare,
            is_detached=is_detached,
        )


def run_git(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command.

    Args:
        *args: Git command and arguments
        cwd: Working directory for the command
        check: Whether to raise on non-zero exit
        capture_output: Whether to capture stdout/stderr

    Returns:
        Completed process result

    Raises:
        GitError: If command fails and check=True
    """
    cmd = ["git", *args]
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            capture_output=capture_output,
            text=True,
        )
        return result
    except subprocess.CalledProcessError as e:
        raise GitError(f"Git command failed: {' '.join(cmd)}\n{e.stderr}") from e


def get_repo_root(path: Path | None = None) -> Path:
    """Get the root directory of the git repository.

    Args:
        path: Starting path (defaults to cwd)

    Returns:
        Path to repository root

    Raises:
        GitError: If not in a git repository
    """
    result = run_git("rev-parse", "--show-toplevel", cwd=path)
    return Path(result.stdout.strip())


def get_main_repo_path(path: Path | None = None) -> Path:
    """Get the main repository path (resolves worktrees to their main repo).

    For a worktree, returns the main repo's working directory.
    For a main repo, returns its root.

    Args:
        path: Starting path (defaults to cwd)

    Returns:
        Path to main repository root

    Raises:
        GitError: If not in a git repository
    """
    # Get the common git directory (shared by all worktrees)
    result = run_git("rev-parse", "--git-common-dir", cwd=path)
    git_common_dir = Path(result.stdout.strip())

    # The common dir is the .git directory of the main repo
    # Its parent is the main repo working directory
    if git_common_dir.name == ".git":
        return git_common_dir.parent
    else:
        # Bare repo or unusual setup - fall back to repo root
        return get_repo_root(path)


def get_current_branch(path: Path | None = None) -> str | None:
    """Get the current branch name.

    Args:
        path: Path within the repository

    Returns:
        Branch name, or None if in detached HEAD state
    """
    result = run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=path)
    branch = result.stdout.strip()
    return None if branch == "HEAD" else branch


def branch_exists(branch: str, path: Path | None = None) -> bool:
    """Check if a branch exists.

    Args:
        branch: Branch name to check
        path: Path within the repository

    Returns:
        True if branch exists
    """
    result = run_git(
        "rev-parse", "--verify", f"refs/heads/{branch}",
        cwd=path,
        check=False,
    )
    return result.returncode == 0


def list_all_branches(path: Path | None = None) -> set[str]:
    """Get all branch names in the repository.

    Args:
        path: Path within the repository

    Returns:
        Set of branch names
    """
    try:
        result = run_git("branch", "--list", "--format=%(refname:short)", cwd=path)
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except GitError:
        return set()


def create_branch(branch: str, base: str | None = None, path: Path | None = None) -> None:
    """Create a new branch.

    Args:
        branch: Name for the new branch
        base: Base branch/commit (defaults to HEAD)
        path: Path within the repository

    Raises:
        GitError: If branch creation fails
    """
    args = ["branch", branch]
    if base:
        args.append(base)
    run_git(*args, cwd=path)


def rename_branch(old_branch: str, new_branch: str, path: Path | None = None) -> None:
    """Rename a git branch.

    Args:
        old_branch: Current branch name
        new_branch: New branch name
        path: Path within the repository

    Raises:
        GitError: If branch rename fails
    """
    run_git("branch", "-m", old_branch, new_branch, cwd=path)


def move_worktree(old_path: Path, new_path: Path, path: Path | None = None) -> None:
    """Move a worktree to a new location.

    Uses git worktree move to properly update internal git references.

    Args:
        old_path: Current worktree path
        new_path: New worktree path
        path: Path within the repository (for running git command)

    Raises:
        GitError: If worktree move fails
    """
    run_git("worktree", "move", str(old_path), str(new_path), cwd=path)


def list_worktrees(path: Path | None = None) -> list[Worktree]:
    """List all worktrees in the repository.

    Args:
        path: Path within the repository

    Returns:
        List of Worktree instances
    """
    result = run_git("worktree", "list", "--porcelain", cwd=path)

    worktrees = []
    current_lines: list[str] = []

    for line in result.stdout.split("\n"):
        if line == "":
            if current_lines:
                worktrees.append(Worktree.from_porcelain_line(current_lines))
                current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        worktrees.append(Worktree.from_porcelain_line(current_lines))

    return worktrees


def add_worktree(
    path: Path,
    branch: str,
    create_branch: bool = False,
    base: str | None = None,
    repo_path: Path | None = None,
) -> None:
    """Add a new worktree.

    Args:
        path: Path for the new worktree
        branch: Branch to check out
        create_branch: Whether to create the branch if it doesn't exist
        base: Base branch/commit for new branch
        repo_path: Path within the repository

    Raises:
        GitError: If worktree creation fails
    """
    args = ["worktree", "add"]

    if create_branch:
        # Check if branch already exists - if so, just check it out
        if branch_exists(branch, repo_path):
            args.append(str(path))
            args.append(branch)
        else:
            args.extend(["-b", branch])
            args.append(str(path))
            if base:
                args.append(base)
    else:
        args.append(str(path))
        args.append(branch)

    run_git(*args, cwd=repo_path)


def remove_worktree(path: Path, force: bool = False, repo_path: Path | None = None) -> None:
    """Remove a worktree.

    Args:
        path: Path of the worktree to remove
        force: Whether to force removal
        repo_path: Path within the repository

    Raises:
        GitError: If worktree removal fails
    """
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(path))
    run_git(*args, cwd=repo_path)


def worktree_path_for_branch(branch: str, path: Path | None = None) -> Path | None:
    """Find the worktree path for a given branch.

    Args:
        branch: Branch name to find
        path: Path within the repository

    Returns:
        Path to the worktree, or None if not found
    """
    for wt in list_worktrees(path):
        if wt.branch == f"refs/heads/{branch}" or wt.branch == branch:
            return wt.path
    return None


def has_uncommitted_changes(path: Path | None = None) -> bool:
    """Check if worktree has uncommitted changes.

    Args:
        path: Path within the repository

    Returns:
        True if there are uncommitted changes
    """
    result = run_git("status", "--porcelain", cwd=path, check=False)
    return bool(result.stdout.strip())


def delete_branch(branch: str, force: bool = False, path: Path | None = None) -> None:
    """Delete a git branch.

    Args:
        branch: Branch name to delete
        force: Whether to force delete (use -D instead of -d)
        path: Path within the repository

    Raises:
        GitError: If branch deletion fails
    """
    flag = "-D" if force else "-d"
    run_git("branch", flag, branch, cwd=path)


def prune_worktrees(path: Path | None = None) -> str:
    """Run git worktree prune to clean up stale entries.

    Args:
        path: Path within the repository

    Returns:
        Output from git worktree prune -v
    """
    result = run_git("worktree", "prune", "-v", cwd=path)
    return result.stdout.strip()
