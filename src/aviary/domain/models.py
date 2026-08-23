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
