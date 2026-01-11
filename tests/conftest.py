"""Test fixtures for wt tests."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Generator

import pytest

from wt.config import Config


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository with an initial commit.

    Yields:
        Path to the repository root
    """
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    # Initialize repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    (repo_path / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    yield repo_path


@pytest.fixture
def temp_config(tmp_path: Path, temp_git_repo: Path) -> Generator[tuple[Path, Config], None, None]:
    """Create a temporary config file and Config instance.

    Yields:
        Tuple of (config_path, Config)
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Use a dedicated worktrees directory to avoid conflicts with the git repo
    worktrees_root = tmp_path / "worktrees"
    worktrees_root.mkdir()

    config_path = config_dir / "config.yaml"
    config_path.write_text(f"""branch_prefix: test
root: "{worktrees_root}"
default_profile: default

profiles:
  default:
    session_name: "{{{{topic}}}}-{{{{name}}}}"
    windows:
      - window_name: dev
        layout: main-vertical
        panes:
          - shell_command:
              - cd {{{{worktree_path}}}}
          - shell_command:
              - cd {{{{worktree_path}}}}
              - echo "Claude placeholder"
""")

    # Set environment variable
    old_config = os.environ.get("WT_CONFIG")
    os.environ["WT_CONFIG"] = str(config_path)

    config = Config.load(config_path)

    yield config_path, config

    # Restore environment
    if old_config is None:
        del os.environ["WT_CONFIG"]
    else:
        os.environ["WT_CONFIG"] = old_config


@pytest.fixture
def headless_tmux() -> Generator[str, None, None]:
    """Create an isolated tmux server for testing.

    Yields:
        Socket name for the test server
    """
    socket = f"wt-test-{uuid.uuid4().hex[:8]}"

    yield socket

    # Cleanup: kill the test server
    subprocess.run(
        ["tmux", "-L", socket, "kill-server"],
        check=False,
        capture_output=True,
    )
