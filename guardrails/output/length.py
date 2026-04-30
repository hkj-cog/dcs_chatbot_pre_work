# Output guardrail: rejects responses exceeding MAX_OUTPUT_CHARS
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.constants import _OUTPUT_TOO_LONG_MSG
from libs.logger import GuardRailEvent, log_guardrail_event


class OutputLengthGuardRail(OutputGuardRailBase):
    """Blocks LLM output exceeding the character limit. Fast, no API calls — runs first in the output chain."""

    def __init__(self, max_chars: Optional[int] = None) -> None:
        # Sets max_chars from arg or falls back to the configured setting.
        if max_chars is not None:
            self._max_chars = max_chars
        else:
            from libs.config import get_settings
            self._max_chars = get_settings().max_output_chars

    # Blocks LLM output that exceeds the configured character limit; no API calls
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        if len(text) > self._max_chars:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="OutputLengthGuardRail",
                layer="output", action="block",
                session_id=session_id, triggered=True,
                reason=f"Output length {len(text)} chars exceeds maximum {self._max_chars}",
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_OUTPUT_TOO_LONG_MSG)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="OutputLengthGuardRail",
            layer="output", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
