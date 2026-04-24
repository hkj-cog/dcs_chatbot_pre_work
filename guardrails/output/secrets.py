# Output guardrail: blocks LLM responses containing credentials (non-disableable)
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.constants import _OUTPUT_SECRETS_BLOCK_MSG
from guardrails.regex_utils import detect_high_entropy_secrets, detect_secrets, describe_detected_secrets
from libs.logger import GuardRailEvent, log_guardrail_event


class SecretsOutputGuardRail(OutputGuardRailBase):
    """Blocks (not redacts) LLM output containing credentials. Block triggers SessionThreatTracker escalation."""

    # Detects credentials in LLM output via regex and entropy; blocks and triggers SIEM escalation
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        found = detect_secrets(text)
        entropy_detected = False
        if not found:
            found = detect_high_entropy_secrets(text)
            entropy_detected = bool(found)
        if found:
            method = "entropy analysis" if entropy_detected else "regex pattern match"
            reason = (
                f"Credential(s) detected in LLM output via {method} — "
                f"{len(found)} type(s): {describe_detected_secrets(found)}"
            )
            log_guardrail_event(GuardRailEvent(
                guardrail_name="SecretsOutputGuardRail",
                layer="output", action="block",
                session_id=session_id, triggered=True,
                reason=reason,
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_OUTPUT_SECRETS_BLOCK_MSG)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="SecretsOutputGuardRail",
            layer="output", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
