# Output guardrail: appends legal/medical/financial disclaimer; fail-safe appends even on LLM error
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.constants import _MISSING_DISCLAIMER_MSG
from guardrails.utils import invoke_chain, llm_chain
from libs.logger import GuardRailEvent, log_guardrail_event, logger

_REQUIRED_INCLUSIONS_PROMPT = """\
You are a validation system for an NSW Government citizen-facing chatbot.

Step 1 — Classify the topic:
Does the following chatbot response touch any of these sensitive domains?
  • Legal matters (rights, obligations, contracts, disputes, court processes, penalties)
  • Medical or health matters (symptoms, diagnoses, treatments, medications, procedures)
  • Financial matters (tax, benefits, grants, fines, payments, superannuation)

Step 2 — Check for a disclaimer:
If the response DOES touch a sensitive domain, does it include at least one of:
  • A recommendation to seek professional advice (legal, medical, or financial)
  • A direction to contact Service NSW or the relevant government agency
  • An acknowledgement that the information is general and may not apply to individual circumstances

If the response touches a sensitive domain AND is missing any such disclaimer:
  Answer: MISSING_DISCLAIMER

If the response does NOT touch a sensitive domain, OR it touches one and already
includes an appropriate disclaimer:
  Answer: COMPLIANT

Chatbot response:
{response}

Answer with EXACTLY one word: COMPLIANT or MISSING_DISCLAIMER"""


class RequiredInclusionsGuardRail(OutputGuardRailBase):
    """Appends the mandatory disclaimer on legal/medical/financial topics. Fail-safe: appends on judge error."""

    def __init__(self, model_id: str, location: str) -> None:
        # Builds the LangChain chain for the required disclaimer LLM judge.
        self._chain = llm_chain(model_id, location, _REQUIRED_INCLUSIONS_PROMPT)

    # Invokes the disclaimer judge and appends (or unconditionally appends on error) the advisory text
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        try:
            verdict = await invoke_chain(self._chain, response=text)
            if verdict.startswith("MISSING_DISCLAIMER"):
                amended = f"{text}\n\n{_MISSING_DISCLAIMER_MSG}"
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="RequiredInclusionsGuardRail",
                    layer="output", action="modify",
                    session_id=session_id, triggered=True,
                    reason="Required disclaimer appended to sensitive-domain response",
                    snippet=text[:80],
                ))
                return GuardRailResult(is_blocked=False, modified_text=amended)
        except Exception as exc:
            logger.error(f"[RequiredInclusionsGuardRail] LLM error: {exc}")
            amended = f"{text}\n\n{_MISSING_DISCLAIMER_MSG}"
            log_guardrail_event(GuardRailEvent(
                guardrail_name="RequiredInclusionsGuardRail",
                layer="output", action="modify",
                session_id=session_id, triggered=True,
                reason=f"Disclaimer check failed — appended unconditionally to maintain compliance: {exc}",
            ))
            return GuardRailResult(is_blocked=False, modified_text=amended)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="RequiredInclusionsGuardRail",
            layer="output", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
