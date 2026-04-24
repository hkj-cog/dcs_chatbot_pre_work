# Output guardrail: LLM judge appends time-sensitive/eligibility currency disclaimer
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.constants import _INFORMATION_CURRENCY_DISCLAIMER, _MISSING_DISCLAIMER_MSG
from guardrails.utils import invoke_chain, llm_chain
from libs.logger import GuardRailEvent, log_guardrail_event, logger

_INFORMATION_CURRENCY_PROMPT = """\
You are a content review system for an NSW Government citizen-facing chatbot.

The DCS "right information to the right citizen at the right time" principle requires
that citizens are warned when a response contains information that:
  (a) may become outdated — such as specific fees, fines, deadlines, expiry dates,
      regulatory thresholds, or requirements under legislation that can be amended; or
  (b) depends heavily on the citizen's individual circumstances — such as eligibility
      criteria for grants, concessions, licences, or support programs where the outcome
      varies by personal situation (income, residency, age, disability status, etc.)

Review the following chatbot response and determine whether it contains either type
of time-sensitive or person-specific information:

TYPE_A — Time-sensitive claims:
  Examples: specific dollar amounts ($150 fee, $1,000 fine), specific timeframes
  ("within 28 days", "applications close 30 June"), licence expiry periods, regulated
  rates or thresholds ("income must be below $65,000"), legislation section numbers.
  Do NOT flag: generic process descriptions, contact details, office locations,
  general explanations of how a service works.

TYPE_B — Citizen-circumstance-specific eligibility:
  Examples: eligibility criteria that depend on age, income, residency, disability
  status, employment, or other personal attributes. Concession card eligibility,
  grant criteria, support program qualifications.
  Do NOT flag: purely factual information that applies universally (e.g., "all NSW
  residents can renew their licence online").

If the response contains TYPE_A, TYPE_B, or both: respond with DISCLAIMER_NEEDED
If the response contains neither: respond with NOT_NEEDED

Chatbot response:
{response}

Answer with EXACTLY one of: DISCLAIMER_NEEDED or NOT_NEEDED"""


class InformationCurrencyGuardRail(OutputGuardRailBase):
    """
    Appends a currency/verification disclaimer to responses with time-sensitive fees or eligibility criteria.
    Skips if RequiredInclusionsGuardRail already appended its disclaimer.
    Fail-open on judge error — RequiredInclusions (fail-safe) covers critical legal/medical/financial domains.
    """

    def __init__(self, model_id: str, location: str) -> None:
        self._chain = llm_chain(model_id, location, _INFORMATION_CURRENCY_PROMPT)

    # Invokes the LLM currency judge and appends the disclaimer if time-sensitive information is detected
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        try:
            verdict = await invoke_chain(self._chain, response=text)
            if verdict.startswith("DISCLAIMER_NEEDED"):
                # Skip if RequiredInclusions already appended, or if idempotent.
                if _MISSING_DISCLAIMER_MSG in text or _INFORMATION_CURRENCY_DISCLAIMER in text:
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="InformationCurrencyGuardRail",
                        layer="output", action="allow",
                        session_id=session_id, triggered=False,
                        reason="Currency disclaimer already present — duplicate suppressed",
                    ))
                    return GuardRailResult(is_blocked=False)

                amended = f"{text}{_INFORMATION_CURRENCY_DISCLAIMER}"
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="InformationCurrencyGuardRail",
                    layer="output", action="modify",
                    session_id=session_id, triggered=True,
                    reason="Time-sensitive or citizen-specific information detected — currency disclaimer appended",
                    snippet=text[:80],
                ))
                return GuardRailResult(is_blocked=False, modified_text=amended)

        except Exception as exc:
            logger.error(f"[InformationCurrencyGuardRail] LLM error (fail-open): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="InformationCurrencyGuardRail",
                layer="output", action="allow",
                session_id=session_id, triggered=False,
                reason=f"Currency check unavailable — fail-open (RequiredInclusions covers critical domains): {exc}",
            ))

        log_guardrail_event(GuardRailEvent(
            guardrail_name="InformationCurrencyGuardRail",
            layer="output", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
