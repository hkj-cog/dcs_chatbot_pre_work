"""
Arize Phoenix integration — currently a no-op stub.

To activate LLM pipeline tracing:
  1. Set PHOENIX_ENDPOINT in .env (e.g. http://localhost:6006/v1/traces).
  2. Replace init_phoenix() and PhoenixTracer.trace_pipeline() with the
     full OTel implementation (TracerProvider + OTLPSpanExporter + BatchSpanProcessor).
     The required packages are already pinned in requirements.txt.

PII contract (must hold in any implementation):
  Only sanitized_input (post-DLP) and final_content (post-guardrail) may flow
  into spans — raw user input must never be traced.
"""

import logging
from typing import Optional

logger = logging.getLogger("dcs_chatbot")


def init_phoenix(endpoint: str) -> None:
    """No-op stub. Logs a notice so operators know the stub is active when endpoint is set."""
    logger.info(
        f"[Phoenix] PHOENIX_ENDPOINT={endpoint!r} is set but the tracing stub is active — "
        "replace libs/phoenix_tracer.py with the OTel implementation to enable tracing."
    )


class PhoenixTracer:
    """No-op tracer stub. All calls are safe and produce no output."""

    def __init__(self, endpoint: Optional[str] = None) -> None:
        if endpoint:
            init_phoenix(endpoint)

    # No-op stub for the pipeline trace call; replace with OTel span logic when Phoenix is activated
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
        pass
