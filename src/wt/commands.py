"""High-level command implementations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from wt import git, graphite, tmux
from wt.config import Config, ConfigError

# Background session for keeping worktree windows running
BACKGROUND_SESSION = "wt-bg"


def link_template(config: Config, worktree_path: Path) -> list[str]:
    """Symlink template directory contents into a worktree.

    Creates symlinks in the worktree for each item in the template directory.
    Existing symlinks pointing to the template are updated; other existing
    files/directories are skipped with a warning.

    Args:
        config: Application configuration
        worktree_path: Path to the worktree

    Returns:
        List of actions taken (for logging)
    """
    actions = []

    if config.template_dir is None or not config.template_dir.exists():
        return actions

    for item in config.template_dir.iterdir():
        target = worktree_path / item.name
        source = item

        if target.is_symlink():
            # Check if it already points to the right place
            if target.resolve() == source.resolve():
                actions.append(f"Already linked: {item.name}")
                continue
            # Remove old symlink and recreate
            target.unlink()
            target.symlink_to(source)
            actions.append(f"Updated link: {item.name}")
        elif target.exists():
            # Don't overwrite existing files/directories
            actions.append(f"Skipped (exists): {item.name}")
        else:
            # Create new symlink
            target.symlink_to(source)
            actions.append(f"Linked: {item.name}")

    return actions


def get_current_worktree_info(config: Config) -> tuple[str, str] | None:
    """Get topic/name for the current working directory if it's a managed worktree.

    Worktrees are stored at $ROOT/<topic>/<name>.

    Args:
        config: Application configuration

    Returns:
        Tuple of (topic, name) or None if not in a managed worktree
    """
    cwd = Path.cwd()

    try:
        rel = cwd.relative_to(config.root)
        parts = rel.parts
        if len(parts) >= 2:
            return parts[0], parts[1]
    except ValueError:
        pass

    return None


def ensure_worktree(
    config: Config,
    name: str,
    from_branch: str | None = None,
) -> tuple[Path, bool]:
    """Ensure a worktree exists, creating it if necessary.

    Args:
        config: Application configuration
        name: Worktree name in "topic/name" format
        from_branch: Base branch for new worktree (defaults to current branch)

    Returns:
        Tuple of (worktree_path, was_created)

    Raises:
        ConfigError: If name format is invalid
        git.GitError: If git operations fail
    """
    topic, wt_name = config.parse_worktree_name(name)
    branch_name = config.branch_name(topic, wt_name)
    worktree_path = config.worktree_path(topic, wt_name)

    if worktree_path.exists():
        return worktree_path, False

    # Ensure parent directory exists
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine base branch
    if from_branch is None:
        from_branch = git.get_current_branch()

    # Create worktree (add_worktree handles existing branches gracefully)
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

    # Link template directory contents
    link_template(config, worktree_path)

    return worktree_path, True


def cmd_open(
    config: Config,
    name: str,
    profile: str | None = None,
    from_branch: str | None = None,
) -> tuple[str, bool]:
    """Open a tmux window for a worktree, creating it if necessary.

    If inside tmux, creates a new window in the current session.
    If outside tmux, creates a new session with a window and attaches.

    Args:
        config: Application configuration
        name: Worktree name in "topic/name" format
        profile: Profile name (defaults to config default)
        from_branch: Base branch if creating new worktree (defaults to current branch)

    Returns:
        Tuple of (window_target, was_created) where was_created indicates
        if a new worktree was created

    Raises:
        ConfigError: If name format is invalid
        git.GitError: If git operations fail
        tmux.TmuxError: If tmux operations fail
    """
    topic, wt_name = config.parse_worktree_name(name)

    # Ensure worktree exists, creating if necessary
    worktree_path, was_created = ensure_worktree(config, name, from_branch)

    profile_config = config.get_profile(profile)
    window_name = f"{topic}-{wt_name}"

    # Get current session if in tmux
    current_session = tmux.get_current_session()

    if current_session:
        # Inside tmux - check if window already exists
        if tmux.window_exists(window_name, current_session):
            tmux.select_window(f"{current_session}:{window_name}")
            return f"{current_session}:{window_name}", was_created

        # Create new window in current session
        window_target = tmux.launch_window(
            profile=profile_config,
            topic=topic,
            name=wt_name,
            worktree_path=worktree_path,
            session_name=current_session,
        )
        return window_target, was_created
    else:
        # Outside tmux - need to create or attach to a session
        session_name = "wt"  # Default session name for wt

        if not tmux.session_exists(session_name):
            # Create new session
            tmux.create_session(session_name, worktree_path)

            # Rename the default window
            tmux.run_tmux("rename-window", "-t", f"{session_name}:0", window_name)

            # Set up panes in the window
            window_target = f"{session_name}:{window_name}"
            profile_rendered = tmux.render_profile(profile_config, topic, wt_name, worktree_path)
            windows = profile_rendered.get("windows", [])
            if windows:
                window_config = windows[0]
                panes = window_config.get("panes", [])
                layout = window_config.get("layout", "main-vertical")

                # Run commands in first pane
                if panes:
                    for cmd in panes[0].get("shell_command", []):
                        tmux.send_keys(window_target, cmd)

                # Create additional panes
                for i, pane_config in enumerate(panes[1:], start=1):
                    tmux.split_window(window_target, start_directory=worktree_path)
                    pane_target = f"{window_target}.{i}"
                    for cmd in pane_config.get("shell_command", []):
                        tmux.send_keys(pane_target, cmd)

                # Apply layout
                if layout and len(panes) > 1:
                    tmux.select_layout(window_target, layout)

                tmux.select_pane(f"{window_target}.0")
        else:
            # Session exists, check for window
            if tmux.window_exists(window_name, session_name):
                window_target = f"{session_name}:{window_name}"
            else:
                # Create new window
                window_target = tmux.launch_window(
                    profile=profile_config,
                    topic=topic,
                    name=wt_name,
                    worktree_path=worktree_path,
                    session_name=session_name,
                )

        # Attach to session
        tmux.attach_session(session_name)
        return window_target, was_created


def cmd_list(config: Config) -> list[dict[str, str | Path | bool]]:
    """List all managed worktrees.

    Scans $ROOT/<topic>/<name> for worktrees.

    Args:
        config: Application configuration

    Returns:
        List of worktree info dicts
    """
    result = []

    if not config.root.exists():
        return result

    # Get all git worktrees for cross-reference
    try:
        git_worktrees = {str(wt.path): wt for wt in git.list_worktrees()}
    except git.GitError:
        git_worktrees = {}

    # Scan root directory for topic/name structure
    for topic_dir in config.root.iterdir():
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

            window_name = f"{topic}-{name}"
            # Check if window exists in current session, 'wt' session, or background session
            current_session = tmux.get_current_session()
            has_window = False
            is_backgrounded = False
            if current_session:
                has_window = tmux.window_exists(window_name, current_session)
            if not has_window and tmux.session_exists("wt"):
                has_window = tmux.window_exists(window_name, "wt")
            if not has_window and tmux.session_exists(BACKGROUND_SESSION):
                is_backgrounded = tmux.window_exists(window_name, BACKGROUND_SESSION)
                has_window = is_backgrounded

            result.append({
                "topic": topic,
                "name": name,
                "path": wt_dir,
                "branch": actual_branch,
                "expected_branch": expected_branch,
                "branch_exists": has_branch,
                "branch_matches": actual_branch == expected_branch,
                "has_window": has_window,
                "is_backgrounded": is_backgrounded,
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


def cmd_link(
    config: Config,
    name: str | None = None,
) -> list[str]:
    """Link template directory contents into a worktree.

    Args:
        config: Application configuration
        name: Worktree name in "topic/name" format (defaults to current)

    Returns:
        List of actions taken

    Raises:
        ConfigError: If name format is invalid or not in a worktree
    """
    if name:
        topic, wt_name = config.parse_worktree_name(name)
        worktree_path = config.worktree_path(topic, wt_name)
    else:
        current = get_current_worktree_info(config)
        if current is None:
            raise ConfigError("Not in a managed worktree. Specify a name or cd to a worktree.")
        topic, wt_name = current
        worktree_path = config.worktree_path(topic, wt_name)

    if not worktree_path.exists():
        raise ConfigError(f"Worktree not found: {worktree_path}")

    if config.template_dir is None or not config.template_dir.exists():
        raise ConfigError(f"Template directory not found: {config.template_dir}")

    return link_template(config, worktree_path)


def cmd_close(config: Config) -> None:
    """Close the current tmux window gracefully.

    Args:
        config: Application configuration

    Raises:
        ConfigError: If not in a managed worktree or tmux window
    """
    current = get_current_worktree_info(config)
    if current is None:
        raise ConfigError("Not in a managed worktree")

    topic, name = current
    window_name = f"{topic}-{name}"

    # Find which session has this window
    current_session = tmux.get_current_session()
    window_target = None

    if current_session and tmux.window_exists(window_name, current_session):
        window_target = f"{current_session}:{window_name}"
    elif tmux.session_exists("wt") and tmux.window_exists(window_name, "wt"):
        window_target = f"wt:{window_name}"

    if window_target is None:
        raise ConfigError(f"No tmux window found: {window_name}")

    # Gracefully close Claude Code
    tmux.close_claude_gracefully(window_target)

    # Kill the window
    tmux.kill_window(window_target)


def cmd_sessions(config: Config) -> list[dict[str, str]]:
    """List all backgrounded worktree windows.

    Args:
        config: Application configuration

    Returns:
        List of session info dicts with keys: name, topic, wt_name
    """
    result = []

    if not tmux.session_exists(BACKGROUND_SESSION):
        return result

    windows = tmux.list_windows(BACKGROUND_SESSION)
    for window in windows:
        window_name = window["name"]
        # Parse topic-name format
        parts = window_name.split("-", 1)
        if len(parts) == 2:
            topic, wt_name = parts
        else:
            topic = window_name
            wt_name = ""

        result.append({
            "name": window_name,
            "topic": topic,
            "wt_name": wt_name,
        })

    return result


def cmd_background(config: Config) -> str:
    """Send the current worktree window to the background session.

    Args:
        config: Application configuration

    Returns:
        Name of the window that was backgrounded

    Raises:
        ConfigError: If not in a managed worktree or tmux
    """
    if not tmux.is_inside_tmux():
        raise ConfigError("Not inside tmux")

    current = get_current_worktree_info(config)
    if current is None:
        raise ConfigError("Not in a managed worktree")

    topic, name = current
    window_name = f"{topic}-{name}"

    current_session = tmux.get_current_session()
    if current_session is None:
        raise ConfigError("Could not determine current tmux session")

    # Check window exists in current session
    if not tmux.window_exists(window_name, current_session):
        raise ConfigError(f"Window {window_name} not found in session {current_session}")

    # Ensure background session exists
    if not tmux.session_exists(BACKGROUND_SESSION):
        # Create background session with a placeholder window
        tmux.create_session(BACKGROUND_SESSION)

    # Move window to background session
    source_target = f"{current_session}:{window_name}"
    tmux.move_window(source_target, BACKGROUND_SESSION)

    return window_name


def cmd_foreground(config: Config, name: str) -> str:
    """Bring a backgrounded worktree window to the foreground.

    Args:
        config: Application configuration
        name: Worktree name in "topic/name" format or window name "topic-name"

    Returns:
        The window target in the current session

    Raises:
        ConfigError: If window not found in background session
    """
    # Convert topic/name to window name format if needed
    if "/" in name:
        topic, wt_name = config.parse_worktree_name(name)
        window_name = f"{topic}-{wt_name}"
    else:
        window_name = name

    # Check background session exists
    if not tmux.session_exists(BACKGROUND_SESSION):
        raise ConfigError("No backgrounded sessions")

    # Check window exists in background session
    if not tmux.window_exists(window_name, BACKGROUND_SESSION):
        raise ConfigError(f"Window {window_name} not found in background session")

    # Determine target session
    current_session = tmux.get_current_session()
    if current_session:
        target_session = current_session
    else:
        # Outside tmux - use or create 'wt' session
        target_session = "wt"
        if not tmux.session_exists(target_session):
            tmux.create_session(target_session)

    # Move window from background to target session
    source_target = f"{BACKGROUND_SESSION}:{window_name}"
    new_target = tmux.move_window(source_target, target_session)

    # Select the window if we're inside tmux
    if tmux.is_inside_tmux():
        tmux.select_window(new_target)

    return new_target


def cmd_switch(config: Config, name: str, close: bool = False) -> str:
    """Background (or close) current window and foreground target window.

    Args:
        config: Configuration
        name: Target window name (topic/name or topic-name format)
        close: If True, close current window instead of backgrounding

    Returns:
        The foregrounded window target
    """
    # Close or background current window first
    if close:
        cmd_close(config)
    else:
        cmd_background(config)

    # Then foreground the target
    return cmd_foreground(config, name)


@dataclass
class StatusInfo:
    """Status information about the current state."""

    # Config info
    config_path: str
    branch_prefix: str
    root: Path
    default_profile: str
    available_profiles: list[str]
    template_dir: Path | None

    # Current worktree info (if in a managed worktree)
    in_managed_worktree: bool
    topic: str | None = None
    name: str | None = None
    worktree_path: Path | None = None
    expected_branch: str | None = None
    current_branch: str | None = None
    has_tmux_window: bool = False
    graphite_available: bool = False


def cmd_status(config: Config, config_path: str | None = None) -> StatusInfo:
    """Get status information about config and current worktree.

    Args:
        config: Application configuration
        config_path: Path to the config file (for display)

    Returns:
        StatusInfo with current state
    """
    import os
    from wt.config import DEFAULT_CONFIG_PATH

    # Determine config path for display
    if config_path is None:
        env_path = os.environ.get("WT_CONFIG")
        config_path = env_path if env_path else str(DEFAULT_CONFIG_PATH)

    # Get current worktree info
    current = get_current_worktree_info(config)

    status = StatusInfo(
        config_path=config_path,
        branch_prefix=config.branch_prefix,
        root=config.root,
        default_profile=config.default_profile,
        available_profiles=list(config.profiles.keys()),
        template_dir=config.template_dir,
        in_managed_worktree=current is not None,
        graphite_available=graphite.is_available(),
    )

    if current is not None:
        topic, name = current
        status.topic = topic
        status.name = name
        status.worktree_path = config.worktree_path(topic, name)
        status.expected_branch = config.branch_name(topic, name)

        # Get current git branch
        try:
            status.current_branch = git.get_current_branch(status.worktree_path)
        except git.GitError:
            pass

        # Check tmux window
        window_name = f"{topic}-{name}"
        current_session = tmux.get_current_session()
        has_window = False
        if current_session:
            has_window = tmux.window_exists(window_name, current_session)
        if not has_window and tmux.session_exists("wt"):
            has_window = tmux.window_exists(window_name, "wt")
        status.has_tmux_window = has_window

    return status
