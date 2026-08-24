"""Sentence segmentation tuned for central bank statements."""

from __future__ import annotations

import re
from typing import Final

_SENTINEL: Final = "\x00"

# Periods that must not end a sentence: initials in names ("Jerome H. Powell"),
# common abbreviations, and decimal points in figures.
_PROTECTED: Final = re.compile(
    r"""
    \b[A-Z]\.                      # single initial
    | \bU\.S\.(?:A\.)?             # U.S., U.S.A.
    | \bU\.K\.
    | \b[ap]\.m\.
    | \b(?:e\.g|i\.e)\.
    | \b(?:Mr|Mrs|Ms|Dr|Prof|Jr|Sr|St|No|vs|etc|Inc|Corp)\.
    | (?<=\d)\.(?=\d)              # decimal point
    """,
    re.VERBOSE,
)

_BOUNDARY: Final = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE: Final = re.compile(r"\s+")


def _protect(text: str) -> str:
    return _PROTECTED.sub(lambda m: m.group(0).replace(".", _SENTINEL), text)


def _restore(text: str) -> str:
    return text.replace(_SENTINEL, ".")


def split_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences.

    Uses a protect-split-restore pass rather than a naive punctuation split,
    since FOMC text is dense with initials, abbreviations and decimals that
    would otherwise produce spurious boundaries.
    """
    normalised = _WHITESPACE.sub(" ", text).strip()
    if not normalised:
        return []

    parts = _BOUNDARY.split(_protect(normalised))
    return [restored for part in parts if (restored := _restore(part).strip())]
