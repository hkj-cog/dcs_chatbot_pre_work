"""Tests for observability bootstrap using InMemorySpanExporter — no GCP credentials required."""
from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from libs import observability


@pytest.fixture(autouse=True)
def _reset_observability():
    observability._reset_for_tests()
    yield
    observability._reset_for_tests()


def _clear_settings_cache():
    from libs.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_disabled_returns_none(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "false")
    _clear_settings_cache()
    assert observability.init_observability() is None


def test_enabled_creates_provider_and_emits_spans(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("OBSERVABILITY_EXPORT_TO_GCP", "false")
    _clear_settings_cache()

    exporter = InMemorySpanExporter()
    provider = observability.init_observability(extra_processors=[SimpleSpanProcessor(exporter)])
    assert isinstance(provider, TracerProvider)

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("unit") as span:
        span.set_attribute("hello", "world")

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "unit"
    assert spans[0].attributes.get("hello") == "world"


def test_record_exception_marks_span_error(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("OBSERVABILITY_EXPORT_TO_GCP", "false")
    _clear_settings_cache()

    exporter = InMemorySpanExporter()
    observability.init_observability(extra_processors=[SimpleSpanProcessor(exporter)])

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("err"):
        observability.record_exception_on_span(ValueError("boom"))
    finished = exporter.get_finished_spans()[0]
    assert finished.status.status_code.name == "ERROR"
    assert any(e.name == "exception" for e in finished.events)


def test_with_session_attrs_sets_span_attributes(monkeypatch):
    monkeypatch.setenv("OBSERVABILITY_ENABLED", "true")
    monkeypatch.setenv("OBSERVABILITY_EXPORT_TO_GCP", "false")
    _clear_settings_cache()

    exporter = InMemorySpanExporter()
    observability.init_observability(extra_processors=[SimpleSpanProcessor(exporter)])

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("s"):
        with observability.with_session_attrs(session_id="sess-1", user_id="u-1"):
            pass

    finished = exporter.get_finished_spans()[0]
    assert finished.attributes.get("session.id") == "sess-1"
    assert finished.attributes.get("user.id") == "u-1"
