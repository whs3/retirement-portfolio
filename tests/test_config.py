"""Tests for env config, stable SECRET_KEY, and path resolution."""

from __future__ import annotations

import os
from pathlib import Path

from portfolio.config import load_dotenv, resolve_path, resolve_secret_key


def test_resolve_path_relative_to_base(tmp_path):
    resolved = resolve_path("data/app.db", base=tmp_path)
    assert Path(resolved) == (tmp_path / "data" / "app.db").resolve()


def test_resolve_path_absolute_unchanged(tmp_path):
    abs_path = tmp_path / "abs.db"
    resolved = resolve_path(str(abs_path), base=tmp_path / "other")
    assert Path(resolved) == abs_path.resolve()


def test_load_dotenv_sets_missing_only(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "FOO=from_file\n"
        "BAR='quoted'\n"
        "export BAZ=exported\n"
        "PRESET=from_file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.delenv("BAR", raising=False)
    monkeypatch.delenv("BAZ", raising=False)
    monkeypatch.setenv("PRESET", "from_env")

    load_dotenv(env_file)

    assert os.environ["FOO"] == "from_file"
    assert os.environ["BAR"] == "quoted"
    assert os.environ["BAZ"] == "exported"
    assert os.environ["PRESET"] == "from_env"  # existing wins


def test_resolve_secret_key_prefers_env(tmp_path):
    key = resolve_secret_key(
        tmp_path,
        env={"SECRET_KEY": "env-secret-value"},
    )
    assert key == "env-secret-value"
    # Should not create a file when env is set
    assert not (tmp_path / ".secret_key").exists()


def test_resolve_secret_key_reads_existing_file(tmp_path):
    key_file = tmp_path / ".secret_key"
    key_file.write_text("persisted-secret\n", encoding="utf-8")
    key = resolve_secret_key(tmp_path, env={})
    assert key == "persisted-secret"


def test_resolve_secret_key_creates_stable_file(tmp_path):
    env: dict[str, str] = {}
    first = resolve_secret_key(tmp_path, env=env)
    second = resolve_secret_key(tmp_path, env=env)
    assert first == second
    assert len(first) == 64  # token_hex(32)
    key_file = tmp_path / ".secret_key"
    assert key_file.is_file()
    assert key_file.read_text(encoding="utf-8").strip() == first
    mode = key_file.stat().st_mode & 0o777
    assert mode == 0o600


def test_resolve_secret_key_custom_file(tmp_path):
    custom = tmp_path / "secrets" / "app.key"
    env = {"SECRET_KEY_FILE": str(custom)}
    key = resolve_secret_key(tmp_path, env=env)
    assert custom.is_file()
    assert custom.read_text(encoding="utf-8").strip() == key
