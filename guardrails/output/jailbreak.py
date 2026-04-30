# Output guardrail: same 13 jailbreak patterns applied to LLM output
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.constants import _JAILBREAK_OUTPUT_BLOCK_MSG
from guardrails.utils import JAILBREAK_REGEX_PATTERNS
from libs.logger import GuardRailEvent, log_guardrail_event


class JailbreakOutputGuardRail(OutputGuardRailBase):
    """Scans LLM output for embedded prompt-injection payloads using the same regex as input jailbreak."""

    # Scans LLM output for the same 13 prompt-injection regex patterns used on input
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        for pattern in JAILBREAK_REGEX_PATTERNS:
            if pattern.search(text):
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="JailbreakOutputGuardRail",
                    layer="output", action="block",
                    session_id=session_id, triggered=True,
                    reason=f"Prompt-injection pattern detected in LLM output: {pattern.pattern[:80]}",
                    # snippet omitted: runs before DlpOutputGuardRail so text is not yet DLP-redacted
                ))
                return GuardRailResult(is_blocked=True, blocked_reason=_JAILBREAK_OUTPUT_BLOCK_MSG)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="JailbreakOutputGuardRail",
            layer="output", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
