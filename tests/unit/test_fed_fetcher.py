"""Tests for the FOMC fetcher."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from aviary.ingestion.fed import (
    _parse_release_date,
    discover_statement_urls,
    fetch_statements,
)

LISTING_HTML = """
<html><body>
  <a href="/newsevents/pressreleases/monetary20240131a.htm">January 31, 2024</a>
  <a href="/newsevents/pressreleases/monetary20240320a.htm">March 20, 2024</a>
  <a href="/newsevents/pressreleases/monetary20231213a.htm">December 13, 2023</a>
  <a href="/monetarypolicy/files/monetary20240131a1.pdf">PDF</a>
</body></html>
"""

STATEMENT_HTML = (
    "<html><body><p>The Committee decided to maintain the target range.</p></body></html>"
)


def _transport(*, fail_on: set[str] | None = None) -> httpx.MockTransport:
    failing = fail_on or set()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in failing:
            return httpx.Response(500)
        if "fomccalendars" in path or "fomc_historical" in path:
            return httpx.Response(200, text=LISTING_HTML)
        return httpx.Response(200, text=STATEMENT_HTML)

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_parse_release_date() -> None:
    assert _parse_release_date("20240131") == date(2024, 1, 31)


@pytest.mark.asyncio
async def test_discover_finds_statement_urls() -> None:
    async with httpx.AsyncClient(transport=_transport()) as client:
        urls = await discover_statement_urls(client)

    assert set(urls) == {date(2023, 12, 13), date(2024, 1, 31), date(2024, 3, 20)}
    assert urls[date(2024, 1, 31)].endswith("monetary20240131a.htm")


@pytest.mark.asyncio
async def test_discover_respects_since_cutoff() -> None:
    async with httpx.AsyncClient(transport=_transport()) as client:
        urls = await discover_statement_urls(client, since=date(2024, 1, 1))

    assert date(2023, 12, 13) not in urls
    assert len(urls) == 2


@pytest.mark.asyncio
async def test_fetch_writes_cache(tmp_path: Path) -> None:
    async with httpx.AsyncClient(transport=_transport()) as client:
        statements = await fetch_statements(tmp_path, client=client)

    assert len(statements) == 3
    assert (tmp_path / "fed-2024-01-31.html").exists()
    assert statements[0].bank.value == "fed"


@pytest.mark.asyncio
async def test_fetch_serves_from_cache(tmp_path: Path) -> None:
    (tmp_path / "fed-2024-01-31.html").write_text("<html>cached</html>", encoding="utf-8")

    async with httpx.AsyncClient(transport=_transport()) as client:
        statements = await fetch_statements(tmp_path, client=client)

    cached = next(s for s in statements if s.released_on == date(2024, 1, 31))
    assert "cached" in cached.html


@pytest.mark.asyncio
async def test_fetch_skips_failures(tmp_path: Path) -> None:
    transport = _transport(fail_on={"/newsevents/pressreleases/monetary20240320a.htm"})

    async with httpx.AsyncClient(transport=transport) as client:
        statements = await fetch_statements(tmp_path, client=client)

    assert len(statements) == 2
    assert all(s.released_on != date(2024, 3, 20) for s in statements)
