"""
Cauveris: Autonomous reality debugger for AI-powered robotic systems.
"""

from __future__ import annotations

import subprocess
from importlib.metadata import PackageNotFoundError, version as _pkg_version


def _resolve_version() -> str:
    """
    Resolve the application version using a production-grade hierarchy:
    1. Installed package metadata (e.g. from setuptools/uv/wheel).
    2. Git describe tag from active repository.
    3. Production release constant matching latest GitHub release.
    """
    try:
        ver = _pkg_version("cauveris")
        if ver and ver != "0.0.0":
            return ver
    except PackageNotFoundError:
        pass

    try:
        git_tag = (
            subprocess.check_output(
                ["git", "describe", "--tags", "--abbrev=0"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            .strip()
            .lstrip("v")
        )
        if git_tag:
            return git_tag
    except Exception:
        pass

    return "3.1.0"


__version__: str = _resolve_version()
__all__ = ["__version__"]
