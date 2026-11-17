"""「复制爆款」解析层（P0）。

Deterministic decomposition of a reference video into a beat-level skeleton:
structure, speech, speakers, rhythm, visual tags, on-screen text.  The gag
extraction and generation stages live in later phases; this package never
generates anything.
"""

from __future__ import annotations

from adplus.recreate.extract import analyze

__all__ = ["analyze"]
