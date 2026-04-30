"""Bootstraps OTel TracerProvider, GCP exporters, ratio sampling, and FastAPI instrumentation. Idempotent, fail-soft."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator, Optional

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Status, StatusCode

from libs.config import get_settings

_initialized: bool = False
_tracer_provider: Optional[TracerProvider] = None
_log = logging.getLogger("dcs_chatbot.observability")


def _build_resource(settings) -> Resource:
    # Builds an OTel Resource with service name, namespace, version, and deploy environment.
    return Resource.create(
        {
            "service.name": settings.service_name,
            "service.namespace": "dcs",
            "service.version": os.getenv("SERVICE_VERSION", "dev"),
            "deployment.environment": os.getenv("DEPLOY_ENV", "local"),
        }
    )


def _attach_gcp(provider: TracerProvider) -> None:
    # Attaches Cloud Trace span exporter and Cloud Logging log bridge; both fail-soft.
    try:
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        _log.info("[Observability] GCP Cloud Trace exporter attached.")
    except Exception as e:  # pragma: no cover
        _log.warning(f"[Observability] GCP Cloud Trace attach failed: {e}")

    # Wire the GCP Cloud Logging bridge so OTel log records carry session_id/user_id.
    try:
        from opentelemetry import _logs as otel_logs
        from opentelemetry.exporter.cloud_logging import CloudLoggingExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        from monitoring.session_processor import GlobalSessionIdProcessor

        log_provider = LoggerProvider()
        log_provider.add_log_record_processor(GlobalSessionIdProcessor())
        log_provider.add_log_record_processor(BatchLogRecordProcessor(CloudLoggingExporter()))
        otel_logs.set_logger_provider(log_provider)
        _log.info("[Observability] GCP Cloud Logging exporter + GlobalSessionIdProcessor attached.")
    except Exception as e:  # pragma: no cover
        _log.warning(f"[Observability] GCP log bridge attach failed: {e}")


def _instrument_fastapi(app: FastAPI, provider: TracerProvider) -> None:
    # Wraps FastAPI with OTel auto-instrumentation so all HTTP spans are captured.
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
        _log.info("[Observability] FastAPIInstrumentor attached.")
    except Exception as e:  # pragma: no cover
        _log.warning(f"[Observability] FastAPIInstrumentor failed: {e}")


def init_observability(
    app: Optional[FastAPI] = None,
    *,
    extra_processors: Optional[list[SpanProcessor]] = None,
) -> Optional[TracerProvider]:
    """Idempotent. Returns the provider, or None when observability is disabled."""
    global _initialized, _tracer_provider
    if _initialized:
        return _tracer_provider

    settings = get_settings()
    if not settings.observability_enabled:
        _log.info("[Observability] Disabled via OBSERVABILITY_ENABLED=false.")
        _initialized = True
        return None

    provider = TracerProvider(
        resource=_build_resource(settings),
        sampler=ParentBased(TraceIdRatioBased(settings.observability_sample_ratio)),
    )
    trace.set_tracer_provider(provider)

    if settings.observability_export_to_gcp:
        _attach_gcp(provider)
    for sp in extra_processors or []:
        provider.add_span_processor(sp)

    if app is not None:
        _instrument_fastapi(app, provider)

    _tracer_provider = provider
    _initialized = True

    _log.info(
        "[Observability] Ready: gcp=%s sample=%.2f service=%s",
        settings.observability_export_to_gcp,
        settings.observability_sample_ratio,
        settings.service_name,
    )
    return provider


def get_status() -> dict:
    """Returned by /healthz."""
    settings = get_settings()
    return {
        "enabled": settings.observability_enabled and _initialized,
        "gcp_export": settings.observability_export_to_gcp,
        "sample_ratio": settings.observability_sample_ratio,
        "service": settings.service_name,
        "redact_pii": settings.observability_redact_pii,
    }


def record_exception_on_span(exc: BaseException, *, escaped: bool = True) -> None:
    # Records the exception on the active span and marks it ERROR; no-ops when no span is recording.
    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return
    span.record_exception(exc, escaped=escaped)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


@contextmanager
def with_session_attrs(*, session_id: Optional[str], user_id: Optional[str]) -> Iterator[None]:
    """Tags the active span with session.id / user.id so downstream ADK spans inherit them."""
    span = trace.get_current_span()
    if span and span.is_recording():
        if session_id:
            span.set_attribute("session.id", str(session_id))
        if user_id:
            span.set_attribute("user.id", str(user_id))
    yield


def _reset_for_tests() -> None:
    global _initialized, _tracer_provider
    _initialized = False
    _tracer_provider = None
    # Resets OTel global so each test can install its own provider (private internals access is intentional).
    import opentelemetry.trace as _otel_trace
    from opentelemetry.util._once import Once
    _otel_trace._TRACER_PROVIDER = None
    _otel_trace._TRACER_PROVIDER_SET_ONCE = Once()
