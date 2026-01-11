"""Configuration loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATHS = [
    Path.home() / ".config" / "wt" / "config.yaml",
    Path.home() / ".config" / "wt" / "config.yml",
]

DEFAULT_PROFILE = {
    "session_name": "{{topic}}-{{name}}",
    "windows": [
        {
            "window_name": "dev",
            "layout": "main-vertical",
            "panes": [
                {"shell_command": ["cd {{worktree_path}}"]},
                {"shell_command": ["cd {{worktree_path}}", "claude --continue"]},
            ],
        }
    ],
}


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


@dataclass
class Config:
    """Application configuration loaded from YAML file."""

    branch_prefix: str
    root: Path
    default_profile: str
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    main_repo: Path | None = None
    trunk: str | None = None  # Primary branch (main, master, etc.) - auto-detected if not set

    @classmethod
    def load(cls, config_path: Path | None = None) -> Config:
        """Load configuration from file.

        Args:
            config_path: Path to config file. If None, uses WT_CONFIG env var
                        or falls back to ~/.config/wt/config.yaml

        Returns:
            Loaded Config instance

        Raises:
            ConfigError: If config file is missing or invalid
        """
        if config_path is None:
            env_path = os.environ.get("WT_CONFIG")
            if env_path:
                config_path = Path(env_path).expanduser()
            else:
                # Try default paths in order
                for default_path in DEFAULT_CONFIG_PATHS:
                    if default_path.exists():
                        config_path = default_path
                        break
                else:
                    raise ConfigError(
                        f"Config file not found. Tried: {', '.join(str(p) for p in DEFAULT_CONFIG_PATHS)}"
                    )
        else:
            config_path = config_path.expanduser()

        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {config_path}: {e}") from e

        if data is None:
            data = {}

        # Required fields
        if "branch_prefix" not in data:
            raise ConfigError("Missing required field: branch_prefix")
        if "root" not in data:
            raise ConfigError("Missing required field: root")

        # Parse paths
        root = Path(data["root"]).expanduser()
        main_repo = Path(data["main_repo"]).expanduser() if data.get("main_repo") else None

        # Optional fields with defaults
        default_profile = data.get("default_profile", "default")

        # Load profiles - ensure "default" always exists
        profiles = data.get("profiles", {})
        if "default" not in profiles:
            profiles["default"] = DEFAULT_PROFILE

        # Optional trunk branch (for graphite)
        trunk = data.get("trunk")

        return cls(
            branch_prefix=data["branch_prefix"],
            root=root,
            default_profile=default_profile,
            profiles=profiles,
            main_repo=main_repo,
            trunk=trunk,
        )

    def branch_name(self, topic: str, name: str) -> str:
        """Generate full branch name from topic and name."""
        return f"{self.branch_prefix}/{topic}/{name}"

    def worktree_path(self, topic: str, name: str) -> Path:
        """Generate worktree path from topic and name.

        Worktrees are stored at $ROOT/<topic>/<name>.
        """
        return self.root / topic / name

    def get_profile(self, name: str | None = None) -> dict[str, Any]:
        """Get a profile by name.

        Args:
            name: Profile name (defaults to default_profile)

        Returns:
            Profile configuration dict

        Raises:
            ConfigError: If profile not found
        """
        profile_name = name or self.default_profile
        if profile_name not in self.profiles:
            raise ConfigError(f"Profile not found: {profile_name}")
        return self.profiles[profile_name]

    def parse_worktree_name(self, name: str) -> tuple[str, str]:
        """Parse a topic/name string into (topic, name) tuple.

        Args:
            name: String in format "topic/name"

        Returns:
            Tuple of (topic, name)

        Raises:
            ConfigError: If name format is invalid
        """
        parts = name.split("/", 1)
        if len(parts) != 2:
            raise ConfigError(f"Invalid worktree name '{name}': expected format 'topic/name'")
        return parts[0], parts[1]
