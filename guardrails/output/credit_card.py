# Output guardrail: regex redaction of 16-digit credit card numbers
import re
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from libs.logger import GuardRailEvent, log_guardrail_event

_CARD_NUMBER_RE = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b")


class CreditCardRedactionGuardRail(OutputGuardRailBase):
    """Fast regex redaction of 16-digit card numbers from LLM output."""

    # Scans LLM output for 16-digit card number patterns and replaces them with a redaction token
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        redacted = _CARD_NUMBER_RE.sub("[REDACTED_CARD_NUMBER]", text)
        if redacted != text:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="CreditCardRedactionGuardRail",
                layer="output", action="modify",
                session_id=session_id, triggered=True,
                reason="Credit card number redacted from output",
            ))
            return GuardRailResult(is_blocked=False, modified_text=redacted)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="CreditCardRedactionGuardRail",
            layer="output", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
