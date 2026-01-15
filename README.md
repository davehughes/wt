# wt - Worktree Session Manager

Utilities for managing development sessions with git worktrees, graphite.dev CLI, Claude Code, and tmux. Each session is tied 1:1 with a branch checked out as a worktree.

## Installation

```bash
pip install -e .
```

## Configuration

wt requires a configuration file. By default, it looks for `~/.config/wt/config.yaml`.

```bash
mkdir -p ~/.config/wt
wt config-template > ~/.config/wt/config.yaml
$EDITOR ~/.config/wt/config.yaml
```

Override the config location with `WT_CONFIG`:

```bash
export WT_CONFIG=~/projects/myproject/.wt.yaml
```

See [CONFIG.md](CONFIG.md) for detailed configuration options and profile examples.

## Commands

### `wt [go] <topic>/<name> [--profile <name>] [--from <branch>]`

Open a worktree in a new tmux window. Creates the worktree if it doesn't exist. The `go` keyword is optional when providing a worktree name.

```bash
# Interactive picker
wt go

# Go to or create a worktree (shorthand)
wt feature/auth

# Explicit form
wt go feature/auth

# Create new worktree from specific branch
wt feature/auth --from main

# Open with specific tmux profile
wt feature/auth --profile focused
```

When creating a new worktree:
- Branch: `<branch_prefix>/<topic>/<name>` (e.g., `dave/feature/auth`)
- Worktree: `<root>/<topic>/<name>` (e.g., `~/projects/feature/auth`)
- If the branch already exists (e.g., from a deleted worktree), it's reused

### `wt switch <topic>/<name> [--profile <name>] [--from <branch>] [--close]` (alias: `sw`)

Switch to a worktree, backgrounding the current window. This is the "context switch" command that:

1. Backgrounds the current window (or closes with `--close`)
2. Foregrounds a backgrounded window (if target is in background)
3. Switches to an active window (if target already has a window)
4. Creates a new window (if worktree exists but no window)
5. Creates worktree + branch + window (if nothing exists yet)

```bash
# Switch to worktree, backgrounding current
wt switch feature/auth
wt sw feature/auth

# Close current window instead of backgrounding
wt switch feature/auth --close
```

### `wt list [--bg]`

List all managed worktrees with their status.

```bash
# List all worktrees
wt list

# List only backgrounded worktrees
wt list --bg
```

### `wt sync [<topic>/<name>] [--all]`

Ensure git/graphite branches exist for worktrees.

```bash
# Sync current worktree
wt sync

# Sync specific worktree
wt sync feature/auth

# Sync all worktrees
wt sync --all
```

### `wt close`

Gracefully close the current window. Sends `/exit` to Claude Code before closing the tmux window.

```bash
wt close
```

### `wt bg` (alias: `yeet`)

Send the current worktree window to the background. The window is moved to a background tmux session (`wt-bg`) where processes like Claude Code continue running.

```bash
wt bg
```

### `wt fg [<name>]` (alias: `yoink`)

Bring a backgrounded worktree window to the foreground. The window is moved from the background session back to the current tmux session.

```bash
# Interactive picker
wt fg

# Bring back specific worktree
wt fg feature/auth
```

### `wt remove [<name>]` (alias: `rm`)

Remove a worktree and its branch.

```bash
# Interactive picker
wt remove

# Remove specific worktree (keeps branch by default)
wt remove feature/auth

# Also delete the git branch
wt remove feature/auth --delete-branch

# Force remove (ignore uncommitted changes, close open windows)
wt remove feature/auth --force

# Skip confirmation prompt
wt remove feature/auth --yes
```

### `wt prune [--dry-run]`

Clean up stale worktree entries and find orphaned branches.

```bash
# Prune stale entries and report orphaned branches
wt prune

# Preview what would be done
wt prune --dry-run
```

### `wt rename [<old>] <new>`

Rename a worktree's branch, directory, and tmux window atomically.

```bash
# Rename current worktree
wt rename feature/new-name

# Rename specific worktree
wt rename feature/old-name feature/new-name
```

### `wt pwd [<topic/name>]`

Print the worktree path. Without arguments, uses the current tmux window name to determine the worktree.

```bash
# Print current worktree path
wt pwd

# Print specific worktree path
wt pwd feature/auth

# Change to worktree directory
cd "$(wt pwd)"
```

**Tip**: Add a shell alias for convenience:
```bash
# Add to ~/.bashrc or ~/.zshrc
alias wtcd='cd "$(wt pwd)"'
```

### `wt status`

Show current configuration and worktree status.

```bash
wt status
```

## Interactive Mode

When `wt go` or `wt fg` are invoked without arguments, an interactive picker is shown:

- Start typing to filter
- **Arrow keys** or **Ctrl-j/k** to navigate
- **Enter** to select
- **q** or **Esc** to cancel

If running in a non-interactive environment (piped output, no TTY), provide the name explicitly.

## Shell Completion

See [COMPLETIONS.md](COMPLETIONS.md) for shell completion setup instructions.

## Claude Code Hooks

wt can send notifications when Claude finishes working or needs attention (permissions, idle). See [HOOKS.md](HOOKS.md) for setup instructions.

## Development

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -v
```

## Requirements

- Python 3.9+
- git
- tmux
- graphite CLI (optional, for branch tracking)
