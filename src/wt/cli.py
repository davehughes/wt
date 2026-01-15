"""Command-line interface."""

from __future__ import annotations

import argparse
import sys

import argcomplete

from wt import commands, git, graphite, picker, tmux
from wt.config import Config, ConfigError


class WorktreeCompleter:
    """Complete worktree names (topic/name format)."""

    def __call__(self, prefix, **kwargs):
        try:
            config = Config.load()
            worktrees = commands.cmd_list(config)
            completions = [f"{wt['topic']}/{wt['name']}" for wt in worktrees]
            # Filter by prefix if provided
            if prefix:
                completions = [c for c in completions if c.startswith(prefix)]
            return completions
        except Exception as e:
            # Write to stderr for debugging (won't affect completions)
            print(f"WorktreeCompleter error: {e}", file=sys.stderr)
            return []


class BranchCompleter:
    """Complete from branches matching branch_prefix/topic/name pattern.

    This is useful for `wt go` since it can create worktrees from existing branches.
    Includes both existing worktrees and branches without worktrees.
    """

    def __call__(self, prefix, **kwargs):
        try:
            config = Config.load()

            # Get existing worktree names
            worktrees = commands.cmd_list(config)
            worktree_names = {f"{wt['topic']}/{wt['name']}" for wt in worktrees}

            # Start with existing worktrees
            completions = set(worktree_names)

            # Add branches that match prefix pattern but don't have worktrees
            branch_prefix = f"{config.branch_prefix}/"
            try:
                # Get main repo for branch listing
                main_repo = config.main_repo
                if not main_repo:
                    for wt in worktrees:
                        try:
                            main_repo = git.get_main_repo_path(wt["path"])
                            break
                        except git.GitError:
                            continue

                if main_repo:
                    all_branches = git.list_all_branches(path=main_repo)
                    for branch in all_branches:
                        if branch.startswith(branch_prefix):
                            # Extract topic/name from prefix/topic/name
                            suffix = branch[len(branch_prefix):]
                            if "/" in suffix:
                                completions.add(suffix)
            except git.GitError:
                pass  # Fall back to just worktrees

            # Filter by prefix if provided
            result = sorted(completions)
            if prefix:
                result = [c for c in result if c.startswith(prefix)]
            return result
        except Exception as e:
            print(f"BranchCompleter error: {e}", file=sys.stderr)
            return []


class SessionCompleter:
    """Complete backgrounded session names."""

    def __call__(self, prefix, **kwargs):
        try:
            config = Config.load()
            sessions = commands.cmd_sessions(config)
            return [s["name"] for s in sessions]
        except Exception:
            return []


class ProfileCompleter:
    """Complete profile names."""

    def __call__(self, prefix, **kwargs):
        try:
            config = Config.load()
            return list(config.profiles.keys())
        except Exception:
            return []


_worktree_completer = WorktreeCompleter()
_branch_completer = BranchCompleter()
_session_completer = SessionCompleter()
_profile_completer = ProfileCompleter()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="wt",
        description="Worktree session manager for git, graphite, tmux, and Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # wt go [name] [--profile <name>] [--from <branch>]
    go_parser = subparsers.add_parser("go", help="Open a worktree in a new window")
    go_parser.add_argument(
        "name",
        nargs="?",
        help="Worktree name in topic/name format. Interactive picker if omitted.",
    ).completer = _branch_completer
    go_parser.add_argument(
        "--profile",
        metavar="NAME",
        help="tmux profile name (defaults to config default)",
    ).completer = _profile_completer
    go_parser.add_argument(
        "--from",
        dest="from_branch",
        metavar="BRANCH",
        help="Base branch if creating new worktree (defaults to current branch)",
    )
    go_parser.set_defaults(func=handle_go)

    # wt switch [name] [--profile <name>] [--from <branch>] [--close] (alias: sw)
    switch_parser = subparsers.add_parser(
        "switch", aliases=["sw"],
        help="Switch to a worktree (backgrounds current, creates if needed)"
    )
    switch_parser.add_argument(
        "name",
        nargs="?",
        help="Worktree name in topic/name format. Interactive picker if omitted.",
    ).completer = _branch_completer
    switch_parser.add_argument(
        "--profile",
        metavar="NAME",
        help="tmux profile name (defaults to config default)",
    ).completer = _profile_completer
    switch_parser.add_argument(
        "--from",
        dest="from_branch",
        metavar="BRANCH",
        help="Base branch if creating new worktree (defaults to current branch)",
    )
    switch_parser.add_argument(
        "--close",
        action="store_true",
        help="Close current window instead of backgrounding it",
    )
    switch_parser.set_defaults(func=handle_switch)

    # wt list (alias: ls) [--bg] [--output <format>]
    list_parser = subparsers.add_parser("list", aliases=["ls"], help="List all managed worktrees")
    list_parser.add_argument(
        "--bg",
        action="store_true",
        help="Only show backgrounded worktrees",
    )
    list_parser.add_argument(
        "--output", "-o",
        choices=["text", "json", "yaml"],
        default="text",
        help="Output format (default: text)",
    )
    list_parser.set_defaults(func=handle_list)

    # wt sync [name] [--all]
    sync_parser = subparsers.add_parser(
        "sync",
        help="Ensure git/graphite branch exists for worktree(s)",
    )
    sync_parser.add_argument(
        "name",
        nargs="?",
        help="Worktree name in topic/name format (defaults to current)",
    ).completer = _worktree_completer
    sync_parser.add_argument(
        "--all",
        action="store_true",
        dest="sync_all",
        help="Sync all worktrees",
    )
    sync_parser.set_defaults(func=handle_sync)

    # wt close
    close_parser = subparsers.add_parser("close", help="Close current tmux window gracefully")
    close_parser.set_defaults(func=handle_close)

    # wt shutdown
    shutdown_parser = subparsers.add_parser("shutdown", help="Close all backgrounded windows gracefully")
    shutdown_parser.set_defaults(func=handle_shutdown)

    # wt status [--output <format>]
    status_parser = subparsers.add_parser("status", help="Show config and current worktree status")
    status_parser.add_argument(
        "--output", "-o",
        choices=["text", "json", "yaml"],
        default="text",
        help="Output format (default: text)",
    )
    status_parser.set_defaults(func=handle_status)

    # wt config-template
    config_template_parser = subparsers.add_parser("config-template", help="Print a configuration template")
    config_template_parser.set_defaults(func=handle_config_template, requires_config=False)

    # wt bg (alias: yeet)
    bg_parser = subparsers.add_parser("bg", aliases=["yeet"], help="Send current window to background")
    bg_parser.set_defaults(func=handle_bg)

    # wt fg [name] (alias: yoink)
    fg_parser = subparsers.add_parser("fg", aliases=["yoink"], help="Bring a backgrounded window to foreground")
    fg_parser.add_argument(
        "name",
        nargs="?",
        help="Worktree name (topic/name format). Interactive picker if omitted.",
    ).completer = _session_completer
    fg_parser.set_defaults(func=handle_fg)

    # wt pwd [name]
    pwd_parser = subparsers.add_parser("pwd", help='Print worktree path (use with: cd "$(wt pwd)")')
    pwd_parser.add_argument(
        "name",
        nargs="?",
        help="Worktree name (topic/name format). Defaults to current window's worktree.",
    ).completer = _worktree_completer
    pwd_parser.set_defaults(func=handle_pwd)

    # wt rename [old] <new>
    rename_parser = subparsers.add_parser(
        "rename",
        help="Rename worktree branch, directory, and tmux window",
    )
    rename_parser.add_argument(
        "names",
        nargs="+",
        metavar="NAME",
        help="[old] new - If one name given, infers old from current worktree. If two names given, first is old.",
    ).completer = _worktree_completer
    rename_parser.set_defaults(func=handle_rename)

    # wt remove [name] (alias: rm)
    remove_parser = subparsers.add_parser(
        "remove",
        aliases=["rm"],
        help="Remove a worktree and optionally its branch",
    )
    remove_parser.add_argument(
        "name",
        nargs="?",
        help="Worktree name (topic/name format). Interactive picker if omitted.",
    ).completer = _worktree_completer
    remove_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force remove even if dirty or has open windows",
    )
    remove_parser.add_argument(
        "--delete-branch",
        action="store_true",
        help="Also delete the git branch",
    )
    remove_parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    remove_parser.set_defaults(func=handle_remove)

    # wt prune [--dry-run]
    prune_parser = subparsers.add_parser(
        "prune",
        help="Clean up stale worktree entries and find orphaned branches",
    )
    prune_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes",
    )
    prune_parser.set_defaults(func=handle_prune)

    # wt hook <type> (called by Claude Code hooks)
    hook_parser = subparsers.add_parser(
        "hook",
        help="Handle Claude Code hooks (reads JSON from stdin)",
    )
    hook_parser.add_argument(
        "hook_type",
        choices=["stop", "attention"],
        help="Hook type: 'stop' (task finished) or 'attention' (needs input)",
    )
    hook_parser.set_defaults(func=handle_hook)

    # wt help
    help_parser = subparsers.add_parser("help", help="Show this help message")
    help_parser.set_defaults(func=lambda _: parser.print_help() or 0, requires_config=False)

    # Disable default file completion - only use our custom completers
    argcomplete.autocomplete(parser, default_completer=None)

    # Check if first arg looks like a worktree name (topic/name) - if so, insert "go"
    # This must be after argcomplete.autocomplete() which exits early during completion
    if len(sys.argv) > 1 and "/" in sys.argv[1] and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "go")

    args = parser.parse_args()

    # Handle commands that don't require config
    if not getattr(args, "requires_config", True):
        return args.func(args)

    try:
        config = Config.load()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    try:
        return args.func(config, args)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except git.GitError as e:
        print(f"Git error: {e}", file=sys.stderr)
        return 1
    except graphite.GraphiteError as e:
        print(f"Graphite error: {e}", file=sys.stderr)
        return 1
    except tmux.TmuxError as e:
        print(f"Tmux error: {e}", file=sys.stderr)
        return 1


def resolve_worktree_name(
    config: Config,
    name: str | None,
    empty_message: str = "No worktrees found",
    hint: str = "wt go <topic/name>",
) -> str | None:
    """Resolve worktree name, using interactive picker if name is None.

    Returns the worktree name (topic/name format) or None if cancelled/error.
    """
    if name is not None:
        return name


    worktrees = commands.cmd_list(config)
    if not worktrees:
        print(f"{empty_message}. Create one with: {hint}", file=sys.stderr)
        return None

    try:
        selected = picker.pick_worktree(worktrees)
        return f"{selected['topic']}/{selected['name']}"
    except picker.PickerUnavailable as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"Provide a worktree name: {hint}", file=sys.stderr)
        return None
    except picker.PickerError:
        return None


def resolve_session_name(
    config: Config,
    name: str | None,
    empty_message: str = "No backgrounded sessions",
    hint: str = "wt fg <topic/name>",
) -> str | None:
    """Resolve session name, using interactive picker if name is None.

    Returns the session name (topic/name format) or None if cancelled/error.
    """
    if name is not None:
        return name


    sessions = commands.cmd_sessions(config)
    if not sessions:
        print(empty_message, file=sys.stderr)
        return None

    try:
        selected = picker.pick_session(sessions)
        return selected["name"]
    except picker.PickerUnavailable as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"Provide a session name: {hint}", file=sys.stderr)
        return None
    except picker.PickerError:
        return None


def handle_list(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'list' command."""
    import json
    import yaml

    worktrees = commands.cmd_list(config)

    # Filter by --bg flag if specified
    if args.bg:
        worktrees = [wt for wt in worktrees if wt.get("is_backgrounded")]

    if not worktrees:
        if args.output == "json":
            print("[]")
        elif args.output == "yaml":
            print("[]")
        elif args.bg:
            print("No backgrounded worktrees")
        else:
            print("No worktrees found")
        return 0

    # JSON/YAML output
    if args.output in ("json", "yaml"):
        # Convert Path objects to strings for serialization
        serializable = []
        for wt in worktrees:
            item = {k: (str(v) if hasattr(v, '__fspath__') else v) for k, v in wt.items()}
            serializable.append(item)

        if args.output == "json":
            print(json.dumps(serializable, indent=2))
        else:
            print(yaml.dump(serializable, default_flow_style=False, sort_keys=False))
        return 0

    # Text output (default)
    # ANSI codes
    DIM = "\033[2m"
    RESET = "\033[0m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"

    for wt in worktrees:
        # Window status icon (left side) - includes Claude status
        claude_status = wt.get("claude_status")
        if wt.get("is_backgrounded"):
            # Backgrounded windows: show Claude status with half-circle
            if claude_status == "idle":
                window_icon = f"{GREEN}◐{RESET}"  # Green = idle
            elif claude_status == "permission":
                window_icon = f"{RED}◐{RESET}"  # Red = needs attention
            elif claude_status == "working":
                window_icon = f"{YELLOW}◐{RESET}"  # Yellow = working
            else:
                window_icon = f"{DIM}◐{RESET}"  # Dim = unknown/no Claude
        elif wt.get("has_window"):
            # Active windows: show Claude status with filled circle
            if claude_status == "idle":
                window_icon = f"{GREEN}●{RESET}"  # Green = idle
            elif claude_status == "permission":
                window_icon = f"{RED}●{RESET}"  # Red = needs attention
            elif claude_status == "working":
                window_icon = f"{YELLOW}●{RESET}"  # Yellow = working
            else:
                window_icon = f"{BLUE}●{RESET}"  # Blue = window but unknown Claude status
        else:
            window_icon = " "

        # Branch status icon (right side, only if there's a problem)
        if not wt.get("branch_exists"):
            branch_icon = f" {RED}✗{RESET}"
        elif not wt.get("branch_matches"):
            branch_icon = f" {YELLOW}!{RESET}"
        else:
            branch_icon = ""

        # Format name with dim prefix
        name = f"{DIM}{config.branch_prefix}/{RESET}{wt['topic']}/{wt['name']}"

        print(f"{window_icon} {name}{branch_icon}")

    return 0


def handle_sync(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'sync' command."""
    actions = commands.cmd_sync(
        config=config,
        name=args.name,
        sync_all=args.sync_all,
    )

    if not actions:
        print("Nothing to sync")
    else:
        for action in actions:
            print(action)

    return 0


def handle_close(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'close' command."""
    commands.cmd_close(config)
    print("Window closed")
    return 0


def handle_shutdown(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'shutdown' command."""
    closed = commands.cmd_close_all_background(config)
    if not closed:
        print("No backgrounded windows to close")
    else:
        for name in closed:
            print(f"Closed: {name}")
        print(f"Shut down {len(closed)} window(s)")
    return 0


def handle_config_template(args: argparse.Namespace) -> int:
    """Handle the 'config-template' command."""
    template = """\
# wt configuration file
# Save this to ~/.config/wt/config.yaml or set WT_CONFIG to point to it

branch_prefix: YOUR_NAME
root: ~/projects/worktrees
trunk: main  # Primary branch for graphite (auto-detected if not set)
# main_repo: ~/projects/myrepo  # Optional: main git repo (auto-detected from existing worktrees)
default_profile: default

# Profiles define the pane layout for worktree windows
# Available variables: {{topic}}, {{name}}, {{worktree_path}}
profiles:
  default:
    layout: main-vertical
    panes:
      - shell_command:
          - cd {{worktree_path}}
      - shell_command:
          - cd {{worktree_path}}
          - claude --continue || claude

  # Example: editor-focused profile
  editor:
    panes:
      - shell_command:
          - cd {{worktree_path}}
          - $EDITOR .

  # Example: three-pane layout
  full:
    layout: main-horizontal
    panes:
      - shell_command:
          - cd {{worktree_path}}
          - $EDITOR .
      - shell_command:
          - cd {{worktree_path}}
      - shell_command:
          - cd {{worktree_path}}
          - claude --continue || claude

  # Example: profile with symlinks for shared files
  with-symlinks:
    layout: main-vertical
    panes:
      - shell_command:
          - cd {{worktree_path}}
      - shell_command:
          - cd {{worktree_path}}
          - claude --continue || claude
    # Symlinks to create in worktrees using this profile
    symlinks:
      ~/.env.local: .env
      ~/projects/main/.vscode: .vscode
"""
    print(template)
    return 0


def handle_status(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'status' command."""
    import json
    import yaml

    status = commands.cmd_status(config)

    if args.output == "json":
        print(json.dumps(status.to_dict(), indent=2))
        return 0

    if args.output == "yaml":
        print(yaml.dump(status.to_dict(), default_flow_style=False, sort_keys=False))
        return 0

    # Text output (default)
    print("Configuration")
    print("─" * 40)
    print(f"  Config file:     {status.config_path}")
    print(f"  Branch prefix:   {status.branch_prefix}")
    print(f"  Root:            {status.root}")
    print(f"  Trunk:           {status.trunk or '(auto-detect)'}")
    print(f"  Main repo:       {status.main_repo or '(auto-detect)'}")
    print(f"  Default profile: {status.default_profile}")
    print(f"  Profiles:        {', '.join(status.available_profiles)}")
    print(f"  Graphite:        {'available' if status.graphite_available else 'not available'}")

    # Tmux info as single line
    if status.inside_tmux:
        tmux_info = status.tmux_session
        if status.backgrounded_count > 0:
            tmux_info += f" ({status.backgrounded_count} backgrounded)"
        print(f"  Tmux session:    {tmux_info}")
    else:
        print("  Tmux session:    not in tmux")

    print()
    print("Current Worktree")
    print("─" * 40)

    if not status.in_managed_worktree:
        print("  Not in a managed worktree")
    else:
        print(f"  Name:            {status.topic}/{status.name}")
        print(f"  Path:            {status.worktree_path}")
        print(f"  Expected branch: {status.expected_branch}")

        if status.current_branch:
            branch_status = ""
            if status.current_branch != status.expected_branch:
                branch_status = " (mismatch!)"
            print(f"  Current branch:  {status.current_branch}{branch_status}")
        else:
            print("  Current branch:  (detached or unknown)")

        window_status = "active" if status.has_tmux_window else "none"
        print(f"  Tmux window:     {window_status}")

    return 0


def handle_bg(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'bg' command (send window to background)."""
    window_name = commands.cmd_background(config)
    print(f"Backgrounded: {window_name}")
    return 0


def handle_fg(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'fg' command (bring window to foreground)."""
    name = resolve_session_name(config, args.name)
    if name is None:
        return 1

    window_target = commands.cmd_foreground(config, name)
    print(f"Foregrounded: {window_target}")
    return 0


def handle_pwd(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'pwd' command."""
    path = commands.cmd_pwd(config, args.name)
    print(path)
    return 0


def handle_rename(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'rename' command."""
    names = args.names

    if len(names) == 1:
        old_name = None
        new_name = names[0]
    elif len(names) == 2:
        old_name = names[0]
        new_name = names[1]
    else:
        print("Error: Expected 1 or 2 arguments: [old] new", file=sys.stderr)
        return 1

    result = commands.cmd_rename(config, old_name, new_name)
    print(result)
    return 0


def handle_remove(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'remove' command."""
    name = resolve_worktree_name(
        config,
        args.name,
        empty_message="No worktrees to remove",
        hint="wt remove <topic/name>",
    )
    if name is None:
        return 1

    # Confirm unless --yes or --force
    if not args.yes and not args.force:
        confirm = input(f"Remove worktree '{name}'? [y/N] ")
        if confirm.lower() != "y":
            print("Cancelled")
            return 0

    result = commands.cmd_remove(
        config,
        name,
        force=args.force,
        delete_branch=args.delete_branch,
    )
    print(result)
    return 0


def handle_prune(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'prune' command."""
    if args.dry_run:
        print("Dry run - no changes will be made")
        print()

    results = commands.cmd_prune(config, dry_run=args.dry_run)

    # Report pruned entries
    if results["pruned"]:
        print("Pruned stale worktree entries:")
        for entry in results["pruned"]:
            print(f"  {entry}")
    elif not args.dry_run:
        print("No stale worktree entries to prune")

    # Report orphaned branches
    if results["orphaned_branches"]:
        print()
        print("Orphaned branches (no worktree):")
        for branch in results["orphaned_branches"]:
            print(f"  {branch}")
        print()
        print("Delete with:")
        for branch in results["orphaned_branches"]:
            print(f"  git branch -d {branch}")
    else:
        print("No orphaned branches found")

    return 0


def handle_go(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'go' command - opens worktree in new window."""
    name = resolve_worktree_name(config, args.name)
    if name is None:
        return 1

    window_target, was_created = commands.cmd_go(
        config,
        name,
        close=False,
        new=True,
        profile=args.profile,
        from_branch=args.from_branch,
    )
    if was_created:
        print(f"Created worktree: {window_target}")
    else:
        print(f"Opened: {window_target}")
    return 0


def handle_switch(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'switch' command - backgrounds current and switches to target."""
    name = resolve_worktree_name(config, args.name)
    if name is None:
        return 1

    window_target, was_created = commands.cmd_go(
        config,
        name,
        close=args.close,
        new=False,
        profile=args.profile,
        from_branch=args.from_branch,
    )
    if was_created:
        print(f"Created worktree: {window_target}")
    else:
        print(f"Switched to: {window_target}")
    return 0


def handle_hook(config: Config, args: argparse.Namespace) -> int:
    """Handle Claude Code hooks (stop, attention)."""
    import json

    # Read JSON from stdin
    try:
        hook_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        hook_data = {}

    if args.hook_type == "stop":
        commands.cmd_hook_stop(config, hook_data)
    elif args.hook_type == "attention":
        commands.cmd_hook_attention(config, hook_data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
