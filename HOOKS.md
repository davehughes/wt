# Claude Code Hooks

wt integrates with Claude Code hooks to provide notifications when Claude finishes working or needs your attention.

## Overview

Claude Code supports hooks that fire at specific events during a session. wt provides two hook handlers:

| Command | Hook Event | Fires When |
|---------|------------|------------|
| `wt hook-stop` | Stop | Claude finishes responding |
| `wt hook-attention` | Notification | Claude needs permission or is idle |

## Notification Channels

When a hook fires, wt sends notifications through multiple channels:

1. **Desktop notifications** (macOS Notification Center)
2. **tmux display-message** (visible in tmux status area)
3. **Sound alert** (for critical events like permission requests)

Notifications include the worktree name when Claude is running in a managed worktree.

## Setup

Add this to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {"type": "command", "command": "wt hook-stop"}
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [
          {"type": "command", "command": "wt hook-attention"}
        ]
      }
    ]
  }
}
```

Note: The `idle_prompt` notification is automatically skipped since the Stop hook already handles "finished" notifications.

### Alternative: Project-specific hooks

For project-specific hooks, add to `.claude/settings.json` in your project root instead.

## Hook Details

### `wt hook-stop`

Called when Claude finishes responding. Sends a "Finished" notification.

**Input (JSON via stdin):**
```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../session.jsonl",
  "cwd": "/path/to/worktree",
  "hook_event_name": "Stop"
}
```

### `wt hook-attention`

Called when Claude needs user attention. The notification urgency depends on the type:

| Notification Type | Urgency | Sound |
|-------------------|---------|-------|
| `permission_prompt` | Critical | Yes |
| `idle_prompt` | Normal | No |
| Other | Normal | No |

**Input (JSON via stdin):**
```json
{
  "session_id": "abc123",
  "notification_type": "permission_prompt",
  "message": "Claude needs permission to use Bash",
  "cwd": "/path/to/worktree"
}
```

## Notification Matchers

The `matcher` field in hook configuration supports regex patterns:

| Pattern | Matches |
|---------|---------|
| `permission_prompt` | Permission request dialogs |
| `idle_prompt` | Idle after 60+ seconds |
| `permission_prompt\|idle_prompt` | Both types |
| (omitted) | All notification types |

## Troubleshooting

### Notifications not appearing

1. Verify hooks are configured:
   ```bash
   cat ~/.claude/settings.json
   ```

2. Test the hook command directly:
   ```bash
   echo '{"cwd": "/tmp", "hook_event_name": "Stop"}' | wt hook-stop
   ```

3. Check macOS notification permissions for Terminal/iTerm2

### tmux messages not visible

tmux display-message shows briefly in the status area. Increase display time:
```bash
tmux set-option -g display-time 4000  # 4 seconds
```

## See Also

- [Claude Code Hooks Documentation](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [CONFIG.md](CONFIG.md) - wt configuration options
