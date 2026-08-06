from __future__ import annotations

import os
from pathlib import Path
import sys


def application_directory() -> Path:
    """Return the portable app root in source and PyInstaller modes."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def data_directory() -> Path:
    override = os.getenv("SPARK_AGENT_DATA_DIR", "").strip()
    return Path(override).expanduser().resolve() if override else application_directory() / "data"
