"""Tests for the configuration layer."""

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from aviary.config import Settings


class IsolatedSettings(Settings):
    """Settings that ignore any developer ``.env`` file on disk."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)


def test_settings_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = IsolatedSettings()

    assert settings.openai_api_key.get_secret_value() == "sk-test"
    assert settings.log_level == "DEBUG"
    assert settings.qdrant_url == "http://localhost:6333"


def test_missing_required_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        IsolatedSettings()

    assert "openai_api_key" in str(exc_info.value)


def test_invalid_log_level_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError):
        IsolatedSettings()


def test_settings_are_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = IsolatedSettings()

    with pytest.raises(ValidationError):
        settings.qdrant_url = "http://elsewhere:6333"  # type: ignore[misc]
