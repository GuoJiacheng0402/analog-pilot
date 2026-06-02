"""Configuration loading for AnalogPilot.

Settings come from a ``.env`` file (searched: an explicit path, then ``./.env``,
then ``~/.apilot/.env``) and the process environment. All keys use the
``APILOT_`` prefix. Multi-server "profiles" are expressed as a case-sensitive
suffix on the key name, e.g. ``APILOT_REMOTE_HOST_lab2`` for profile ``lab2``.

This module is part of AnalogPilot's independently-written bridge engine.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is a declared dependency
    load_dotenv = None


def _default_env_path() -> Path:
    return Path.home() / ".apilot" / ".env"


def resolve_env_path(explicit: str | os.PathLike | None = None) -> Path | None:
    """Return the .env file to use, or None if none is found.

    A ``./.env`` in the current directory is used only if it actually looks like
    an AnalogPilot config (contains an ``APILOT_`` key); otherwise an unrelated
    project's ``.env`` would be picked up by mistake. Falls back to ``~/.apilot/.env``.
    """
    if explicit is not None:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(".env file not found: %s" % p)
        return p
    here = Path.cwd() / ".env"
    if here.is_file():
        try:
            if "APILOT_" in here.read_text(encoding="utf-8", errors="replace"):
                return here
        except OSError:
            pass
    user = _default_env_path()
    return user if user.is_file() else None


def load_env(explicit: str | os.PathLike | None = None) -> Path | None:
    """Load the resolved .env into the process environment (override=True)."""
    path = resolve_env_path(explicit)
    if path is not None and load_dotenv is not None:
        load_dotenv(path, override=True)
    return path


def _get(key: str, profile: str | None) -> str | None:
    """Read APILOT_<key>[_<profile>] from the environment."""
    if profile:
        val = os.environ.get("APILOT_%s_%s" % (key, profile))
        if val is not None:
            return val
    return os.environ.get("APILOT_%s" % key)


def _stable_port(seed: str, low: int = 49152, high: int = 65000) -> int:
    """Deterministic high port from a string (stable per remote user)."""
    h = 0
    for ch in seed:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return low + (h % (high - low))


@dataclass
class Settings:
    """Resolved connection settings for one profile."""

    remote_host: str
    remote_user: str
    remote_port: int            # daemon TCP port on the remote host
    local_port: int             # local port forwarded to remote_port
    jump_host: str | None = None
    jump_user: str | None = None
    scratch_root: str = ""      # remote dir for deployed bridge files
    disable_control_master: bool = True
    profile: str | None = None

    @property
    def ssh_target(self) -> str:
        return "%s@%s" % (self.remote_user, self.remote_host) if self.remote_user else self.remote_host

    @classmethod
    def from_env(cls, profile: str | None = None, env_path: str | os.PathLike | None = None) -> "Settings":
        load_env(env_path)
        host = _get("REMOTE_HOST", profile)
        if not host:
            raise RuntimeError(
                "APILOT_REMOTE_HOST is not set. Copy .env.example to ~/.apilot/.env "
                "and fill in your server and account."
            )
        user = _get("REMOTE_USER", profile) or ""
        seed = "%s@%s/%s" % (user, host, profile or "")
        remote_port = int(_get("REMOTE_PORT", profile) or _stable_port(seed))
        local_port = int(_get("LOCAL_PORT", profile) or (remote_port + 1))
        scratch = _get("REMOTE_SCRATCH_ROOT", profile) or ("/tmp/apilot_%s" % (user or "user"))
        dcm = (_get("DISABLE_CONTROL_MASTER", profile) or "true").strip().lower()
        return cls(
            remote_host=host,
            remote_user=user,
            remote_port=remote_port,
            local_port=local_port,
            jump_host=_get("JUMP_HOST", profile),
            jump_user=_get("JUMP_USER", profile),
            scratch_root=scratch,
            disable_control_master=dcm in ("1", "true", "yes", "on"),
            profile=profile,
        )
