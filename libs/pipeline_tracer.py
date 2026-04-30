"""Emits one OTel span + pipeline_summary log per request. Only DLP-sanitized I/O flows into spans (PII contract)."""
from __future__ import annotations

import logging
from typing import Optional

from opentelemetry import trace

logger = logging.getLogger("dcs_chatbot")


class PipelineTracer:
    """Emits an OTel summary span and a structured log entry for each pipeline run."""

    SPAN_NAME = "chat.pipeline"

    def trace_pipeline(
        self,
        session_id: str,
        sanitized_input: str,
        final_content: str,
        score: Optional[str] = None,
        was_blocked: bool = False,
        guardrail_policy_version: str = "",
        reference_count: int = 0,
        context_chunks: Optional[list[str]] = None,
    ) -> None:
        """Records a summary OTel span + structured log entry with redacted I/O."""
        try:
            from monitoring.redaction import default_redactor
            red = default_redactor()
        except Exception:
            red = None

        safe_input = red.redact(sanitized_input) if red else sanitized_input
        safe_output = red.redact(final_content) if red else final_content
        context_text = " ".join(context_chunks or [])[:4000] if context_chunks else ""

        otel_tracer = trace.get_tracer("dcs_chatbot.pipeline")
        with otel_tracer.start_as_current_span(self.SPAN_NAME) as span:
            span.set_attribute("session.id", session_id or "")
            span.set_attribute("input.value", safe_input[:4000])
            span.set_attribute("output.value", safe_output[:4000])
            span.set_attribute("guardrail.was_blocked", bool(was_blocked))
            span.set_attribute("guardrail.policy_version", guardrail_policy_version or "")
            span.set_attribute("retrieval.reference_count", int(reference_count))
            if score is not None:
                span.set_attribute("eval.score", str(score))

            # Logged inside span so Cloud Trace ↔ Cloud Logging correlation headers are populated.
            logger.info(
                "pipeline_summary",
                extra={
                    "pipeline_summary": {
                        "session_id": session_id or "",
                        "input": safe_input[:4000],
                        "output": safe_output[:4000],
                        "context": context_text,
                        "score": score,
                        "was_blocked": bool(was_blocked),
                        "policy_version": guardrail_policy_version or "",
                        "reference_count": int(reference_count),
                    }
                },
            )
