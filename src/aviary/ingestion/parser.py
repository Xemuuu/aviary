"""Parsing FOMC statement HTML into the domain model."""

from __future__ import annotations

import re
from typing import Final

from bs4 import BeautifulSoup, Tag

from aviary.domain.models import (
    Decision,
    RateRange,
    RawStatement,
    SectionKind,
    Sentence,
    Statement,
    StatementKind,
)
from aviary.ingestion.segmentation import split_sentences
from aviary.logging import get_logger

log = get_logger(__name__)

_CONTAINER_SELECTORS: Final = "#article, #content, .col-xs-12.col-sm-8.col-md-8"

_RELEASE_LINE: Final = re.compile(r"^For (?:release|immediate release)\b", re.IGNORECASE)
_DATE_LINE: Final = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}$",
    re.IGNORECASE,
)
_MEDIA_LINE: Final = re.compile(r"^For media inquiries\b", re.IGNORECASE)
_IMPLEMENTATION_LINE: Final = re.compile(r"^Implementation Note\b", re.IGNORECASE)
_LAST_UPDATE_LINE: Final = re.compile(r"^Last Update\b", re.IGNORECASE)

_LEAD_VOTE: Final = re.compile(
    r"approved the following statement for release by a\s+(\d+)\s*[\u2013\u2014-]\s*(\d+)\s+vote",
    re.IGNORECASE,
)
_VOTING_LINE: Final = re.compile(r"^Voting (for|against)\b", re.IGNORECASE)
_DISSENT_LINE: Final = re.compile(r"^Voting against\b", re.IGNORECASE)

# Decision verbs are anchored on "target" because the Fed uses the same
# vocabulary for balance sheet actions ("decided to increase the size of the
# Federal Reserve's balance sheet"), which must not be read as a rate move.
_DECISION_ACTIVE: Final = re.compile(
    r"decided\s+(?:today\s+)?to\s+(maintain|keep|raise|increase|lower|reduce)\s+"
    r"(?:its\s+|the\s+)?target",
    re.IGNORECASE,
)
_DECISION_PASSIVE: Final = re.compile(
    r"will\s+(maintain|keep)\s+(?:its\s+|the\s+)?target\s+(?:range|for)",
    re.IGNORECASE,
)
# 2013-2015 tapering era: no decision verb, the statement reaffirms that the
# existing range stays in place.
_DECISION_CURRENT: Final = re.compile(
    r"(?:maintain|reaffirmed[^.]{0,40}?)\s+(?:the\s+|this\s+)?current[^.]{0,40}?target\s+range",
    re.IGNORECASE,
)
_DECISION_MAP: Final = {
    "maintain": Decision.MAINTAIN,
    "keep": Decision.MAINTAIN,
    "raise": Decision.RAISE,
    "increase": Decision.RAISE,
    "lower": Decision.LOWER,
    "reduce": Decision.LOWER,
}

_NUM: Final = r"[\d\u2010\u2011\u2012\u2013\-/]+"
_TARGET_RANGE: Final = re.compile(
    rf"target range for the federal funds rate"
    rf"(?:\s+by\s+{_NUM}\s+percentage\s+points?)?"
    rf",?\s+(?:at|to|of)\s*({_NUM})\s+to\s+({_NUM})\s+percent",
    re.IGNORECASE,
)
_TARGET_RANGE_PREFIX: Final = re.compile(
    rf"\b({_NUM})\s+to\s+({_NUM})\s+percent\s+target\s+range\s+for\s+the\s+federal\s+funds\s+rate",
    re.IGNORECASE,
)
_TARGET_LEVEL: Final = re.compile(
    rf"target for the federal funds rate[^.]{{0,80}}?\b(?:at|to)\s*({_NUM})\s+percent",
    re.IGNORECASE,
)


class ParseError(RuntimeError):
    """Raised when a statement cannot be parsed into the domain model."""


def _parse_fraction(raw: str) -> float:
    """Convert Fed rate notation into a float.

    Handles ``3``, ``1/4`` and ``3-1/2`` (meaning three and a half).
    """
    normalised = re.sub(r"[\u2010\u2011\u2012\u2013]", "-", raw)
    whole, _, fraction = normalised.partition("-")
    if not fraction:
        if "/" in whole:
            numerator, _, denominator = whole.partition("/")
            return int(numerator) / int(denominator)
        return float(whole)

    numerator, _, denominator = fraction.partition("/")
    return float(whole) + int(numerator) / int(denominator)


def _classify(text: str) -> SectionKind | None:
    """Return the section a paragraph belongs to, or None to discard it."""
    if not text:
        return None
    if _DATE_LINE.match(text) or _RELEASE_LINE.match(text):
        return None
    if _MEDIA_LINE.match(text) or _IMPLEMENTATION_LINE.match(text):
        return None
    if _LAST_UPDATE_LINE.match(text):
        return None
    if _VOTING_LINE.match(text):
        return SectionKind.VOTING
    if _LEAD_VOTE.search(text):
        return SectionKind.LEAD
    return SectionKind.BODY


def _extract_container(html: str) -> Tag:
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one(_CONTAINER_SELECTORS)
    if container is None:
        raise ParseError("no known article container found in document")
    return container


def _extract_decision(body_text: str) -> Decision:
    """Determine what the Committee did with the target rate."""
    if match := (_DECISION_ACTIVE.search(body_text) or _DECISION_PASSIVE.search(body_text)):
        return _DECISION_MAP[match.group(1).lower()]
    if _DECISION_CURRENT.search(body_text):
        return Decision.MAINTAIN
    return Decision.UNKNOWN


def _extract_rate(body_text: str) -> tuple[str, str] | None:
    """Return the raw lower and upper bounds of the target rate, if stated."""
    if match := (_TARGET_RANGE.search(body_text) or _TARGET_RANGE_PREFIX.search(body_text)):
        return match.group(1), match.group(2)
    if match := _TARGET_LEVEL.search(body_text):
        return match.group(1), match.group(1)
    return None


def parse_statement(raw: RawStatement) -> Statement:
    """Turn fetched HTML into a validated :class:`Statement`.

    Raises:
        ParseError: if the document has no recognisable structure or no body text.
    """
    container = _extract_container(raw.html)

    sentences: list[Sentence] = []
    votes_for: int | None = None
    votes_against: int | None = None
    has_dissent = False
    index = 0

    for paragraph in container.find_all("p"):
        text = " ".join(paragraph.get_text(" ", strip=True).split())
        kind = _classify(text)
        if kind is None:
            continue

        if kind is SectionKind.LEAD and (match := _LEAD_VOTE.search(text)):
            votes_for = int(match.group(1))
            votes_against = int(match.group(2))
        if _DISSENT_LINE.match(text):
            has_dissent = True

        for chunk in split_sentences(text):
            sentences.append(Sentence(index=index, section=kind, text=chunk))
            index += 1

    body = [s.text for s in sentences if s.section is SectionKind.BODY]
    if not body:
        raise ParseError(f"no body text extracted from {raw.slug}")

    body_text = " ".join(body)
    decision = _extract_decision(body_text)

    target_rate: RateRange | None = None
    if bounds := _extract_rate(body_text):
        try:
            target_rate = RateRange(
                lower=_parse_fraction(bounds[0]), upper=_parse_fraction(bounds[1])
            )
        except (ValueError, ZeroDivisionError):
            log.warning("rate_parse_failed", date=raw.released_on.isoformat(), raw=bounds)

    statement_kind = (
        StatementKind.POST_MEETING
        if any(s.section is SectionKind.VOTING for s in sentences)
        else StatementKind.OTHER
    )

    log.info(
        "statement_parsed",
        date=raw.released_on.isoformat(),
        kind=statement_kind.value,
        sentences=len(sentences),
        decision=decision.value,
        dissent=has_dissent,
    )

    return Statement(
        bank=raw.bank,
        released_on=raw.released_on,
        url=raw.url,
        kind=statement_kind,
        decision=decision,
        target_rate=target_rate,
        votes_for=votes_for,
        votes_against=votes_against,
        has_dissent=has_dissent,
        sentences=sentences,
    )
