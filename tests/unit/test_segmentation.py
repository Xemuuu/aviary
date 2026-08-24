"""Tests for sentence segmentation."""

from __future__ import annotations

import pytest

from aviary.ingestion.segmentation import split_sentences


def test_splits_on_sentence_boundaries() -> None:
    assert split_sentences("Inflation eased. Growth slowed. Risks remain.") == [
        "Inflation eased.",
        "Growth slowed.",
        "Risks remain.",
    ]


def test_protects_initials_in_names() -> None:
    text = "Voting for were Jerome H. Powell, Chair, and John C. Williams, Vice Chair."
    assert split_sentences(text) == [text]


def test_protects_decimals_and_abbreviations() -> None:
    text = "The U.S. economy grew 2.5 percent. Prices rose at 2 p.m. yesterday."
    assert split_sentences(text) == [
        "The U.S. economy grew 2.5 percent.",
        "Prices rose at 2 p.m. yesterday.",
    ]


def test_normalises_whitespace() -> None:
    assert split_sentences("  Growth   slowed.\n\n  Risks  remain. ") == [
        "Growth slowed.",
        "Risks remain.",
    ]


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_returns_empty_for_blank_input(text: str) -> None:
    assert split_sentences(text) == []
