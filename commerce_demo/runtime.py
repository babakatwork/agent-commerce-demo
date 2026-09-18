"""Trusted host state. Capabilities are injected by the application, never by the LLM."""
import os
from pathlib import Path
from .arbiter import Arbiter

ROOT = Path(__file__).resolve().parent.parent
_arbiter = None


def configure(arbiter):
    global _arbiter
    _arbiter = arbiter


def authority():
    global _arbiter
    if _arbiter is None:
        _arbiter = Arbiter(os.environ.get("COMMERCE_DB", str(ROOT / ".runtime" / "commerce.sqlite")))
    return _arbiter
