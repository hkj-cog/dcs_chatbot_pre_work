# Input guardrail: Cloud Language API content moderation on user input
import asyncio

from guardrails.base import GuardRail, GuardRailResult
from guardrails.constants import _IMPROPER_BLOCK_MSG, _JUDGE_UNAVAILABLE_BLOCK_MSG
from guardrails.utils import (
    HARMFUL_CATEGORIES,
    MODERATION_CATEGORIES_INPUT,
    TOXIC_CATEGORIES,
    check_moderation_categories,
)
from libs.logger import GuardRailEvent, log_guardrail_event, logger


class ImproperContentGuardRail(GuardRail):
    """Cloud Language API moderation on user input. Fail-closed. Emits separate events for toxic vs improper content."""

    # Calls the Cloud Language API to check user input for toxic and harmful content categories
    async def process(self, text: str, session_id: str = "", conversation_history: str = "", session_state: dict = None) -> GuardRailResult:
        try:
            triggered = await asyncio.to_thread(
                check_moderation_categories, text, MODERATION_CATEGORIES_INPUT
            )
            if triggered:
                toxic = [c for c in triggered if c in TOXIC_CATEGORIES]
                harmful = [c for c in triggered if c in HARMFUL_CATEGORIES]
                if toxic:
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="ToxicLanguageInputGuardRail",
                        layer="input", action="block",
                        session_id=session_id, triggered=True,
                        reason=f"Toxic language in input: {', '.join(toxic)}",
                        snippet=text[:80],
                    ))
                if harmful:
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="ImproperContentInputGuardRail",
                        layer="input", action="block",
                        session_id=session_id, triggered=True,
                        reason=f"Improper/harmful content in input: {', '.join(harmful)}",
                        snippet=text[:80],
                    ))
                return GuardRailResult(is_blocked=True, blocked_reason=_IMPROPER_BLOCK_MSG)

        except Exception as exc:
            logger.error(f"[ImproperContentGuardRail] API error (fail-closed): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="ImproperContentGuardRail",
                layer="input", action="block",
                session_id=session_id, triggered=True,
                reason=f"Content moderation API unavailable — blocking to maintain safety: {exc}",
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_JUDGE_UNAVAILABLE_BLOCK_MSG)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="ImproperContentGuardRail",
            layer="input", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
