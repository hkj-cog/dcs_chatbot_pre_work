# Output guardrail: Cloud Language API at stricter thresholds than input
import asyncio
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.constants import _JUDGE_UNAVAILABLE_BLOCK_MSG, _OUTPUT_BLOCK_MSG
from guardrails.utils import (
    HARMFUL_CATEGORIES,
    MODERATION_CATEGORIES_OUTPUT,
    TOXIC_CATEGORIES,
    check_moderation_categories,
)
from libs.logger import GuardRailEvent, log_guardrail_event, logger


class ContentModerationOutputGuardRail(OutputGuardRailBase):
    """Cloud Language API moderation on LLM output. Fail-closed. Covers toxic and improper content."""

    # Checks LLM output against stricter moderation thresholds; emits separate events for toxic vs harmful
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        try:
            triggered = await asyncio.to_thread(
                check_moderation_categories, text, MODERATION_CATEGORIES_OUTPUT
            )
            if triggered:
                toxic = [c for c in triggered if c in TOXIC_CATEGORIES]
                harmful = [c for c in triggered if c in HARMFUL_CATEGORIES]
                if toxic:
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="ToxicLanguageOutputGuardRail",
                        layer="output", action="block",
                        session_id=session_id, triggered=True,
                        reason=f"Toxic language in output: {', '.join(toxic)}",
                        snippet=text[:80],
                    ))
                if harmful:
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="ImproperContentOutputGuardRail",
                        layer="output", action="block",
                        session_id=session_id, triggered=True,
                        reason=f"Improper/harmful content in output: {', '.join(harmful)}",
                        snippet=text[:80],
                    ))
                return GuardRailResult(is_blocked=True, blocked_reason=_OUTPUT_BLOCK_MSG)

        except Exception as exc:
            logger.error(f"[ContentModerationOutputGuardRail] API error (fail-closed): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="ContentModerationOutputGuardRail",
                layer="output", action="block",
                session_id=session_id, triggered=True,
                reason=f"Content moderation API unavailable — blocking to maintain safety: {exc}",
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_JUDGE_UNAVAILABLE_BLOCK_MSG)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="ContentModerationOutputGuardRail",
            layer="output", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
