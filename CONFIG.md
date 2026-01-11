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

## Profiles

Profiles define how tmux windows are set up when you open a worktree. Each profile can have multiple windows, and each window can have multiple panes with different commands.

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
    session_name: "{{topic}}-{{name}}"  # Used for window naming
    windows:
      - window_name: name              # Name shown in tmux
        layout: main-vertical          # Pane layout
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
    session_name: "{{topic}}-{{name}}"
    windows:
      - window_name: dev
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
    session_name: "{{topic}}-{{name}}"
    windows:
      - window_name: code
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
```

#### Editor Focused

```yaml
editor:
  session_name: "{{topic}}-{{name}}"
  windows:
    - window_name: code
      panes:
        - shell_command:
            - cd {{worktree_path}}
            - $EDITOR .
```

#### Full Stack (Multiple Windows)

```yaml
fullstack:
  session_name: "{{topic}}-{{name}}"
  windows:
    - window_name: code
      layout: main-vertical
      panes:
        - shell_command:
            - cd {{worktree_path}}
            - $EDITOR .
        - shell_command:
            - cd {{worktree_path}}
    - window_name: servers
      layout: even-horizontal
      panes:
        - shell_command:
            - cd {{worktree_path}}
            - npm run dev
        - shell_command:
            - cd {{worktree_path}}
            - npm run watch:css
    - window_name: claude
      panes:
        - shell_command:
            - cd {{worktree_path}}
            - claude --continue || claude
```

#### Minimal (Just a Shell)

```yaml
minimal:
  session_name: "{{topic}}-{{name}}"
  windows:
    - window_name: shell
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
wt feature/auth --profile fullstack
```
