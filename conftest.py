"""Repo-root pytest bootstrap: makes `shared` and backend's `app` importable
without needing an editable install -- kept intentionally minimal (hackathon
feasibility over packaging ceremony)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
