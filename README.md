# wt - Worktree Session Manager

Utilities for managing development sessions with git worktrees, graphite.dev CLI, Claude Code, and tmux. Each session is tied 1:1 with a branch checked out as a worktree.

## Installation

```bash
pip install -e .
```

## Configuration

Create a config file at `~/.config/wt/config.yaml`:

```yaml
branch_prefix: dave
root: ~/projects
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
              - claude --continue || claude

  # Custom profile for focused coding
  focused:
    session_name: "{{topic}}-{{name}}"
    windows:
      - window_name: code
        panes:
          - shell_command:
              - cd {{worktree_path}}
              - $EDITOR .
```

You can override the config location with the `WT_CONFIG` environment variable:

```bash
export WT_CONFIG=~/projects/myproject/.wt.yaml
```

### Configuration Options

| Option | Description |
|--------|-------------|
| `branch_prefix` | Prefix for branch names (e.g., `dave` creates branches like `dave/feature/auth`) |
| `root` | Base directory for worktrees (worktrees stored at `$root/<topic>/<name>`) |
| `main_repo` | (Optional) Path to main git repository. Auto-detected from existing worktrees if not set. |
| `default_profile` | Default tmux profile name |
| `profiles` | Dictionary of tmux profile configurations |

### Profile Variables

| Variable | Description |
|----------|-------------|
| `{{topic}}` | Worktree topic |
| `{{name}}` | Worktree name |
| `{{worktree_path}}` | Full path to the worktree |

## Commands

### `wt [go] <topic>/<name> [--profile <name>] [--from <branch>] [--close]`

The primary command for working with worktrees. The `go` keyword is optional when providing a worktree name. This is the "go work on XYZ" command that transparently handles:

1. Backgrounding the current window (if in a managed worktree)
2. Foregrounding a backgrounded window (if target is in background)
3. Switching to an active window (if target already has a window)
4. Creating a new window (if worktree exists but no window)
5. Creating worktree + branch + window (if nothing exists yet)

```bash
# Interactive picker
wt go

# Go to or create a worktree (shorthand)
wt feature/auth

# Explicit form
wt go feature/auth

# Create new worktree from specific branch
wt feature/auth --from main

# Go with specific tmux profile
wt feature/auth --profile focused

# Close current window instead of backgrounding
wt feature/auth --close
```

When creating a new worktree:
- Branch: `<branch_prefix>/<topic>/<name>` (e.g., `dave/feature/auth`)
- Worktree: `<root>/<topic>/<name>` (e.g., `~/projects/feature/auth`)
- If the branch already exists (e.g., from a deleted worktree), it's reused

### `wt list [--bg]`

List all managed worktrees with their status.

```bash
# List all worktrees
wt list

# List only backgrounded worktrees
wt list --bg
```

Output shows:
- Worktree name
- Branch status (including warnings for mismatched/missing branches)
- Window status (active, background, or none)

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

### `wt bg`

Send the current worktree window to the background. The window is moved to a background tmux session (`wt-bg`) where processes like Claude Code continue running.

```bash
wt bg
```

### `wt fg [<name>]`

Bring a backgrounded worktree window to the foreground. The window is moved from the background session back to the current tmux session.

```bash
# Interactive picker
wt fg

# Bring back by window name
wt fg feature-auth

# Or use topic/name format
wt fg feature/auth
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

Example output:
```
Configuration
────────────────────────────────────────
  Config file:     ~/.config/wt/config.yaml
  Branch prefix:   dave
  Root:            /home/dave/projects
  Default profile: default
  Profiles:        default, focused
  Graphite:        available
  Tmux session:    feature-auth (1 backgrounded)

Current Worktree
────────────────────────────────────────
  Name:            feature/auth
  Path:            /home/dave/projects/feature/auth
  Expected branch: dave/feature/auth
  Current branch:  dave/feature/auth
  Tmux window:     active
```

## Shell Completion

Enable tab completion for commands, worktree names, and options.

First, find where `wt` is installed:
```bash
which wt
# e.g., /Users/dave/projects/wt/.venv/bin/wt
```

Use the same directory for `register-python-argcomplete`.

### Zsh

Add to `~/.zshrc`:
```zsh
autoload -Uz compinit && compinit
eval "$(/path/to/.venv/bin/register-python-argcomplete wt)"
```

### Bash

Add to `~/.bashrc`:
```bash
eval "$(/path/to/.venv/bin/register-python-argcomplete wt)"
```

### Fish

Run once:
```fish
/path/to/.venv/bin/register-python-argcomplete --shell fish wt > ~/.config/fish/completions/wt.fish
```

After setup, tab completion works for:
- Subcommands (`wt <tab>` → `go`, `list`, `fg`, etc.)
- Worktree names (`wt feature/<tab>` → existing worktrees)
- Session names (`wt fg <tab>` → backgrounded sessions)
- Profile names (`wt go --profile <tab>` → available profiles)

## Interactive Mode

When `wt go` or `wt fg` are invoked without arguments, an interactive picker is shown:

- **j/k** or arrow keys to navigate
- **/** to filter by typing
- **Enter** to select
- **q** or **Esc** to cancel

If running in a non-interactive environment (piped output, no TTY), provide the name explicitly.

### `wt config-template`

Print a configuration template to stdout. Useful for initial setup:

```bash
# Create config directory and file
mkdir -p ~/.config/wt
wt config-template > ~/.config/wt/config.yaml

# Then edit to customize
$EDITOR ~/.config/wt/config.yaml
```

## Project Structure

```
wt/
├── pyproject.toml
├── src/wt/
│   ├── __init__.py
│   ├── cli.py           # CLI entry point (argparse)
│   ├── commands.py      # High-level command implementations
│   ├── config.py        # Config loading from WT_CONFIG
│   ├── git.py           # Git worktree operations
│   ├── graphite.py      # Graphite CLI wrapper
│   ├── picker.py        # Interactive selection (simple-term-menu)
│   └── tmux.py          # Tmux session/window management
└── tests/
    ├── conftest.py      # Test fixtures
    ├── test_commands.py
    ├── test_config.py
    ├── test_git.py
    ├── test_picker.py
    └── test_tmux.py
```

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
