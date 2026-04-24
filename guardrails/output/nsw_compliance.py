# Output guardrail: LLM judge for AI transparency and NSW government scope (AI Assurance Framework)
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.constants import _JUDGE_UNAVAILABLE_BLOCK_MSG, _NSW_COMPLIANCE_BLOCK_MSG
from guardrails.utils import invoke_chain, llm_chain
from libs.logger import GuardRailEvent, log_guardrail_event, logger

_NSW_AI_COMPLIANCE_PROMPT = """\
You are a compliance checker for an NSW Government AI chatbot.

Review the following chatbot response against NSW AI Assurance Framework principles:

1. TRANSPARENCY: The response must NOT claim to be from a human, must NOT make
   unqualified guarantees about accuracy (e.g. "I guarantee this is 100% correct",
   "this is definitely the law"), and must NOT impersonate a government official.

2. SCOPE: The response must stay within information provision. It must NOT make
   binding commitments on behalf of the NSW Government, issue official determinations,
   or promise outcomes (e.g. "Your application WILL be approved").

Chatbot response:
{response}

Is this response compliant with NSW AI Assurance Framework principles?
Answer with EXACTLY one word: COMPLIANT or NON_COMPLIANT"""


class NSWAIComplianceGuardRail(OutputGuardRailBase):
    """LLM judge checking AI transparency and scope per NSW AI Assurance Framework. Fail-closed."""

    def __init__(self, model_id: str, location: str) -> None:
        self._chain = llm_chain(model_id, location, _NSW_AI_COMPLIANCE_PROMPT)

    # Invokes the NSW AI Assurance Framework LLM judge to check transparency and scope compliance
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        try:
            verdict = await invoke_chain(self._chain, response=text)
            if verdict.startswith("NON_COMPLIANT"):
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="NSWAIComplianceGuardRail",
                    layer="output", action="block",
                    session_id=session_id, triggered=True,
                    reason="Response violates NSW AI Assurance Framework principles",
                    snippet=text[:80],
                ))
                return GuardRailResult(is_blocked=True, blocked_reason=_NSW_COMPLIANCE_BLOCK_MSG)
        except Exception as exc:
            logger.error(f"[NSWAIComplianceGuardRail] LLM error (fail-closed): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="NSWAIComplianceGuardRail",
                layer="output", action="block",
                session_id=session_id, triggered=True,
                reason=f"LLM judge unavailable — blocking to maintain compliance: {exc}",
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_JUDGE_UNAVAILABLE_BLOCK_MSG)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="NSWAIComplianceGuardRail",
            layer="output", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
