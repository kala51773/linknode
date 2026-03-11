"""Compatibility package for src-layout imports without installation."""

from __future__ import annotations

from pathlib import Path

__all__ = ["__version__"]
__version__ = "0.1.0"

_pkg_dir = Path(__file__).resolve().parent
_src_pkg = _pkg_dir.parent / "src" / "wickhunter"

# Redirect package discovery to src/wickhunter so submodules resolve correctly.
__path__ = [str(_src_pkg)]
