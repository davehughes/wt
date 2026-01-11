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
              - claude --continue

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
| `template_dir` | Directory containing files to symlink into new worktrees (defaults to `$root/.template`) |
| `default_profile` | Default tmux profile name |
| `profiles` | Dictionary of tmux profile configurations |

### Profile Template Variables

| Variable | Description |
|----------|-------------|
| `{{topic}}` | Worktree topic |
| `{{name}}` | Worktree name |
| `{{worktree_path}}` | Full path to the worktree |

## Commands

### `wt open [<topic>/<name>] [--profile <name>] [--from <branch>]`

Open a tmux window for a worktree, creating the worktree if it doesn't exist.

If inside tmux, creates a new window in the current session.
If outside tmux, creates/attaches to a "wt" session and adds the window there.

```bash
# Interactive picker (requires simple-term-menu)
wt open

# Open existing or create new worktree from current branch
wt open feature/auth

# Create new worktree from specific branch
wt open feature/auth --from main

# Open with specific profile
wt open feature/auth --profile focused
```

When creating a new worktree:
- Branch: `<branch_prefix>/<topic>/<name>` (e.g., `dave/feature/auth`)
- Worktree: `<root>/<topic>/<name>` (e.g., `~/projects/feature/auth`)
- If the branch already exists (e.g., from a deleted worktree), it's reused

### `wt list`

List all managed worktrees with their status.

```bash
wt list
```

Output shows:
- Worktree name
- Branch status (including warnings for mismatched/missing branches)
- Active tmux window indicator

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

### `wt link [<topic>/<name>]`

Symlink template directory contents into a worktree. Useful for re-linking after template changes or if symlinks were accidentally removed.

```bash
# Link in current worktree
wt link

# Link in specific worktree
wt link feature/auth
```

Template files are symlinked (not copied), so changes to the template are reflected in all worktrees.

### `wt close`

Gracefully close the current window. Sends `/exit` to Claude Code before closing the tmux window.

```bash
wt close
```

### `wt sessions`

List all backgrounded worktree windows. Backgrounded windows continue running in a hidden tmux session.

```bash
wt sessions
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

### `wt switch [<name>] [--close]`

Background the current window and foreground another in one operation.

```bash
# Interactive picker
wt switch

# Direct switch
wt switch feature/auth

# Close current window instead of backgrounding
wt switch feature/auth --close
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
  Template dir:    /home/dave/projects/.template (exists)
  Default profile: default
  Profiles:        default, focused
  Graphite:        available

Current Worktree
────────────────────────────────────────
  Name:            feature/auth
  Path:            /home/dave/projects/feature/auth
  Expected branch: dave/feature/auth
  Current branch:  dave/feature/auth
  Tmux window:     active
```

## Interactive Mode

When `wt open`, `wt fg`, or `wt switch` are invoked without arguments, an interactive picker is shown:

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
