"""Configuration loading and validation."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "wt" / "config.toml"


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


@dataclass
class Config:
    """Application configuration loaded from TOML file."""

    branch_prefix: str
    root: Path
    default_profile: str
    profiles_dir: Path

    @classmethod
    def load(cls, config_path: Path | None = None) -> Config:
        """Load configuration from file.

        Args:
            config_path: Path to config file. If None, uses WT_CONFIG env var
                        or falls back to ~/.config/wt/config.toml

        Returns:
            Loaded Config instance

        Raises:
            ConfigError: If config file is missing or invalid
        """
        if config_path is None:
            env_path = os.environ.get("WT_CONFIG")
            config_path = Path(env_path) if env_path else DEFAULT_CONFIG_PATH

        config_path = config_path.expanduser()

        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")

        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"Invalid TOML in {config_path}: {e}") from e

        # Required fields
        if "branch_prefix" not in data:
            raise ConfigError("Missing required field: branch_prefix")
        if "root" not in data:
            raise ConfigError("Missing required field: root")

        # Parse paths
        root = Path(data["root"]).expanduser()

        # Optional fields with defaults
        default_profile = data.get("default_profile", "default")

        profiles_dir_data = data.get("profiles_dir", {})
        if isinstance(profiles_dir_data, dict):
            profiles_dir = Path(profiles_dir_data.get("path", "~/.config/wt/profiles"))
        else:
            profiles_dir = Path(profiles_dir_data)
        profiles_dir = profiles_dir.expanduser()

        return cls(
            branch_prefix=data["branch_prefix"],
            root=root,
            default_profile=default_profile,
            profiles_dir=profiles_dir,
        )

    @property
    def worktrees_dir(self) -> Path:
        """Directory where worktrees are stored."""
        return self.root / "worktrees"

    def branch_name(self, topic: str, name: str) -> str:
        """Generate full branch name from topic and name."""
        return f"{self.branch_prefix}/{topic}/{name}"

    def worktree_path(self, topic: str, name: str) -> Path:
        """Generate worktree path from topic and name."""
        return self.worktrees_dir / topic / name

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
