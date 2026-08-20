"""Tests for the logging layer."""

import json

import pytest
from structlog.contextvars import get_contextvars
from structlog.testing import capture_logs

from aviary.logging import configure_logging, get_logger, node_context, run_context


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_logger_emits_event_and_fields() -> None:
    log = get_logger(__name__)

    with capture_logs() as logs:
        log.info("signals_extracted", count=5)

    assert len(logs) == 1
    assert logs[0]["event"] == "signals_extracted"
    assert logs[0]["count"] == 5


def test_run_context_binds_run_id() -> None:
    with run_context("abc123"):
        assert get_contextvars()["run_id"] == "abc123"

    assert "run_id" not in get_contextvars()


def test_node_context_is_scoped() -> None:
    with node_context("diff"):
        assert get_contextvars()["node"] == "diff"

    assert "node" not in get_contextvars()


def test_contexts_nest() -> None:
    with run_context("run-1"), node_context("extract", attempt=2):
        bound = get_contextvars()
        assert bound["run_id"] == "run-1"
        assert bound["node"] == "extract"
        assert bound["attempt"] == 2


def test_json_output_includes_bound_context(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("LOG_JSON", "true")
    from aviary.config import get_settings

    get_settings.cache_clear()
    configure_logging(force=True)

    log = get_logger(__name__)
    with run_context("run-9"), node_context("diff"):
        log.info("sentences_compared", added=3)

    entry = json.loads(capsys.readouterr().out.strip())
    assert entry["event"] == "sentences_compared"
    assert entry["run_id"] == "run-9"
    assert entry["node"] == "diff"
    assert entry["added"] == 3

    get_settings.cache_clear()
    configure_logging(force=True)
