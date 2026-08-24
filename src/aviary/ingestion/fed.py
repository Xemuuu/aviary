"""Fetching FOMC statements from the Federal Reserve website."""

from __future__ import annotations

import asyncio
import re
from datetime import date
from pathlib import Path
from typing import Final

import httpx

from aviary.domain.models import Bank, RawStatement
from aviary.logging import get_logger, node_context

log = get_logger(__name__)

BASE_URL: Final = "https://www.federalreserve.gov"
CALENDAR_URL: Final = f"{BASE_URL}/monetarypolicy/fomccalendars.htm"
HISTORICAL_URL_TEMPLATE: Final = f"{BASE_URL}/monetarypolicy/fomchistorical{{year}}.htm"

EARLIEST_ARCHIVED_YEAR: Final = 2006
"""Archive pages below this year do not link statements in a recoverable format."""

_STATEMENT_HREF: Final = re.compile(
    r"/newsevents/(?:press/monetary/|pressreleases/monetary)(\d{8})a\.htm",
    re.IGNORECASE,
)

_REQUEST_TIMEOUT: Final = 30.0
_CONCURRENCY: Final = 4
_DELAY_BETWEEN_REQUESTS: Final = 0.5

USER_AGENT: Final = "aviary/0.1 (research project; +https://github.com/Xemuuu/aviary)"


class FetchError(RuntimeError):
    """Raised when a statement cannot be retrieved."""


def _cache_path(cache_dir: Path, slug: str) -> Path:
    return cache_dir / f"{slug}.html"


def _parse_release_date(raw: str) -> date:
    """Turn a ``YYYYMMDD`` fragment from a statement URL into a date."""
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def _listing_urls(since: date | None) -> list[str]:
    """Return the listing pages worth scanning for a given cutoff."""
    first_year = max(since.year if since else EARLIEST_ARCHIVED_YEAR, EARLIEST_ARCHIVED_YEAR)
    current_year = date.today().year

    years = range(first_year, current_year + 1)
    return [CALENDAR_URL, *(HISTORICAL_URL_TEMPLATE.format(year=y) for y in years)]


async def discover_statement_urls(
    client: httpx.AsyncClient,
    *,
    since: date | None = None,
) -> dict[date, str]:
    """Return statement URLs keyed by release date.

    Scans the current calendar page plus one archive page per year, since the
    Fed publishes historical materials year by year rather than in a single
    listing.
    """
    found: dict[date, str] = {}
    unreachable: list[str] = []

    for listing in _listing_urls(since):
        try:
            response = await client.get(listing)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            unreachable.append(listing)
            log.warning("listing_fetch_failed", url=listing, error=str(exc))
            continue

        matches = 0
        for match in _STATEMENT_HREF.finditer(response.text):
            released_on = _parse_release_date(match.group(1))
            if since is not None and released_on < since:
                continue
            found[released_on] = f"{BASE_URL}{match.group(0)}"
            matches += 1

        if matches == 0:
            log.warning("listing_yielded_nothing", url=listing)

    if unreachable:
        log.error("listings_unreachable", count=len(unreachable), urls=unreachable[:5])

    log.info("statements_discovered", count=len(found), listings=len(_listing_urls(since)))
    return found


async def _fetch_one(
    client: httpx.AsyncClient,
    released_on: date,
    url: str,
    cache_dir: Path,
    semaphore: asyncio.Semaphore,
) -> RawStatement | None:
    """Fetch a single statement, serving from cache when available."""
    slug = f"{Bank.FED.value}-{released_on.isoformat()}"
    cached = _cache_path(cache_dir, slug)

    if cached.exists():
        return RawStatement(
            bank=Bank.FED,
            released_on=released_on,
            url=url,
            html=cached.read_text(encoding="utf-8"),
        )

    async with semaphore:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("statement_fetch_failed", date=released_on.isoformat(), error=str(exc))
            return None

        await asyncio.sleep(_DELAY_BETWEEN_REQUESTS)

    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(response.text, encoding="utf-8")

    log.info("statement_fetched", date=released_on.isoformat(), bytes=len(response.text))
    return RawStatement(
        bank=Bank.FED,
        released_on=released_on,
        url=url,
        html=response.text,
    )


async def fetch_statements(
    cache_dir: Path,
    *,
    since: date | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[RawStatement]:
    """Fetch all FOMC statements released on or after ``since``.

    Results are cached on disk, so repeated runs do not hit the network.
    Individual failures are logged and skipped rather than aborting the run.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )

    try:
        with node_context("fetch_fed"):
            urls = await discover_statement_urls(client, since=since)
            semaphore = asyncio.Semaphore(_CONCURRENCY)

            results = await asyncio.gather(
                *(
                    _fetch_one(client, released_on, url, cache_dir, semaphore)
                    for released_on, url in sorted(urls.items())
                )
            )

            statements = [s for s in results if s is not None]
            log.info(
                "fetch_complete",
                requested=len(urls),
                retrieved=len(statements),
                failed=len(urls) - len(statements),
            )
            return statements
    finally:
        if owns_client:
            await client.aclose()
