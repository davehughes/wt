"""High-level command implementations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from wt import git, graphite, tmux
from wt.config import Config, ConfigError

# Background session for keeping worktree windows running
BACKGROUND_SESSION = "wt-bg"
# Placeholder window name (filtered from listings)
PLACEHOLDER_WINDOW = "_placeholder"


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

    # Determine main repo path
    repo_path = config.main_repo
    if repo_path is None:
        # Try to get repo from current directory
        try:
            repo_path = git.get_repo_root()
        except git.GitError:
            pass

    if repo_path is None:
        # Try to find main repo from an existing worktree
        if config.root.exists():
            for topic_dir in config.root.iterdir():
                if not topic_dir.is_dir():
                    continue
                for wt_dir in topic_dir.iterdir():
                    git_file = wt_dir / ".git"
                    if git_file.is_file():
                        # Parse gitdir from .git file to find main repo
                        content = git_file.read_text().strip()
                        if content.startswith("gitdir:"):
                            gitdir = content[7:].strip()
                            # gitdir points to .git/worktrees/name, main repo is parent of .git
                            if "/worktrees/" in gitdir:
                                main_git = gitdir.split("/worktrees/")[0]
                                repo_path = Path(main_git).parent
                                break
                if repo_path:
                    break

    if repo_path is None:
        raise ConfigError("Cannot determine main git repository. Set 'main_repo' in config or run from within a git repo.")

    # Determine base branch
    if from_branch is None:
        try:
            from_branch = git.get_current_branch()
        except git.GitError:
            # Not in a git repo - use default branch from main repo
            for default in ["main", "master"]:
                if git.branch_exists(default, path=repo_path):
                    from_branch = default
                    break

        if from_branch is None:
            from_branch = "main"  # Last resort fallback

    # Create worktree (add_worktree handles existing branches gracefully)
    git.add_worktree(
        path=worktree_path,
        branch=branch_name,
        create_branch=True,
        base=from_branch,
        repo_path=repo_path,
    )

    # Track with graphite if available
    # Use main repo path for graphite (worktrees don't share graphite state)
    if graphite.is_available():
        try:
            main_repo = git.get_main_repo_path(worktree_path)
            # Ensure graphite is initialized before tracking
            if graphite.ensure_initialized(cwd=main_repo, trunk=config.trunk):
                # Use from_branch as parent since that's what we branched from
                graphite.branch_track(branch_name, parent=from_branch, cwd=main_repo)
        except (graphite.GraphiteError, git.GitError):
            # Non-fatal: graphite tracking can be done later with sync
            pass

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
    window_name = f"{topic}/{wt_name}"

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

    # Get all git worktrees for cross-reference (single git call)
    try:
        git_worktrees = {str(wt.path): wt for wt in git.list_worktrees()}
    except git.GitError:
        git_worktrees = {}

    # Get all branches upfront (single git call)
    try:
        all_branches = git.list_all_branches(path=config.main_repo or config.root)
    except git.GitError:
        all_branches = set()

    # Get tmux window info upfront (minimize tmux calls)
    current_session = tmux.get_current_session()
    current_windows = {w["name"] for w in tmux.list_windows(current_session)} if current_session else set()
    wt_windows = {w["name"] for w in tmux.list_windows("wt")} if tmux.session_exists("wt") else set()
    bg_windows = {w["name"] for w in tmux.list_windows(BACKGROUND_SESSION) if w["name"] != PLACEHOLDER_WINDOW} if tmux.session_exists(BACKGROUND_SESSION) else set()

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

            # Check branch status using cached branch list
            has_branch = expected_branch in all_branches
            actual_branch = None
            if git_wt and git_wt.branch:
                actual_branch = git_wt.branch.replace("refs/heads/", "")

            window_name = f"{topic}/{name}"
            # Check windows using cached window lists
            has_window = window_name in current_windows or window_name in wt_windows
            is_backgrounded = window_name in bg_windows
            if is_backgrounded:
                has_window = True

            # Get Claude status if window exists
            claude_status = None
            if has_window:
                # Determine which session has the window
                if is_backgrounded:
                    window_target = f"{BACKGROUND_SESSION}:{window_name}"
                elif window_name in wt_windows:
                    window_target = f"wt:{window_name}"
                else:
                    window_target = f"{current_session}:{window_name}"
                claude_status = tmux.get_claude_status(window_target)

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
                "claude_status": claude_status,
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
        # Use main repo path for graphite (worktrees don't share graphite state)
        if graphite.is_available():
            try:
                main_repo = git.get_main_repo_path(worktree_path)
            except git.GitError:
                actions.append(f"Failed to get main repo for {topic}/{wt_name}")
                continue

            # Ensure graphite is initialized
            if not graphite.is_initialized(cwd=main_repo):
                if graphite.ensure_initialized(cwd=main_repo, trunk=config.trunk):
                    actions.append("Initialized graphite")
                else:
                    actions.append("Failed to initialize graphite")
                    continue

            if not graphite.is_tracked(branch_name, cwd=main_repo):
                try:
                    # Try auto-detect parent first
                    graphite.branch_track(branch_name, cwd=main_repo)
                    actions.append(f"Tracked {branch_name} with graphite")
                except graphite.GraphiteError:
                    # Auto-detect failed, try with trunk as parent
                    # Use config.trunk if set, otherwise try main/master
                    trunk_candidates = [config.trunk] if config.trunk else ["main", "master"]
                    try:
                        for trunk in trunk_candidates:
                            if git.branch_exists(trunk, path=main_repo):
                                graphite.branch_track(branch_name, parent=trunk, cwd=main_repo)
                                actions.append(f"Tracked {branch_name} with graphite (parent: {trunk})")
                                break
                        else:
                            actions.append(f"Failed to track {branch_name}: no trunk branch found")
                    except graphite.GraphiteError as e:
                        actions.append(f"Failed to track {branch_name}: {e}")

    return actions


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
    window_name = f"{topic}/{name}"

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


def cmd_close_all_background(config: Config) -> list[str]:
    """Close all backgrounded worktree windows gracefully.

    Args:
        config: Application configuration

    Returns:
        List of window names that were closed
    """
    if not tmux.session_exists(BACKGROUND_SESSION):
        return []

    closed = []
    windows = tmux.list_windows(BACKGROUND_SESSION)

    for window in windows:
        window_name = window["name"]
        # Skip placeholder window
        if window_name == PLACEHOLDER_WINDOW:
            continue

        window_target = f"{BACKGROUND_SESSION}:{window_name}"

        # Gracefully close Claude Code
        tmux.close_claude_gracefully(window_target)

        # Kill the window
        tmux.kill_window(window_target)
        closed.append(window_name)

    # Kill the background session if it only has the placeholder left
    remaining = tmux.list_windows(BACKGROUND_SESSION)
    if len(remaining) <= 1:  # Only placeholder or empty
        tmux.kill_session(BACKGROUND_SESSION)

    return closed


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
        # Skip placeholder window
        if window_name == PLACEHOLDER_WINDOW:
            continue
        # Parse topic/name format
        parts = window_name.split("/", 1)
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
    window_name = f"{topic}/{name}"

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
        # Rename the default window to placeholder (filtered from listings)
        tmux.run_tmux("rename-window", "-t", f"{BACKGROUND_SESSION}:0", PLACEHOLDER_WINDOW)

    # Move window to background session
    source_target = f"{current_session}:{window_name}"
    tmux.move_window(source_target, BACKGROUND_SESSION)

    return window_name


def cmd_foreground(config: Config, name: str, target_session: str | None = None) -> str:
    """Bring a backgrounded worktree window to the foreground.

    Args:
        config: Application configuration
        name: Worktree name in "topic/name" format
        target_session: Session to move window to (defaults to current session)

    Returns:
        The window target in the target session

    Raises:
        ConfigError: If window not found in background session
    """
    # Parse and normalize the window name
    if "/" in name:
        topic, wt_name = config.parse_worktree_name(name)
        window_name = f"{topic}/{wt_name}"
    else:
        window_name = name

    # Check background session exists
    if not tmux.session_exists(BACKGROUND_SESSION):
        raise ConfigError("No backgrounded sessions")

    # Check window exists in background session
    if not tmux.window_exists(window_name, BACKGROUND_SESSION):
        raise ConfigError(f"Window {window_name} not found in background session")

    # Determine target session
    if target_session is None:
        current_session = tmux.get_current_session()
        if current_session and current_session != BACKGROUND_SESSION:
            target_session = current_session
        else:
            # Outside tmux or in background session - use or create 'wt' session
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


def cmd_go(
    config: Config,
    name: str,
    close: bool = False,
    new: bool = False,
    profile: str | None = None,
    from_branch: str | None = None,
) -> tuple[str, bool]:
    """Go to a worktree, creating it if necessary.

    This is the unified "go work on XYZ" command that:
    1. Backgrounds (or closes) the current window if in a managed worktree
    2. If target is backgrounded → foregrounds it
    3. If target has an active window → switches to it
    4. If target worktree exists but no window → creates window
    5. If target doesn't exist → creates worktree + branch + window

    Args:
        config: Configuration
        name: Target worktree name (topic/name format)
        close: If True, close current window instead of backgrounding
        new: If True, don't background or close the current window
        profile: Profile name for new windows (defaults to config default)
        from_branch: Base branch if creating new worktree

    Returns:
        Tuple of (window_target, was_created) where was_created indicates
        if a new worktree was created
    """
    topic, wt_name = config.parse_worktree_name(name)
    target_window_name = f"{topic}/{wt_name}"
    worktree_path = config.worktree_path(topic, wt_name)

    # ===== PHASE 1: Capture all state upfront before any mutations =====
    inside_tmux = tmux.is_inside_tmux()
    original_session = tmux.get_current_session() if inside_tmux else None

    # Current worktree info (for deciding whether to background)
    current_worktree = get_current_worktree_info(config)
    current_window_name = None
    should_background_current = False
    if current_worktree is not None:
        current_window_name = f"{current_worktree[0]}-{current_worktree[1]}"
        # Background if in tmux, not --new, and switching to different worktree
        should_background_current = (
            inside_tmux and
            not new and
            current_window_name != target_window_name
        )

    # Check where the target window exists (if anywhere)
    target_in_background = (
        tmux.session_exists(BACKGROUND_SESSION) and
        tmux.window_exists(target_window_name, BACKGROUND_SESSION)
    )
    target_in_original_session = (
        original_session is not None and
        tmux.window_exists(target_window_name, original_session)
    )
    target_in_wt_session = (
        tmux.session_exists("wt") and
        tmux.window_exists(target_window_name, "wt")
    )

    # Check if worktree exists on disk
    worktree_exists = worktree_path.exists()

    # ===== PHASE 2: Determine the action plan =====
    # Plan: (action, details)
    # Actions: "foreground", "switch", "switch_wt", "create_window", "create_worktree"
    if target_in_background:
        action = "foreground"
    elif target_in_original_session:
        action = "switch"
    elif target_in_wt_session:
        action = "switch_wt"
    elif worktree_exists:
        action = "create_window"
    else:
        action = "create_worktree"

    # ===== PHASE 3: Execute the plan =====

    # Step 1: Background/close current window if needed
    if should_background_current:
        if close:
            cmd_close(config)
        else:
            cmd_background(config)

    # Step 2: Execute the main action
    if action == "foreground":
        window_target = cmd_foreground(config, name, target_session=original_session)
        return window_target, False

    elif action == "switch":
        window_target = f"{original_session}:{target_window_name}"
        tmux.select_window(window_target)
        return window_target, False

    elif action == "switch_wt":
        window_target = f"wt:{target_window_name}"
        if inside_tmux:
            tmux.select_window(window_target)
        else:
            tmux.attach_session("wt")
        return window_target, False

    elif action == "create_window":
        # Worktree exists but no window - create window using pre-captured session
        return _create_window_for_worktree(
            config=config,
            topic=topic,
            wt_name=wt_name,
            worktree_path=worktree_path,
            profile=profile,
            target_session=original_session,
            inside_tmux=inside_tmux,
        )

    else:  # action == "create_worktree"
        # Create worktree + window
        return _create_worktree_and_window(
            config=config,
            name=name,
            topic=topic,
            wt_name=wt_name,
            profile=profile,
            from_branch=from_branch,
            target_session=original_session,
            inside_tmux=inside_tmux,
        )


def _create_window_for_worktree(
    config: Config,
    topic: str,
    wt_name: str,
    worktree_path: Path,
    profile: str | None,
    target_session: str | None,
    inside_tmux: bool,
) -> tuple[str, bool]:
    """Create a tmux window for an existing worktree.

    Uses pre-captured session info to avoid state inconsistencies.
    """
    profile_config = config.get_profile(profile)
    window_name = f"{topic}/{wt_name}"

    if inside_tmux and target_session:
        # Create new window in the target session
        window_target = tmux.launch_window(
            profile=profile_config,
            topic=topic,
            name=wt_name,
            worktree_path=worktree_path,
            session_name=target_session,
        )
        return window_target, False
    else:
        # Outside tmux - create or use 'wt' session
        session_name = "wt"
        if not tmux.session_exists(session_name):
            tmux.create_session(session_name, worktree_path)
            tmux.run_tmux("rename-window", "-t", f"{session_name}:0", window_name)
            window_target = f"{session_name}:{window_name}"

            # Set up panes from profile
            profile_rendered = tmux.render_profile(profile_config, topic, wt_name, worktree_path)
            panes = profile_rendered.get("panes", [])
            layout = profile_rendered.get("layout", "main-vertical")

            if panes:
                for cmd in panes[0].get("shell_command", []):
                    tmux.send_keys(window_target, cmd)

            for i, pane_config in enumerate(panes[1:], start=1):
                tmux.split_window(window_target, start_directory=worktree_path)
                pane_target = f"{window_target}.{i}"
                for cmd in pane_config.get("shell_command", []):
                    tmux.send_keys(pane_target, cmd)

            if layout and len(panes) > 1:
                tmux.select_layout(window_target, layout)

            if panes:
                tmux.select_pane(f"{window_target}.0")
        else:
            window_target = tmux.launch_window(
                profile=profile_config,
                topic=topic,
                name=wt_name,
                worktree_path=worktree_path,
                session_name=session_name,
            )

        tmux.attach_session(session_name)
        return window_target, False


def _create_worktree_and_window(
    config: Config,
    name: str,
    topic: str,
    wt_name: str,
    profile: str | None,
    from_branch: str | None,
    target_session: str | None,
    inside_tmux: bool,
) -> tuple[str, bool]:
    """Create a new worktree and its tmux window.

    Uses pre-captured session info to avoid state inconsistencies.
    """
    # Create the worktree
    worktree_path, _ = ensure_worktree(config, name, from_branch)

    # Create the window using pre-captured session info
    window_target, _ = _create_window_for_worktree(
        config=config,
        topic=topic,
        wt_name=wt_name,
        worktree_path=worktree_path,
        profile=profile,
        target_session=target_session,
        inside_tmux=inside_tmux,
    )

    return window_target, True


@dataclass
class StatusInfo:
    """Status information about the current state."""

    # Config info
    config_path: str
    branch_prefix: str
    root: Path
    default_profile: str
    available_profiles: list[str]
    trunk: str | None = None
    main_repo: Path | None = None

    # Current worktree info (if in a managed worktree)
    in_managed_worktree: bool = False
    topic: str | None = None
    name: str | None = None
    worktree_path: Path | None = None
    expected_branch: str | None = None
    current_branch: str | None = None
    has_tmux_window: bool = False
    graphite_available: bool = False

    # Tmux session info
    inside_tmux: bool = False
    tmux_session: str | None = None
    tmux_window: str | None = None
    tmux_panes: list[str] | None = None
    backgrounded_count: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            "config": {
                "config_path": self.config_path,
                "branch_prefix": self.branch_prefix,
                "root": str(self.root),
                "trunk": self.trunk,
                "main_repo": str(self.main_repo) if self.main_repo else None,
                "default_profile": self.default_profile,
                "available_profiles": self.available_profiles,
            },
            "graphite_available": self.graphite_available,
            "tmux": {
                "inside_tmux": self.inside_tmux,
                "session": self.tmux_session,
                "window": self.tmux_window,
                "panes": self.tmux_panes,
                "backgrounded_count": self.backgrounded_count,
            },
            "worktree": {
                "in_managed_worktree": self.in_managed_worktree,
                "topic": self.topic,
                "name": self.name,
                "path": str(self.worktree_path) if self.worktree_path else None,
                "expected_branch": self.expected_branch,
                "current_branch": self.current_branch,
                "has_tmux_window": self.has_tmux_window,
            } if self.in_managed_worktree else None,
        }


def cmd_status(config: Config, config_path: str | None = None) -> StatusInfo:
    """Get status information about config and current worktree.

    Args:
        config: Application configuration
        config_path: Path to the config file (for display)

    Returns:
        StatusInfo with current state
    """
    import os
    from wt.config import DEFAULT_CONFIG_PATHS

    # Determine config path for display
    if config_path is None:
        env_path = os.environ.get("WT_CONFIG")
        if env_path:
            config_path = env_path
        else:
            # Find the first existing default path
            for default_path in DEFAULT_CONFIG_PATHS:
                if default_path.exists():
                    config_path = str(default_path)
                    break
            else:
                config_path = str(DEFAULT_CONFIG_PATHS[0])

    # Get current worktree info
    current = get_current_worktree_info(config)

    status = StatusInfo(
        config_path=config_path,
        branch_prefix=config.branch_prefix,
        root=config.root,
        default_profile=config.default_profile,
        available_profiles=list(config.profiles.keys()),
        trunk=config.trunk,
        main_repo=config.main_repo,
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
        window_name = f"{topic}/{name}"
        current_session = tmux.get_current_session()
        has_window = False
        if current_session:
            has_window = tmux.window_exists(window_name, current_session)
        if not has_window and tmux.session_exists("wt"):
            has_window = tmux.window_exists(window_name, "wt")
        status.has_tmux_window = has_window

    # Tmux session info
    status.inside_tmux = tmux.is_inside_tmux()
    if status.inside_tmux:
        window_info = tmux.get_current_window_info()
        if window_info:
            status.tmux_session = window_info["session_name"]
            status.tmux_window = window_info["window_name"]
            status.tmux_panes = window_info["panes"]

    # Count backgrounded sessions
    backgrounded = cmd_sessions(config)
    status.backgrounded_count = len(backgrounded)

    return status


def cmd_pwd(config: Config, name: str | None = None) -> Path:
    """Get the worktree path for a worktree.

    Args:
        config: Configuration
        name: Worktree name (topic/name format). If None, detect from tmux window name.

    Returns:
        Path to the worktree

    Raises:
        ConfigError: If not in a wt-managed window or worktree not found
    """
    if name is not None:
        # Explicit worktree specified
        topic, wt_name = config.parse_worktree_name(name)
    else:
        # Detect from current tmux window name
        if not tmux.is_inside_tmux():
            raise ConfigError("Not inside tmux. Specify a worktree name: wt pwd <topic/name>")

        window_info = tmux.get_current_window_info()
        if window_info is None:
            raise ConfigError("Could not get current window info")

        window_name = window_info["window_name"]
        # Parse topic/name format
        if "/" not in window_name:
            raise ConfigError(f"Window '{window_name}' is not a wt-managed window")

        topic, wt_name = window_name.split("/", 1)

    worktree_path = config.worktree_path(topic, wt_name)
    if not worktree_path.exists():
        raise ConfigError(f"Worktree not found: {worktree_path}")

    return worktree_path
