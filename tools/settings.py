"""Local settings: this repo's .env (not in git) fills the environment variables not set already."""

import os
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1]


def load_env():
    """Set each KEY=VALUE of .env that the environment doesn't already have."""
    env = WORKFLOW / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))
