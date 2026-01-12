# Future Features

Potential improvements and new features for `wt`.

---

## New Commands

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

### `wt batch <operation>`

**Problem**: Some operations would benefit from selecting multiple targets at once rather than running the command multiple times.

**Behavior**: Multi-select picker for batch operations.

```bash
wt batch close     # Multi-select worktree windows to close gracefully
wt batch sync      # Multi-select worktrees to sync branches
wt batch fg        # Multi-select backgrounded windows to foreground
wt batch shutdown  # Multi-select backgrounded windows to close
```

**Implementation**:
- Add `pick_many()` to picker.py using simple-term-menu's `multi_select=True`
- Show multi-select picker (space/tab to select, enter to confirm)
- Execute operation on each selected item
- Report results: "Closed 3 windows"

---

## Enhancements

### Additional list filters

Currently `wt list --bg` shows only backgrounded worktrees. Could add more filters:

```bash
wt list --active     # Only with active (non-backgrounded) windows
wt list --no-window  # Only without any window
wt list <topic>      # Filter by topic prefix
```

---

### Interactive list with actions

**Problem**: Current flow requires multiple commands: `wt list`, then `wt go <name>`.

**Behavior**: `wt list -i` opens interactive list where:
- j/k to navigate
- Enter to open (go)
- d to remove
- b to background (if active)
- f to foreground (if backgrounded)
- s to sync
- q to quit

**Complexity**: Medium - requires more sophisticated TUI than simple picker.

---

## Priority Summary

| Priority | Feature | Effort |
|----------|---------|--------|
| Medium | `wt batch` | Medium |
| Medium | Additional list filters | Low |
| Low | `wt run` | Low |
| Low | Interactive list | Medium |
