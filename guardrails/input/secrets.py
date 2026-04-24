# Input guardrail: blocks (not redacts) user input containing credentials (non-disableable)
from guardrails.base import GuardRail, GuardRailResult
from guardrails.constants import _SECRETS_BLOCK_MSG
from guardrails.regex_utils import detect_high_entropy_secrets, detect_secrets, describe_detected_secrets
from libs.logger import GuardRailEvent, log_guardrail_event


class SecretsInputGuardRail(GuardRail):
    """Blocks (not redacts) user input containing credentials. Presence of a secret is itself a signal."""

    # Detects credentials in user input via regex and entropy analysis; blocks rather than redacts
    async def process(self, text: str, session_id: str = "", conversation_history: str = "", session_state: dict = None) -> GuardRailResult:
        found = detect_secrets(text)
        entropy_detected = False
        if not found:
            found = detect_high_entropy_secrets(text)
            entropy_detected = bool(found)
        if found:
            method = "entropy analysis" if entropy_detected else "regex pattern match"
            reason = (
                f"Credential(s) detected in user input via {method} — "
                f"{len(found)} type(s): {describe_detected_secrets(found)}"
            )
            log_guardrail_event(GuardRailEvent(
                guardrail_name="SecretsInputGuardRail",
                layer="input", action="block",
                session_id=session_id, triggered=True,
                reason=reason,
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_SECRETS_BLOCK_MSG)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="SecretsInputGuardRail",
            layer="input", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
