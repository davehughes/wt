# wt - Worktree Session Manager

Utilities for managing development sessions with git worktrees, graphite.dev CLI, Claude Code, and tmux. Each session is tied 1:1 with a branch checked out as a worktree.

## Installation

```bash
pip install -e .
```

## Configuration

Create a config file at `~/.config/wt/config.toml`:

```toml
branch_prefix = "dave"
root = "~/projects"
default_profile = "default"

[profiles_dir]
path = "~/.config/wt/profiles"
```

You can override the config location with the `WT_CONFIG` environment variable:

```bash
export WT_CONFIG=~/projects/myproject/.wt.toml
```

### Configuration Options

| Option | Description |
|--------|-------------|
| `branch_prefix` | Prefix for branch names (e.g., `dave` creates branches like `dave/feature/auth`) |
| `root` | Base directory for worktrees (worktrees stored under `$root/worktrees/<topic>/<name>`) |
| `default_profile` | Default tmuxp profile name |
| `profiles_dir.path` | Directory containing tmuxp profile templates |

## Commands

### `wt new <topic>/<name> [--from <branch>]`

Create a new worktree and branch.

```bash
# Create from current branch
wt new feature/auth

# Create from specific branch
wt new feature/auth --from main
```

This creates:
- Branch: `<branch_prefix>/<topic>/<name>` (e.g., `dave/feature/auth`)
- Worktree: `<root>/worktrees/<topic>/<name>` (e.g., `~/projects/worktrees/feature/auth`)

### `wt open <topic>/<name> [--profile <name>]`

Open a tmux session for a worktree using tmuxp.

```bash
# Open with default profile
wt open feature/auth

# Open with specific profile
wt open feature/auth --profile claude-dev
```

### `wt list`

List all managed worktrees with their status.

```bash
wt list
```

Output shows:
- Worktree name
- Branch status (including warnings for mismatched/missing branches)
- Active tmux session indicator

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

Gracefully close the current session. Sends `/exit` to Claude Code before closing the tmux session.

```bash
wt close
```

## tmuxp Profiles

Profiles are YAML templates stored in the profiles directory. Template variables:

| Variable | Description |
|----------|-------------|
| `{{topic}}` | Worktree topic |
| `{{name}}` | Worktree name |
| `{{worktree_path}}` | Full path to the worktree |

Example profile (`~/.config/wt/profiles/default.yaml`):

```yaml
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
```

## Project Structure

```
wt/
├── pyproject.toml
├── src/wt/
│   ├── __init__.py
│   ├── cli.py           # CLI entry point (argparse)
│   ├── config.py        # Config loading from WT_CONFIG
│   ├── git.py           # Git worktree operations
│   ├── graphite.py      # Graphite CLI wrapper
│   ├── tmux.py          # tmuxp integration
│   └── commands.py      # High-level command implementations
├── tests/
│   ├── conftest.py      # Test fixtures
│   ├── test_config.py
│   ├── test_git.py
│   ├── test_tmux.py
│   └── test_commands.py
└── profiles/
    └── default.yaml
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
- tmuxp
- graphite CLI (optional, for branch tracking)
