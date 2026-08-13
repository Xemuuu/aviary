# Aviary

Multi-agent system for analysing central bank communication. Extracts policy
signals from monetary policy statements by diffing them against previous
releases, then branches into parallel scenario analyses.

> **Status:** work in progress. Not investment advice — this is an analytical
> tool, not a forecasting or trading system.

## Stack

Python 3.12 · LangGraph · Qdrant · fastembed · Pydantic · uv

## Quickstart

```bash
docker compose up -d
uv sync
uv run aviary --help
```

## License

MIT
