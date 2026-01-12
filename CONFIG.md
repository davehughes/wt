# Configuration

wt requires a configuration file to operate. By default, it looks for `~/.config/wt/config.yaml` or `~/.config/wt/config.yml`.

## Quick Start

```bash
mkdir -p ~/.config/wt
wt config-template > ~/.config/wt/config.yaml
$EDITOR ~/.config/wt/config.yaml
```

## Config Location

The config file location can be overridden with the `WT_CONFIG` environment variable:

```bash
export WT_CONFIG=~/projects/myproject/.wt.yaml
```

## Example Configuration

```yaml
branch_prefix: dave
root: ~/projects
trunk: main
default_profile: default

profiles:
  default:
    layout: main-vertical
    panes:
      - shell_command:
          - cd {{worktree_path}}
      - shell_command:
          - cd {{worktree_path}}
          - claude --continue || claude

# Optional: symlink shared files into each worktree
symlinks:
  ~/.env.myproject: .env
  ~/projects/main/.vscode: .vscode
```

## Options

| Option | Required | Description |
|--------|----------|-------------|
| `branch_prefix` | Yes | Prefix for branch names (e.g., `dave` creates branches like `dave/feature/auth`) |
| `root` | Yes | Base directory for worktrees (worktrees stored at `$root/<topic>/<name>`) |
| `trunk` | No | Primary branch name for graphite (e.g., `main`, `master`). Auto-detected if not set. |
| `default_profile` | Yes | Name of the default tmux profile |
| `profiles` | Yes | Dictionary of tmux profile configurations (at least one required) |
| `main_repo` | No | Path to main git repository. Auto-detected from existing worktrees if not set. |
| `symlinks` | No | Files to symlink into each worktree. See [Symlinks](#symlinks) below. |

## Profiles

Profiles define the pane layout for worktree windows. Each profile specifies a layout and a list of panes with their shell commands.

### Template Variables

These variables are available in all string values within a profile:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{topic}}` | The worktree topic (first path segment) | `feature` |
| `{{name}}` | The worktree name (second path segment) | `auth` |
| `{{worktree_path}}` | Full absolute path to the worktree | `/home/dave/projects/feature/auth` |

### Profile Structure

```yaml
profiles:
  profile_name:
    layout: main-vertical    # Pane layout (optional, defaults to main-vertical)
    panes:
      - shell_command:
          - command1
          - command2
      - shell_command:
          - command3
```

### Layouts

#### Named Layouts

| Layout | Description |
|--------|-------------|
| `main-horizontal` | One large pane on top, smaller panes below |
| `main-vertical` | One large pane on left, smaller panes on right |
| `tiled` | All panes equal size in a grid |
| `even-horizontal` | All panes equal width, side by side |
| `even-vertical` | All panes equal height, stacked |

#### Custom Layouts

You can also use custom tmux layout strings for precise control. Get a layout string from an existing window with:

```bash
tmux list-windows -F '#{window_layout}'
```

Then use it in your config:

```yaml
profiles:
  custom:
    layout: "0a31,198x48,0,0{98x48,0,0,5,99x48,99,0[99x11,99,0,6,99x12,99,12,7,99x23,99,25,8]}"
    panes:
      - shell_command: [cd {{worktree_path}}]
      - shell_command: [cd {{worktree_path}}]
      - shell_command: [cd {{worktree_path}}]
```

#### Reusable Layouts with YAML Anchors

Use YAML anchors to define layouts once and reuse them:

```yaml
# Define reusable layouts at the top
layouts:
  vsplit_1_3: &layout_vsplit "0a31,198x48,0,0{98x48,0,0,5,99x48,99,0[99x11,99,0,6,99x12,99,12,7,99x23,99,25,8]}"

profiles:
  dev:
    layout: *layout_vsplit
    panes:
      - shell_command: [cd {{worktree_path}}, $EDITOR .]
      - shell_command: [cd {{worktree_path}}]
      - shell_command: [cd {{worktree_path}}]
```

Note: The `layouts` key is ignored by wt but allows you to define anchors at the top level.

### Example Profiles

#### Development (Claude + Shell)

```yaml
default:
  layout: main-vertical
  panes:
    - shell_command:
        - cd {{worktree_path}}
    - shell_command:
        - cd {{worktree_path}}
        - claude --continue || claude
```

#### Editor Focused

```yaml
editor:
  panes:
    - shell_command:
        - cd {{worktree_path}}
        - $EDITOR .
```

#### Three-Pane Development

```yaml
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
```

#### Minimal (Just a Shell)

```yaml
minimal:
  panes:
    - shell_command:
        - cd {{worktree_path}}
```

### Using Profiles

Specify a profile when opening a worktree:

```bash
# Use default profile
wt feature/auth

# Use specific profile
wt feature/auth --profile full
```

## Symlinks

The `symlinks` option allows you to automatically create symlinks in each worktree, pointing to shared files or directories. This is useful for:

- Environment files (`.env`) that should be shared across worktrees
- IDE configuration (`.vscode/`, `.idea/`)
- Local configuration files not tracked in git
- Build caches or node_modules (if you want to share them)

### Format

```yaml
symlinks:
  /absolute/path/to/source: relative/target/in/worktree
  ~/path/with/tilde: another/target
```

- **Source paths** (keys): Absolute paths to files/directories. Tilde (`~`) is expanded.
- **Target paths** (values): Relative paths within the worktree. Must not be absolute.

### Example

```yaml
symlinks:
  ~/.env.myproject: .env
  ~/projects/main/.vscode: .vscode
  ~/projects/main/.claude/settings.local.json: .claude/settings.local.json
```

This configuration will:
1. Symlink `~/.env.myproject` to `.env` in each worktree
2. Symlink the main project's `.vscode` directory
3. Symlink Claude Code local settings

### Behavior

Symlinks are created:
- When a worktree is created (`wt go <new-worktree>`)
- When syncing (`wt sync` or `wt sync --all`)

Rules:
- If the source doesn't exist, the symlink is skipped (with a message)
- If a correct symlink already exists, it's left unchanged
- If a symlink exists but points elsewhere, it's updated
- If a regular file/directory exists at the target, it's **not** overwritten (warning issued)
- Parent directories are created as needed

### Use Cases

#### Shared Environment File

Keep one `.env` file and symlink it to all worktrees:

```yaml
symlinks:
  ~/.env.myproject: .env
```

#### Shared IDE Settings

Share VS Code settings across worktrees:

```yaml
symlinks:
  ~/projects/main/.vscode: .vscode
```

#### Shared Node Modules (Advanced)

Share `node_modules` to save disk space (use with caution):

```yaml
symlinks:
  ~/projects/main/node_modules: node_modules
```

Note: This only works if all worktrees use the same dependencies.
