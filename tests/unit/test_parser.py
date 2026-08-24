"""Tests for FOMC statement parsing."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from aviary.domain.models import Bank, Decision, RawStatement, SectionKind, StatementKind
from aviary.ingestion.parser import ParseError, _parse_fraction, parse_statement

FIXTURES = Path(__file__).parent.parent / "fixtures"

ALL_FIXTURES = [
    "fed-2006-08-08",
    "fed-2014-06-18",
    "fed-2017-12-13",
    "fed-2024-09-18",
    "fed-2026-07-29",
]


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _load(slug: str) -> RawStatement:
    released_on = date.fromisoformat(slug.removeprefix("fed-"))
    return RawStatement(
        bank=Bank.FED,
        released_on=released_on,
        url=(
            "https://www.federalreserve.gov/newsevents/pressreleases/"
            f"monetary{released_on:%Y%m%d}a.htm"
        ),
        html=(FIXTURES / f"{slug}.html").read_text(encoding="utf-8"),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3", 3.0),
        ("1/4", 0.25),
        ("3-1/2", 3.5),
        ("5-3/4", 5.75),
        ("1\u20111/2", 1.5),  # non-breaking hyphen
    ],
)
def test_parse_fraction(raw: str, expected: float) -> None:
    assert _parse_fraction(raw) == expected


@pytest.mark.parametrize("slug", ALL_FIXTURES)
def test_every_layout_yields_a_complete_statement(slug: str) -> None:
    statement = parse_statement(_load(slug))

    assert statement.kind is StatementKind.POST_MEETING
    assert statement.decision is not Decision.UNKNOWN
    assert statement.target_rate is not None
    assert statement.section(SectionKind.BODY)
    assert statement.section(SectionKind.VOTING)


@pytest.mark.parametrize("slug", ALL_FIXTURES)
def test_sentences_are_contiguous_and_non_empty(slug: str) -> None:
    statement = parse_statement(_load(slug))

    assert [s.index for s in statement.sentences] == list(range(len(statement.sentences)))
    assert all(s.text.strip() for s in statement.sentences)


@pytest.mark.parametrize("slug", ALL_FIXTURES)
def test_boilerplate_is_dropped(slug: str) -> None:
    text = parse_statement(_load(slug)).full_text

    assert "Implementation Note" not in text
    assert "For media inquiries" not in text
    assert "For release at" not in text
    assert "For immediate release" not in text


@pytest.mark.parametrize(
    ("slug", "decision", "lower", "upper"),
    [
        ("fed-2006-08-08", Decision.MAINTAIN, 5.25, 5.25),  # single level, pre-2008
        ("fed-2014-06-18", Decision.MAINTAIN, 0.0, 0.25),  # range stated before the phrase
        ("fed-2017-12-13", Decision.RAISE, 1.25, 1.5),  # non-breaking hyphens
        ("fed-2024-09-18", Decision.LOWER, 4.75, 5.0),  # "by 1/2 percentage point to"
    ],
)
def test_decision_and_rate_across_regimes(
    slug: str, decision: Decision, lower: float, upper: float
) -> None:
    statement = parse_statement(_load(slug))

    assert statement.decision is decision
    assert statement.target_rate is not None
    assert statement.target_rate.lower == lower
    assert statement.target_rate.upper == upper


def test_balance_sheet_language_is_not_read_as_a_rate_move() -> None:
    """The Fed uses "decided to increase" for asset purchases too."""
    statement = parse_statement(_load("fed-2014-06-18"))

    assert statement.decision is Decision.MAINTAIN


def test_lead_vote_count_is_extracted_when_present() -> None:
    statement = parse_statement(_load("fed-2026-07-29"))

    assert statement.votes_for == 9
    assert statement.votes_against == 3
    assert statement.has_dissent is True


def test_older_layout_has_no_lead_section() -> None:
    statement = parse_statement(_load("fed-2006-08-08"))

    assert statement.votes_for is None
    assert not statement.section(SectionKind.LEAD)


def test_non_meeting_document_is_classified_as_other() -> None:
    statement = parse_statement(_load("fed-2020-03-23"))

    assert statement.kind is StatementKind.OTHER
    assert statement.decision is Decision.UNKNOWN


def test_missing_container_raises() -> None:
    raw = RawStatement(
        bank=Bank.FED,
        released_on=date(2024, 1, 31),
        url="https://www.federalreserve.gov/newsevents/pressreleases/monetary20240131a.htm",
        html="<html><body><div>nothing here</div></body></html>",
    )

    with pytest.raises(ParseError, match="container"):
        parse_statement(raw)


def test_body_with_only_boilerplate_raises() -> None:
    raw = RawStatement(
        bank=Bank.FED,
        released_on=date(2024, 1, 31),
        url="https://www.federalreserve.gov/newsevents/pressreleases/monetary20240131a.htm",
        html=(
            '<html><body><div id="content"><p>For release at 2:00 p.m. EST</p></div></body></html>'
        ),
    )

    with pytest.raises(ParseError, match="no body text"):
        parse_statement(raw)
