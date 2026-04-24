# Input guardrail: rejects messages exceeding MAX_INPUT_CHARS
from typing import Optional

from guardrails.base import GuardRail, GuardRailResult
from guardrails.constants import _INPUT_TOO_LONG_MSG
from libs.logger import GuardRailEvent, log_guardrail_event


class InputLengthGuardRail(GuardRail):
    """
    Rejects input exceeding the maximum character limit.
    Fast, no API calls — runs first in the chain.
    Spec: Technical · Security · Input
    """

    def __init__(self, max_chars: Optional[int] = None) -> None:
        if max_chars is not None:
            self._max_chars = max_chars
        else:
            from libs.config import get_settings
            self._max_chars = get_settings().max_input_chars

    # Blocks input that exceeds the configured character limit; no API calls
    async def process(self, text: str, session_id: str = "", conversation_history: str = "", session_state: dict = None) -> GuardRailResult:
        if len(text) > self._max_chars:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="InputLengthGuardRail",
                layer="input", action="block",
                session_id=session_id, triggered=True,
                reason=f"Input length {len(text)} chars exceeds maximum {self._max_chars}",
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_INPUT_TOO_LONG_MSG)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="InputLengthGuardRail",
            layer="input", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
