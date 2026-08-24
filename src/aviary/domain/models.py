"""Core domain models shared across the pipeline."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Bank(StrEnum):
    FED = "fed"


class RawStatement(BaseModel):
    """An unparsed statement as fetched from the source.

    Holds the original HTML plus enough metadata to locate and order it.
    Parsing into structured content happens downstream.
    """

    model_config = ConfigDict(frozen=True)

    bank: Bank
    released_on: date = Field(description="Date the statement was published.")
    url: HttpUrl
    html: str = Field(repr=False)

    @property
    def slug(self) -> str:
        """Stable identifier used for cache filenames."""
        return f"{self.bank.value}-{self.released_on.isoformat()}"


class Decision(StrEnum):
    """What the Committee did with the target rate."""

    MAINTAIN = "maintain"
    RAISE = "raise"
    LOWER = "lower"
    UNKNOWN = "unknown"


class SectionKind(StrEnum):
    """Which part of a statement a sentence belongs to."""

    LEAD = "lead"
    BODY = "body"
    VOTING = "voting"


class RateRange(BaseModel):
    """Target range for the federal funds rate, in percent."""

    model_config = ConfigDict(frozen=True)

    lower: float = Field(ge=0)
    upper: float = Field(ge=0)

    def __str__(self) -> str:
        return f"{self.lower:g}-{self.upper:g}%"


class Sentence(BaseModel):
    """A single sentence, positioned within the statement."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    section: SectionKind
    text: str = Field(min_length=1)


class Statement(BaseModel):
    """A parsed central bank statement.

    Sentence-level segmentation is the unit the diff node operates on,
    so ordering and indices are part of the contract.
    """

    model_config = ConfigDict(frozen=True)

    bank: Bank
    released_on: date
    url: HttpUrl
    kind: StatementKind
    decision: Decision
    target_rate: RateRange | None
    votes_for: int | None
    votes_against: int | None
    has_dissent: bool
    sentences: list[Sentence]

    @property
    def full_text(self) -> str:
        return " ".join(s.text for s in self.sentences)

    def section(self, kind: SectionKind) -> list[Sentence]:
        """Return sentences belonging to one section, in order."""
        return [s for s in self.sentences if s.section is kind]


class StatementKind(StrEnum):
    """Whether a document is a regular post-meeting statement."""

    POST_MEETING = "post_meeting"
    OTHER = "other"
