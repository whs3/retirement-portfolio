"""Application configuration loaded from environment variables and optional files."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

# Project root (parent of the portfolio package)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ (no overwrite).

    Lines starting with # and blank lines are ignored. Values may be optionally
    wrapped in single or double quotes. Existing environment variables win.
    """
    env_path = path or (PROJECT_ROOT / ".env")
    if not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


def resolve_path(value: str, base: Path | None = None) -> str:
    """Return an absolute path; relative values are resolved against project root."""
    root = base or PROJECT_ROOT
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return str(path.resolve())


def resolve_secret_key(
    project_root: Path | None = None,
    *,
    env: dict[str, str] | None = None,
) -> str:
    """Return a stable Flask secret key.

    Precedence:
      1. ``SECRET_KEY`` environment variable
      2. Contents of ``SECRET_KEY_FILE`` (default: ``<project>/.secret_key``)
      3. Generate a new key, write it to the secret file (mode 0o600), and return it

    Persisting to a local file keeps CSRF tokens valid across process restarts
    when the operator has not set ``SECRET_KEY`` (common for home-lab installs).
    """
    root = project_root or PROJECT_ROOT
    environ = env if env is not None else os.environ

    env_key = (environ.get("SECRET_KEY") or "").strip()
    if env_key:
        return env_key

    key_file_raw = (environ.get("SECRET_KEY_FILE") or "").strip() or str(root / ".secret_key")
    key_file = Path(key_file_raw).expanduser()
    if not key_file.is_absolute():
        key_file = root / key_file

    if key_file.is_file():
        try:
            existing = key_file.read_text(encoding="utf-8").strip()
        except OSError:
            existing = ""
        if existing:
            return existing

    key = secrets.token_hex(32)
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        # Write privately when the OS supports it
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(str(key_file), flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key + "\n")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
    except OSError:
        # Fall back to an in-memory key if the file is not writable
        pass
    return key


# Load optional .env before reading configuration values
load_dotenv()


class Config:
    """Default configuration for the retirement portfolio app."""

    DATABASE = resolve_path(os.getenv("PORTFOLIO_DATABASE", "portfolio.db"))
    AUDIT_LOG = resolve_path(os.getenv("PORTFOLIO_AUDIT_LOG", "portfolio_audit.log"))
    SECRET_KEY = resolve_secret_key()
    SECRET_KEY_FILE = resolve_path(
        os.getenv("SECRET_KEY_FILE", str(PROJECT_ROOT / ".secret_key"))
    )
    WTF_CSRF_HEADERS = ["X-CSRFToken"]
    TEMPLATES_AUTO_RELOAD = True
    TESTING = False
    # flask-limiter: set False in tests to avoid rate-limit noise
    RATELIMIT_ENABLED = True


class TestConfig(Config):
    """In-memory / temp-file friendly config for pytest."""

    TESTING = True
    SECRET_KEY = "test-secret-key-not-for-production"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    TEMPLATES_AUTO_RELOAD = False
