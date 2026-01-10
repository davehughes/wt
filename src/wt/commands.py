"""High-level command implementations."""

from __future__ import annotations

import os
from pathlib import Path

from wt import git, graphite, tmux
from wt.config import Config, ConfigError


def get_current_worktree_info(config: Config) -> tuple[str, str] | None:
    """Get topic/name for the current working directory if it's a managed worktree.

    Args:
        config: Application configuration

    Returns:
        Tuple of (topic, name) or None if not in a managed worktree
    """
    cwd = Path.cwd()
    worktrees_dir = config.worktrees_dir

    try:
        rel = cwd.relative_to(worktrees_dir)
        parts = rel.parts
        if len(parts) >= 2:
            return parts[0], parts[1]
    except ValueError:
        pass

    return None


def cmd_new(
    config: Config,
    name: str,
    from_branch: str | None = None,
) -> Path:
    """Create a new worktree and branch.

    Args:
        config: Application configuration
        name: Worktree name in "topic/name" format
        from_branch: Base branch (defaults to current branch)

    Returns:
        Path to the created worktree

    Raises:
        ConfigError: If name format is invalid
        git.GitError: If git operations fail
    """
    topic, wt_name = config.parse_worktree_name(name)
    branch_name = config.branch_name(topic, wt_name)
    worktree_path = config.worktree_path(topic, wt_name)

    # Ensure parent directory exists
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine base branch
    if from_branch is None:
        from_branch = git.get_current_branch()

    # Create worktree with new branch
    git.add_worktree(
        path=worktree_path,
        branch=branch_name,
        create_branch=True,
        base=from_branch,
    )

    # Track with graphite if available
    if graphite.is_available():
        try:
            graphite.branch_track(branch_name, cwd=worktree_path)
        except graphite.GraphiteError:
            # Non-fatal: graphite tracking can be done later with sync
            pass

    return worktree_path


def cmd_open(
    config: Config,
    name: str,
    profile: str | None = None,
) -> str:
    """Open a tmux session for a worktree.

    Args:
        config: Application configuration
        name: Worktree name in "topic/name" format
        profile: Profile name (defaults to config default)

    Returns:
        Session name

    Raises:
        ConfigError: If name format is invalid or worktree doesn't exist
        tmux.TmuxError: If tmux operations fail
    """
    topic, wt_name = config.parse_worktree_name(name)
    worktree_path = config.worktree_path(topic, wt_name)

    if not worktree_path.exists():
        raise ConfigError(f"Worktree not found: {worktree_path}")

    profile_name = profile or config.default_profile
    profile_path = config.profiles_dir / f"{profile_name}.yaml"

    if not profile_path.exists():
        raise ConfigError(f"Profile not found: {profile_path}")

    session_name = f"{topic}-{wt_name}"

    # Check if session already exists
    if tmux.session_exists(session_name):
        # Check if we're in tmux
        if os.environ.get("TMUX"):
            tmux.switch_client(session_name)
        else:
            tmux.attach_session(session_name)
        return session_name

    # Launch new session
    tmux.launch_session(
        profile_path=profile_path,
        topic=topic,
        name=wt_name,
        worktree_path=worktree_path,
    )

    # Attach or switch to session
    if os.environ.get("TMUX"):
        tmux.switch_client(session_name)
    else:
        tmux.attach_session(session_name)

    return session_name


def cmd_list(config: Config) -> list[dict[str, str | Path | bool]]:
    """List all managed worktrees.

    Args:
        config: Application configuration

    Returns:
        List of worktree info dicts
    """
    worktrees_dir = config.worktrees_dir
    result = []

    if not worktrees_dir.exists():
        return result

    # Get all git worktrees for cross-reference
    try:
        git_worktrees = {str(wt.path): wt for wt in git.list_worktrees()}
    except git.GitError:
        git_worktrees = {}

    # Scan worktrees directory
    for topic_dir in worktrees_dir.iterdir():
        if not topic_dir.is_dir():
            continue
        topic = topic_dir.name

        for wt_dir in topic_dir.iterdir():
            if not wt_dir.is_dir():
                continue
            name = wt_dir.name

            expected_branch = config.branch_name(topic, name)
            git_wt = git_worktrees.get(str(wt_dir))

            # Check branch status
            has_branch = git.branch_exists(expected_branch, path=wt_dir) if wt_dir.exists() else False
            actual_branch = None
            if git_wt and git_wt.branch:
                actual_branch = git_wt.branch.replace("refs/heads/", "")

            session_name = f"{topic}-{name}"
            has_session = tmux.session_exists(session_name)

            result.append({
                "topic": topic,
                "name": name,
                "path": wt_dir,
                "branch": actual_branch,
                "expected_branch": expected_branch,
                "branch_exists": has_branch,
                "branch_matches": actual_branch == expected_branch,
                "has_session": has_session,
            })

    return result


def cmd_sync(
    config: Config,
    name: str | None = None,
    sync_all: bool = False,
) -> list[str]:
    """Ensure git/graphite branches exist for worktrees.

    Args:
        config: Application configuration
        name: Specific worktree to sync (topic/name format)
        sync_all: Sync all worktrees

    Returns:
        List of actions taken

    Raises:
        ConfigError: If name format is invalid
    """
    actions = []

    if name:
        targets = [config.parse_worktree_name(name)]
    elif sync_all:
        worktrees = cmd_list(config)
        targets = [(wt["topic"], wt["name"]) for wt in worktrees]
    else:
        # Sync current worktree
        current = get_current_worktree_info(config)
        if current is None:
            raise ConfigError("Not in a managed worktree. Specify a name or use --all")
        targets = [current]

    for topic, wt_name in targets:
        branch_name = config.branch_name(topic, wt_name)
        worktree_path = config.worktree_path(topic, wt_name)

        if not worktree_path.exists():
            actions.append(f"Skipped {topic}/{wt_name}: worktree not found")
            continue

        # Check if branch exists
        if not git.branch_exists(branch_name, path=worktree_path):
            # Create branch from current HEAD
            git.create_branch(branch_name, path=worktree_path)
            actions.append(f"Created branch {branch_name}")

        # Track with graphite
        if graphite.is_available():
            if not graphite.is_tracked(branch_name, cwd=worktree_path):
                try:
                    graphite.branch_track(branch_name, cwd=worktree_path)
                    actions.append(f"Tracked {branch_name} with graphite")
                except graphite.GraphiteError as e:
                    actions.append(f"Failed to track {branch_name}: {e}")

    return actions


def cmd_close(config: Config) -> None:
    """Close the current tmux session gracefully.

    Args:
        config: Application configuration

    Raises:
        ConfigError: If not in a managed worktree or tmux session
    """
    current = get_current_worktree_info(config)
    if current is None:
        raise ConfigError("Not in a managed worktree")

    topic, name = current
    session_name = f"{topic}-{name}"

    if not tmux.session_exists(session_name):
        raise ConfigError(f"No tmux session found: {session_name}")

    # Gracefully close Claude Code
    tmux.close_claude_gracefully(session_name)

    # Kill the session
    tmux.kill_session(session_name)
