"""
Arize Phoenix Cloud integration — OTLP HTTP exporter with API-key auth.

Activation:
  1. Set PHOENIX_ENDPOINT (default: https://app.phoenix.arize.com).
  2. Set PHOENIX_API_KEY to your Phoenix Cloud API key.
  3. Set OBSERVABILITY_ENABLED=true (default).

Self-hosted Phoenix still works: leave PHOENIX_API_KEY empty and point
PHOENIX_ENDPOINT at your collector (e.g. http://localhost:6006).

PII contract:
  Only sanitized_input (post-DLP) and final_content (post-guardrail) may flow
  into spans. trace_pipeline() applies the redactor again as defence in depth.
"""
from __future__ import annotations

import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("dcs_chatbot")


def init_phoenix(
    endpoint: str,
    *,
    api_key: str = "",
    tracer_provider=None,
) -> bool:
    """
    Attaches a Phoenix OTLP HTTP span processor to the given (or global) TracerProvider.

    Returns True if the exporter was attached, False otherwise (logged at WARNING).
    """
    if not endpoint:
        logger.info("[Phoenix] PHOENIX_ENDPOINT not set — Phoenix exporter disabled.")
        return False
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except Exception as e:  # pragma: no cover
        logger.warning(f"[Phoenix] OTLP HTTP exporter not available: {e}")
        return False

    provider = tracer_provider or trace.get_tracer_provider()
    if not hasattr(provider, "add_span_processor"):
        logger.warning(
            "[Phoenix] Active TracerProvider does not support add_span_processor "
            "(is observability initialised?). Phoenix exporter NOT attached."
        )
        return False

    url = endpoint.rstrip("/") + "/v1/traces"

    # Phoenix Cloud expects the API key in the `api_key` header. Self-hosted
    # Phoenix needs no header. We also set Authorization: Bearer for forward-compat.
    headers: Optional[dict] = None
    if api_key:
        headers = {
            "api_key": api_key,
            "authorization": f"Bearer {api_key}",
        }

    try:
        exporter = OTLPSpanExporter(endpoint=url, headers=headers)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        auth_mode = "Phoenix Cloud (api_key)" if api_key else "self-hosted (no auth)"
        logger.info(f"[Phoenix] OTLP exporter attached → {url} [{auth_mode}]")
        return True
    except Exception as e:  # pragma: no cover
        logger.warning(f"[Phoenix] Failed to attach OTLP exporter: {e}")
        return False


class PhoenixTracer:
    """
    Convenience wrapper for emitting a single span that summarises the full pipeline run.

    The chat pipeline already produces detailed spans automatically (via the
    GoogleADKInstrumentor). This class is for the optional aggregate "AGENT" span
    that captures sanitized input/output and post-process metadata — exactly the
    shape the Phoenix evaluators expect.
    """

    SPAN_NAME = "chat.pipeline"

    def __init__(self, endpoint: Optional[str] = None) -> None:
        # No-op constructor — exporter wiring is done by libs.observability.init_observability().
        # `endpoint` kept for backward compatibility with previous callers.
        self._endpoint = endpoint

    def trace_pipeline(
        self,
        session_id: str,
        sanitized_input: str,
        final_content: str,
        score: Optional[str] = None,
        was_blocked: bool = False,
        guardrail_policy_version: str = "",
        reference_count: int = 0,
    ) -> None:
        """Records a single summary span with redacted I/O."""
        try:
            from monitoring.redaction import default_redactor
        except Exception:
            default_redactor = None  # type: ignore[assignment]

        red = default_redactor() if default_redactor else None
        safe_input = red.redact(sanitized_input) if red else sanitized_input
        safe_output = red.redact(final_content) if red else final_content

        tracer = trace.get_tracer("dcs_chatbot.phoenix")
        with tracer.start_as_current_span(self.SPAN_NAME) as span:
            span.set_attribute("session.id", session_id or "")
            span.set_attribute("input.value", safe_input[:4000])
            span.set_attribute("output.value", safe_output[:4000])
            span.set_attribute("guardrail.was_blocked", bool(was_blocked))
            span.set_attribute("guardrail.policy_version", guardrail_policy_version or "")
            span.set_attribute("retrieval.reference_count", int(reference_count))
            if score is not None:
                span.set_attribute("eval.score", str(score))
            # OpenInference span kind — surfaces in Phoenix as an "AGENT" span.
            span.set_attribute("openinference.span.kind", "AGENT")