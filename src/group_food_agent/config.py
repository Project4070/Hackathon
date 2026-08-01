"""Process configuration loading for CLI entry points."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_project_dotenv(dotenv_path: str | Path | None = None) -> Path | None:
    """Load local ``.env`` without overriding explicit process values."""

    if os.getenv("GROUP_FOOD_SKIP_DOTENV", "").lower() in {"1", "true", "yes"}:
        return None
    path = Path(dotenv_path) if dotenv_path is not None else Path.cwd() / ".env"
    path = path.resolve()
    if not path.is_file():
        return None
    load_dotenv(dotenv_path=path, override=False)
    return path
