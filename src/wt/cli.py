"""Command-line interface."""

from __future__ import annotations

import argparse
import sys

from wt import commands, git, graphite, tmux
from wt.config import Config, ConfigError


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="wt",
        description="Worktree session manager for git, graphite, tmux, and Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # wt new <topic>/<name> [--from <branch>]
    new_parser = subparsers.add_parser("new", help="Create a new worktree and branch")
    new_parser.add_argument("name", help="Worktree name in topic/name format")
    new_parser.add_argument(
        "--from",
        dest="from_branch",
        metavar="BRANCH",
        help="Base branch (defaults to current branch)",
    )

    # wt open <topic>/<name> [--profile <name>]
    open_parser = subparsers.add_parser("open", help="Open tmux session for a worktree")
    open_parser.add_argument("name", help="Worktree name in topic/name format")
    open_parser.add_argument(
        "--profile",
        metavar="NAME",
        help="tmuxp profile name (defaults to config default)",
    )

    # wt list
    subparsers.add_parser("list", help="List all managed worktrees")

    # wt sync [name] [--all]
    sync_parser = subparsers.add_parser(
        "sync",
        help="Ensure git/graphite branch exists for worktree(s)",
    )
    sync_parser.add_argument(
        "name",
        nargs="?",
        help="Worktree name in topic/name format (defaults to current)",
    )
    sync_parser.add_argument(
        "--all",
        action="store_true",
        dest="sync_all",
        help="Sync all worktrees",
    )

    # wt close
    subparsers.add_parser("close", help="Close current tmux session gracefully")

    args = parser.parse_args()

    try:
        config = Config.load()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    try:
        if args.command == "new":
            return handle_new(config, args)
        elif args.command == "open":
            return handle_open(config, args)
        elif args.command == "list":
            return handle_list(config, args)
        elif args.command == "sync":
            return handle_sync(config, args)
        elif args.command == "close":
            return handle_close(config, args)
        else:
            parser.print_help()
            return 1
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


def handle_new(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'new' command."""
    path = commands.cmd_new(
        config=config,
        name=args.name,
        from_branch=args.from_branch,
    )
    print(f"Created worktree at {path}")
    return 0


def handle_open(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'open' command."""
    session = commands.cmd_open(
        config=config,
        name=args.name,
        profile=args.profile,
    )
    print(f"Opened session: {session}")
    return 0


def handle_list(config: Config, args: argparse.Namespace) -> int:
    """Handle the 'list' command."""
    worktrees = commands.cmd_list(config)

    if not worktrees:
        print("No worktrees found")
        return 0

    # Print header
    print(f"{'NAME':<30} {'BRANCH':<40} {'SESSION':<10}")
    print("-" * 80)

    for wt in worktrees:
        name = f"{wt['topic']}/{wt['name']}"
        branch = wt.get("branch", "")

        # Show warning if branch doesn't match expected
        if branch and not wt.get("branch_matches"):
            branch = f"{branch} (expected: {wt['expected_branch']})"
        elif not wt.get("branch_exists"):
            branch = f"(missing: {wt['expected_branch']})"

        session = "active" if wt.get("has_session") else ""

        print(f"{name:<30} {branch:<40} {session:<10}")

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
    print("Session closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
