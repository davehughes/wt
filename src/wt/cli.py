"""Command-line interface."""

from __future__ import annotations

import argparse
import sys

import argcomplete
from argcomplete.completers import ChoicesCompleter

from wt import commands, git, graphite, tmux
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
            import sys
            print(f"WorktreeCompleter error: {e}", file=sys.stderr)
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
_session_completer = SessionCompleter()
_profile_completer = ProfileCompleter()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="wt",
        description="Worktree session manager for git, graphite, tmux, and Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # wt go [name] [--profile <name>] [--from <branch>] [--close]
    go_parser = subparsers.add_parser(
        "go", help="Go to a worktree (creates if needed)"
    )
    go_parser.add_argument(
        "name",
        nargs="?",
        help="Worktree name in topic/name format. Interactive picker if omitted.",
    ).completer = _worktree_completer
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
    go_parser.add_argument(
        "--close",
        action="store_true",
        help="Close current window instead of backgrounding it",
    )
    go_parser.set_defaults(func=handle_go)

    # wt list (alias: ls) [--bg]
    list_parser = subparsers.add_parser(
        "list", aliases=["ls"], help="List all managed worktrees"
    )
    list_parser.add_argument(
        "--bg",
        action="store_true",
        help="Only show backgrounded worktrees",
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
    close_parser = subparsers.add_parser(
        "close", help="Close current tmux window gracefully"
    )
    close_parser.set_defaults(func=handle_close)

    # wt status
    status_parser = subparsers.add_parser(
        "status", help="Show config and current worktree status"
    )
    status_parser.set_defaults(func=handle_status)

    # wt config-template
    config_template_parser = subparsers.add_parser(
        "config-template", help="Print a configuration template"
    )
    config_template_parser.set_defaults(func=handle_config_template, requires_config=False)

    # wt bg
    bg_parser = subparsers.add_parser("bg", help="Send current window to background")
    bg_parser.set_defaults(func=handle_bg)

    # wt fg [name]
    fg_parser = subparsers.add_parser(
        "fg", help="Bring a backgrounded window to foreground"
    )
    fg_parser.add_argument(
        "name",
        nargs="?",
        help="Worktree name (topic/name or topic-name format). Interactive picker if omitted.",
    ).completer = _session_completer
    fg_parser.set_defaults(func=handle_fg)

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
    hint: str = "wt open <topic/name>",
) -> str | None:
    """Resolve worktree name, using interactive picker if name is None.

    Returns the worktree name (topic/name format) or None if cancelled/error.
    """
    if name is not None:
        return name

    from wt import picker

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

    Returns the session name (topic-name format) or None if cancelled/error.
    """
    if name is not None:
        return name

    from wt import picker

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
    worktrees = commands.cmd_list(config)

    # Filter by --bg flag if specified
    if args.bg:
        worktrees = [wt for wt in worktrees if wt.get("is_backgrounded")]

    if not worktrees:
        if args.bg:
            print("No backgrounded worktrees")
        else:
            print("No worktrees found")
        return 0

    # Print header
    print(f"{'NAME':<30} {'BRANCH':<40} {'WINDOW':<10}")
    print("-" * 80)

    for wt in worktrees:
        name = f"{wt['topic']}/{wt['name']}"
        branch = wt.get("branch") or ""

        # Show warning if branch doesn't match expected
        if branch and not wt.get("branch_matches"):
            branch = f"{branch} (expected: {wt['expected_branch']})"
        elif not wt.get("branch_exists"):
            branch = f"(missing: {wt['expected_branch']})"

        if wt.get("is_backgrounded"):
            window = "background"
        elif wt.get("has_window"):
            window = "active"
        else:
            window = ""

        print(f"{name:<30} {branch:<40} {window:<10}")

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


def handle_config_template(args: argparse.Namespace) -> int:
    """Handle the 'config-template' command."""
    template = """\
# wt configuration file
# Save this to ~/.config/wt/config.yaml or set WT_CONFIG to point to it

branch_prefix: YOUR_NAME
root: ~/projects/worktrees
# main_repo: ~/projects/myrepo  # Optional: main git repo (auto-detected from existing worktrees)
default_profile: default

profiles:
  default:
    session_name: "{{topic}}-{{name}}"
    windows:
      - window_name: dev
        layout: main-vertical
        panes:
          - shell_command:
              - cd {{worktree_path}}
          - shell_command:
              - cd {{worktree_path}}
              - claude --continue

  # Example: editor-focused profile
  editor:
    session_name: "{{topic}}-{{name}}"
    windows:
      - window_name: code
        panes:
          - shell_command:
              - cd {{worktree_path}}
              - $EDITOR .

  # Example: full development setup
  full:
    session_name: "{{topic}}-{{name}}"
    windows:
      - window_name: code
        layout: main-horizontal
        panes:
          - shell_command:
              - cd {{worktree_path}}
              - $EDITOR .
          - shell_command:
              - cd {{worktree_path}}
      - window_name: claude
        panes:
          - shell_command:
              - cd {{worktree_path}}
              - claude --continue
"""
    print(template)
    return 0


def handle_status(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'status' command."""
    status = commands.cmd_status(config)

    print("Configuration")
    print("─" * 40)
    print(f"  Config file:     {status.config_path}")
    print(f"  Branch prefix:   {status.branch_prefix}")
    print(f"  Root:            {status.root}")
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
        print(f"  Tmux session:    not in tmux")

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
    """Handle the 'bg' command."""
    window_name = commands.cmd_background(config)
    print(f"Backgrounded: {window_name}")
    return 0


def handle_fg(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'fg' command."""
    name = resolve_session_name(config, args.name)
    if name is None:
        return 1

    window_target = commands.cmd_foreground(config, name)
    print(f"Foregrounded: {window_target}")
    return 0


def handle_go(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'go' command."""
    name = resolve_worktree_name(config, args.name)
    if name is None:
        return 1

    window_target, was_created = commands.cmd_go(
        config,
        name,
        close=args.close,
        profile=args.profile,
        from_branch=args.from_branch,
    )
    if was_created:
        print(f"Created worktree: {window_target}")
    else:
        print(f"Switched to: {window_target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
