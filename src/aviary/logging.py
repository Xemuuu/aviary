"""Structured logging configuration."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import uuid4

import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars
from structlog.typing import FilteringBoundLogger

from aviary.config import get_settings

_configured = False


def configure_logging(*, force: bool = False) -> None:
    """
    Configure structlog for the current process.

    Safe to call more than once
    """
    global _configured
    if _configured and not force:
        return

    settings = get_settings()

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """Return a logger, configuring logging on first use."""
    configure_logging()
    return cast("FilteringBoundLogger", structlog.get_logger(name))


def new_run_id() -> str:
    """Return a short identifier for a single graph execution."""
    return uuid4().hex[:8]


@contextmanager
def run_context(run_id: str | None = None) -> Iterator[str]:
    """Bind a run identifier to every log emitted inside the block."""
    rid = run_id or new_run_id()
    bind_contextvars(run_id=rid)
    try:
        yield rid
    finally:
        unbind_contextvars("run_id")


@contextmanager
def node_context(node: str, **extra: Any) -> Iterator[None]:
    """Bind a node name, and any extra fields, for the duration of the block."""
    bind_contextvars(node=node, **extra)
    try:
        yield
    finally:
        unbind_contextvars("node", *extra)
