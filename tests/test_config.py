"""Tests for config module."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from wt.config import Config, ConfigError


class TestConfig:
    """Tests for Config class."""

    def test_load_from_path(self, tmp_path: Path) -> None:
        """Test loading config from explicit path."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("""
branch_prefix = "dave"
root = "/home/dave/projects"
default_profile = "default"

[profiles_dir]
path = "~/.config/wt/profiles"
""")

        config = Config.load(config_path)

        assert config.branch_prefix == "dave"
        assert config.root == Path("/home/dave/projects")
        assert config.default_profile == "default"

    def test_load_from_env_var(self, tmp_path: Path) -> None:
        """Test loading config from WT_CONFIG env var."""
        config_path = tmp_path / "my-config.toml"
        config_path.write_text("""
branch_prefix = "test"
root = "/tmp/test"
""")

        old_value = os.environ.get("WT_CONFIG")
        try:
            os.environ["WT_CONFIG"] = str(config_path)
            config = Config.load()
            assert config.branch_prefix == "test"
        finally:
            if old_value is None:
                del os.environ["WT_CONFIG"]
            else:
                os.environ["WT_CONFIG"] = old_value

    def test_missing_config_file(self, tmp_path: Path) -> None:
        """Test error when config file doesn't exist."""
        with pytest.raises(ConfigError, match="Config file not found"):
            Config.load(tmp_path / "nonexistent.toml")

    def test_missing_required_field(self, tmp_path: Path) -> None:
        """Test error when required field is missing."""
        config_path = tmp_path / "config.toml"
        config_path.write_text('root = "/tmp"')

        with pytest.raises(ConfigError, match="Missing required field: branch_prefix"):
            Config.load(config_path)

    def test_invalid_toml(self, tmp_path: Path) -> None:
        """Test error on invalid TOML."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("this is not valid toml [[[")

        with pytest.raises(ConfigError, match="Invalid TOML"):
            Config.load(config_path)

    def test_worktrees_dir(self, tmp_path: Path) -> None:
        """Test worktrees_dir property."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("""
branch_prefix = "test"
root = "/projects"
""")

        config = Config.load(config_path)
        assert config.worktrees_dir == Path("/projects/worktrees")

    def test_branch_name(self, tmp_path: Path) -> None:
        """Test branch_name method."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("""
branch_prefix = "dave"
root = "/projects"
""")

        config = Config.load(config_path)
        assert config.branch_name("feature", "auth") == "dave/feature/auth"

    def test_worktree_path(self, tmp_path: Path) -> None:
        """Test worktree_path method."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("""
branch_prefix = "dave"
root = "/projects"
""")

        config = Config.load(config_path)
        assert config.worktree_path("feature", "auth") == Path("/projects/worktrees/feature/auth")

    def test_parse_worktree_name_valid(self, tmp_path: Path) -> None:
        """Test parsing valid worktree name."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("""
branch_prefix = "test"
root = "/tmp"
""")

        config = Config.load(config_path)
        topic, name = config.parse_worktree_name("feature/auth")
        assert topic == "feature"
        assert name == "auth"

    def test_parse_worktree_name_with_slashes(self, tmp_path: Path) -> None:
        """Test parsing worktree name with extra slashes in name part."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("""
branch_prefix = "test"
root = "/tmp"
""")

        config = Config.load(config_path)
        topic, name = config.parse_worktree_name("feature/auth/oauth")
        assert topic == "feature"
        assert name == "auth/oauth"

    def test_parse_worktree_name_invalid(self, tmp_path: Path) -> None:
        """Test error on invalid worktree name."""
        config_path = tmp_path / "config.toml"
        config_path.write_text("""
branch_prefix = "test"
root = "/tmp"
""")

        config = Config.load(config_path)
        with pytest.raises(ConfigError, match="Invalid worktree name"):
            config.parse_worktree_name("no-slash")
