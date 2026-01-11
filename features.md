# Future Features

Potential improvements and new features for `wt`.

---

## Consolidation

### Merge `sessions` into `list`

**Problem**: `wt list` already shows window status (active/background/none) in the WINDOW column. `wt sessions` duplicates this by showing only backgrounded windows.

**Solution**: Add filtering flags to `list` and deprecate `sessions`.

```bash
wt list              # All worktrees (current behavior)
wt list --bg         # Only backgrounded
wt list --active     # Only with active windows
wt list --no-window  # Only without windows
wt list <topic>      # Filter by topic prefix
```

**Implementation**:
- Add `--bg`, `--active`, `--no-window` flags to list parser
- Add optional positional `topic` filter
- Mark `sessions` as deprecated (print warning, keep working)
- Eventually remove `sessions`

---

## New Commands

### `wt remove <name> [--force] [--keep-branch]`

**Problem**: No way to cleanly remove a worktree. Users must manually run `git worktree remove` and `git branch -d`.

**Behavior**:
1. Check if worktree has a tmux window (active or backgrounded)
2. If window exists and not `--force`: error with suggestion to close first
3. If window exists and `--force`: close the window first
4. Remove the git worktree (`git worktree remove`)
5. Unless `--keep-branch`: delete the branch (`git branch -d` or `-D` with `--force`)

```bash
wt remove feature/auth              # Remove worktree + branch
wt remove feature/auth --keep-branch # Remove worktree, keep branch
wt remove feature/auth --force       # Force remove even if dirty/has window
```

**Edge cases**:
- Worktree has uncommitted changes: require `--force`
- Branch has unpushed commits: warn, require `--force` to delete branch
- Currently in the worktree directory: error, suggest cd out first

---

### `wt path <name>`

**Problem**: No easy way to get a worktree's path for use in scripts or shell commands.

**Behavior**: Print the absolute path to the worktree directory.

```bash
wt path feature/auth
# Output: /home/dave/projects/feature/auth

# Use cases:
cd $(wt path feature/auth)
ls $(wt path feature/auth)/src
code $(wt path feature/auth)
```

**With no argument**: Print current worktree path (if in one).

```bash
wt path  # /home/dave/projects/feature/auth (current worktree)
```

**Implementation**: Simple - just call `config.worktree_path(topic, name)` and print.

---

### `wt prune [--dry-run]`

**Problem**: Over time, orphaned worktrees and branches accumulate:
- Worktree directories without corresponding git worktree entries
- Git worktree entries pointing to deleted directories
- Branches without worktrees (from previously deleted worktrees)

**Behavior**:
1. Run `git worktree prune` to clean up stale worktree entries
2. Find branches matching `{branch_prefix}/*/*` pattern
3. For each branch, check if corresponding worktree exists
4. Report orphaned branches (don't auto-delete without confirmation)

```bash
wt prune --dry-run
# Output:
# Would prune stale worktree entry: /home/dave/projects/old/thing
# Orphaned branches (no worktree):
#   dave/feature/deleted-thing
#   dave/bugfix/old-fix

wt prune
# Pruned 1 stale worktree entry
# Found 2 orphaned branches. Delete with: git branch -d <branch>
```

**Future enhancement**: Interactive mode to select branches to delete.

---

### `wt attach <name>`

**Problem**: When outside tmux, `wt fg` creates/uses a "wt" session but doesn't attach to it. User must manually `tmux attach`.

**Behavior**: Attach to the tmux session containing a worktree's window.

```bash
# Outside tmux:
wt attach feature/auth
# Attaches to the session containing the feature-auth window

# Inside tmux:
wt attach feature/auth
# Switches to the window (same as wt fg if backgrounded, or just selects if active)
```

**Implementation**:
- Find which session contains the window (active session or wt-bg)
- If outside tmux: `tmux attach -t <session>`
- If inside tmux: `tmux select-window -t <target>`

---

### `wt rename <old> <new>`

**Problem**: Renaming a worktree requires multiple manual steps:
1. Rename the directory
2. Update git worktree entry
3. Rename the branch
4. Rename tmux window (if exists)

**Behavior**:
```bash
wt rename feature/auth feature/authentication
# Renames:
#   Directory: feature/auth -> feature/authentication
#   Branch: dave/feature/auth -> dave/feature/authentication
#   Window: feature-auth -> feature-authentication (if exists)
```

**Complexity**: High - need to handle:
- Active windows (must close/reopen or use tmux rename-window)
- Graphite branch tracking
- In-progress work (uncommitted changes)

**Recommendation**: Lower priority due to complexity. Users can create new + remove old.

---

### `wt run <name> <command...>`

**Problem**: No way to run a command in a worktree directory without cd'ing there.

**Behavior**:
```bash
wt run feature/auth npm install
wt run feature/auth git status
wt run feature/auth make test
```

**Implementation**:
```python
def cmd_run(config: Config, name: str, command: list[str]) -> int:
    topic, wt_name = config.parse_worktree_name(name)
    path = config.worktree_path(topic, wt_name)
    return subprocess.run(command, cwd=path).returncode
```

**Note**: Simple but limited - no shell expansion, no interactive commands.

---

## Output Enhancements

### `--json` flag for machine-readable output

**Problem**: Output is human-readable but not easily parseable by scripts.

**Apply to**: `list`, `sessions`, `status`

```bash
wt list --json
# [{"topic": "feature", "name": "auth", "branch": "dave/feature/auth", ...}]

wt status --json
# {"config": {...}, "worktree": {...}}
```

**Implementation**: Add `--json` flag, use `json.dumps()` instead of print formatting.

---

## Interactive Enhancements

### Interactive `list` with actions

**Problem**: Current flow requires multiple commands: `wt list`, then `wt open <name>`.

**Behavior**: `wt list -i` or `wt` (no command) opens interactive list where:
- j/k to navigate
- Enter to open
- d to remove
- b to background (if active)
- f to foreground (if backgrounded)
- s to sync
- q to quit

**Complexity**: Medium - requires more sophisticated TUI than simple picker.

**Recommendation**: Lower priority. Current `wt open` with picker covers main use case.

---

## Priority Summary

| Priority | Feature | Effort |
|----------|---------|--------|
| High | `wt remove` | Medium |
| High | `wt path` | Low |
| High | List filtering (`--bg`, `--active`) | Low |
| Medium | `wt prune` | Medium |
| Medium | `wt attach` | Low |
| Medium | `--json` output | Low |
| Low | `wt rename` | High |
| Low | `wt run` | Low |
| Low | Interactive list | Medium |
