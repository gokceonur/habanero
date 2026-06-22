"""habanero — MCP server and CLI tools for Habanero iOS simulator control."""

from __future__ import annotations

import os
from pathlib import Path

__version__ = "1.1.7"


def _find_dylib() -> str:
    """Locate the Habanero dylib (framework binary).

    Resolution order:
    1. HABANERO_DYLIB_PATH (or legacy PEPPER_DYLIB_PATH) env var (explicit override).
    2. Package data (pip-installed): habanero/_dylib/Habanero.framework/Habanero.
    3. Development build dir: <repo>/build/Habanero.framework/Habanero.
    """
    # 1. Explicit env override (new name first, legacy fallback for back-compat)
    env_path = os.environ.get("HABANERO_DYLIB_PATH") or os.environ.get("PEPPER_DYLIB_PATH", "")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2. Installed package data
    pkg_dylib = Path(__file__).parent / "_dylib" / "Habanero.framework" / "Habanero"
    if pkg_dylib.is_file():
        return str(pkg_dylib)

    # 3. Development build directory (repo root / build / ...)
    repo_root = Path(__file__).parent.parent
    dev_dylib = repo_root / "build" / "Habanero.framework" / "Habanero"
    if dev_dylib.is_file():
        return str(dev_dylib)

    # 4. Auto-download from GitHub Releases (pip installs)
    try:
        from .dylib_fetch import ensure_dylib
        return ensure_dylib()
    except Exception:
        pass

    return ""
