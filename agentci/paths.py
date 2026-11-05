"""Profile-relative locations, resolved like core does."""

from __future__ import annotations

import os
from pathlib import Path


def hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(get_hermes_home())
    except Exception:  # pragma: no cover
        local = os.environ.get("LOCALAPPDATA")
        if local and (Path(local) / "hermes").exists():
            return Path(local) / "hermes"
        return Path.home() / ".hermes"


def state_db() -> Path:
    return hermes_home() / "state.db"


def runs_dir() -> Path:
    path = hermes_home() / "agentci" / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path
