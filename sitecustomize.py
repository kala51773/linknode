"""Repository-local Python startup customization.

Ensures src-layout imports (``import wickhunter``) work in ad-hoc commands such as
``python -m unittest discover`` without requiring users to export PYTHONPATH=src.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.exists():
    src_str = str(_SRC)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
