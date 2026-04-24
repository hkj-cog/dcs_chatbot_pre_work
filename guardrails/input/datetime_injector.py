# Input guardrail: prepends current AEST datetime to every message for LLM temporal context
from datetime import datetime

from guardrails.base import GuardRail, GuardRailResult
from guardrails.utils import SYDNEY_TZ
from libs.logger import GuardRailEvent, log_guardrail_event


class DateTimeInjectorGuardRail(GuardRail):
    """Prepends current AEST/AEDT datetime so the LLM has correct temporal context."""

    # Prepends the current AEST/AEDT datetime to the input text before it reaches the LLM
    async def process(self, text: str, session_id: str = "", conversation_history: str = "", session_state: dict = None) -> GuardRailResult:
        now = datetime.now(SYDNEY_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
        modified = f"[Context: Today is {now}]\n{text}"
        log_guardrail_event(GuardRailEvent(
            guardrail_name="DateTimeInjectorGuardRail",
            layer="input", action="modify",
            session_id=session_id, triggered=True,
            reason="Datetime context injected (AEST/AEDT)",
        ))
        return GuardRailResult(is_blocked=False, modified_text=modified)
