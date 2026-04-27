"""
Single source of truth for observability bootstrap.

* Builds a TracerProvider with proper Resource attributes.
* Configures Phoenix Cloud (or self-hosted) and optional GCP Cloud Trace exporters.
* Applies parent-based ratio sampling.
* Instruments FastAPI and Google ADK exactly once.
* Idempotent. Fail-soft: any exporter/instrumentor error is logged and the app
  keeps running without that exporter.
"""
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
    return Resource.create(
        {
            "service.name": settings.service_name,
            "service.namespace": "dcs",
            "service.version": os.getenv("SERVICE_VERSION", "dev"),
            "deployment.environment": os.getenv("DEPLOY_ENV", "local"),
            "phoenix.project.name": settings.phoenix_project_name,
        }
    )


def _attach_phoenix(provider: TracerProvider, settings) -> None:
    if not settings.phoenix_endpoint:
        _log.info("[Observability] PHOENIX_ENDPOINT empty — Phoenix exporter skipped.")
        return
    try:
        from libs.phoenix_tracer import init_phoenix
        init_phoenix(
            settings.phoenix_endpoint,
            api_key=settings.phoenix_api_key,
            tracer_provider=provider,
        )
    except Exception as e:  # pragma: no cover
        _log.warning(f"[Observability] Phoenix attach failed: {e}")


def _attach_gcp(provider: TracerProvider) -> None:
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


def _instrument_adk(provider: TracerProvider) -> None:
    try:
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor
        GoogleADKInstrumentor().instrument(tracer_provider=provider)
        _log.info("[Observability] GoogleADKInstrumentor attached.")
    except Exception as e:  # pragma: no cover
        _log.warning(f"[Observability] GoogleADKInstrumentor failed: {e}")


def _instrument_fastapi(app: FastAPI, provider: TracerProvider) -> None:
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

    _attach_phoenix(provider, settings)
    if settings.observability_export_to_gcp:
        _attach_gcp(provider)
    for sp in extra_processors or []:
        provider.add_span_processor(sp)

    _instrument_adk(provider)
    if app is not None:
        _instrument_fastapi(app, provider)

    _tracer_provider = provider
    _initialized = True

    mode = "cloud" if settings.phoenix_api_key else ("self-hosted" if settings.phoenix_endpoint else "off")
    _log.info(
        "[Observability] Ready: phoenix_mode=%s endpoint=%s gcp=%s sample=%.2f service=%s project=%s",
        mode,
        settings.phoenix_endpoint or "<none>",
        settings.observability_export_to_gcp,
        settings.observability_sample_ratio,
        settings.service_name,
        settings.phoenix_project_name,
    )
    return provider


def get_status() -> dict:
    """Returned by /healthz. Never includes the API key value."""
    settings = get_settings()
    if settings.phoenix_api_key:
        mode = "cloud"
    elif settings.phoenix_endpoint:
        mode = "self-hosted"
    else:
        mode = "off"
    return {
        "enabled": settings.observability_enabled and _initialized,
        "phoenix_mode": mode,
        "phoenix_endpoint": settings.phoenix_endpoint or None,
        "phoenix_project": settings.phoenix_project_name,
        "phoenix_api_key_set": bool(settings.phoenix_api_key),
        "gcp_export": settings.observability_export_to_gcp,
        "sample_ratio": settings.observability_sample_ratio,
        "service": settings.service_name,
        "redact_pii": settings.observability_redact_pii,
    }


def record_exception_on_span(exc: BaseException, *, escaped: bool = True) -> None:
    span = trace.get_current_span()
    if span is None or not span.is_recording():
        return
    span.record_exception(exc, escaped=escaped)
    span.set_status(Status(StatusCode.ERROR, str(exc)))


@contextmanager
def with_session_attrs(*, session_id: Optional[str], user_id: Optional[str]) -> Iterator[None]:
    """
    Tags the active span with session.id / user.id and propagates them via
    OpenInference's `using_attributes` so downstream ADK spans inherit them.
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        if session_id:
            span.set_attribute("session.id", str(session_id))
        if user_id:
            span.set_attribute("user.id", str(user_id))

    try:
        from openinference.instrumentation import using_attributes
    except Exception:
        yield
        return
    with using_attributes(session_id=str(session_id) if session_id else "", user_id=user_id or ""):
        yield


def _reset_for_tests() -> None:  # pragma: no cover
    global _initialized, _tracer_provider
    _initialized = False
    _tracer_provider = None
    # Reset the OTel global provider so tests can each install their own TracerProvider.
    # Accessing private OTel internals is intentional here — test-only helper.
    import opentelemetry.trace as _otel_trace
    from opentelemetry.util._once import Once
    _otel_trace._TRACER_PROVIDER = None
    _otel_trace._TRACER_PROVIDER_SET_ONCE = Once()