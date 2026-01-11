# Shell Completion

Enable tab completion for commands, worktree names, and options.

First, find where `wt` is installed:
```bash
which wt
# e.g., /Users/dave/projects/wt/.venv/bin/wt
```

Use the same directory for `register-python-argcomplete`.

## Zsh

Add to `~/.zshrc`:
```zsh
autoload -Uz compinit && compinit
eval "$(/path/to/.venv/bin/register-python-argcomplete wt)"
```

## Bash

Add to `~/.bashrc`:
```bash
eval "$(/path/to/.venv/bin/register-python-argcomplete wt)"
```

## Fish

Run once:
```fish
/path/to/.venv/bin/register-python-argcomplete --shell fish wt > ~/.config/fish/completions/wt.fish
```

## What Gets Completed

After setup, tab completion works for:
- Subcommands (`wt <tab>` → `go`, `list`, `fg`, etc.)
- Worktree names (`wt feature/<tab>` → existing worktrees)
- Session names (`wt fg <tab>` → backgrounded sessions)
- Profile names (`wt go --profile <tab>` → available profiles)
