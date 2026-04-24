# Output guardrail: Cloud DLP redaction on LLM output (non-disableable)
import asyncio
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.constants import _OUTPUT_BLOCK_MSG
from libs.dlp import GoogleDlp
from libs.logger import GuardRailEvent, log_guardrail_event, logger


class DlpOutputGuardRail(OutputGuardRailBase):
    """Runs Cloud DLP on the LLM response to redact PII. Fail-closed."""

    def __init__(self, dlp: GoogleDlp) -> None:
        self._dlp = dlp

    # Runs Cloud DLP on LLM output to redact PII; blocks the response if DLP is unavailable
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        try:
            redacted = await asyncio.to_thread(self._dlp.invoke, text)
            if redacted != text:
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="DlpOutputGuardRail",
                    layer="output", action="modify",
                    session_id=session_id, triggered=True,
                    reason="PII redacted from LLM output via Cloud DLP",
                ))
                return GuardRailResult(is_blocked=False, modified_text=redacted)

            log_guardrail_event(GuardRailEvent(
                guardrail_name="DlpOutputGuardRail",
                layer="output", action="allow",
                session_id=session_id, triggered=False,
            ))
            return GuardRailResult(is_blocked=False)

        except Exception as exc:
            logger.error(f"[DlpOutputGuardRail] DLP API error — blocking output to protect PII: {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="DlpOutputGuardRail",
                layer="output", action="block",
                session_id=session_id, triggered=True,
                reason=f"DLP API unavailable — output blocked to protect PII: {exc}",
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_OUTPUT_BLOCK_MSG)
