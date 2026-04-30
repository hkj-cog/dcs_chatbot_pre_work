# Post-process checker: blocks ungrounded responses with no Vertex AI Search citation support (non-disableable)
from guardrails.constants import _GROUNDEDNESS_BLOCK_MSG
from guardrails.utils import invoke_chain, llm_chain
from libs.logger import GuardRailEvent, log_guardrail_event, logger

_GROUNDEDNESS_PROMPT = """\
You are a groundedness-evaluation system for an NSW Government chatbot.

Your role is to protect citizens from hallucinated government information. Incorrect
information about government services can cause real harm — citizens may miss deadlines,
pay wrong amounts, or be denied services based on misinformation.

Retrieved context (authoritative source documents):
{context}

Chatbot response:
{response}

Important: The response may contain [REDACTED] or [REDACTED_<TYPE>] tokens where personally
identifiable information (phone numbers, email addresses, names, etc.) has been automatically
removed for privacy compliance. Treat any [REDACTED] token as grounded provided the retrieved
context contained a value of that type at the corresponding location — the redaction confirms
the value existed in the source, not what the specific value was.

Is every factual claim in the chatbot response directly supported by the
retrieved context above? Responses should not introduce facts or figures
not present in the context.

Every factual claim must be grounded — this applies uniformly, not only to specific
types. Factual claims include (but are not limited to):
  - Specific dollar amounts: fees, fines, penalties, rebates (e.g. "$150", "$1,500 per unit")
  - Specific legislative references: Act names, section/clause numbers (e.g. "Section 14 of
    the Road Transport Act 1999")
  - Specific timeframes or deadlines: processing times, appeal windows, expiry periods
    (e.g. "within 28 days", "must renew by 1 March")
  - Specific eligibility thresholds: income limits, age requirements, residency periods
  - Contact details: phone numbers, website URLs, office addresses
  - Any other specific facts, names, procedures, or requirements stated in the response

Standard service-communication language is always permitted and must NOT be counted
against groundedness, regardless of whether it appears in the retrieved context:
  - Recommendations to seek legal, medical, or financial professional advice
  - Directions to contact Service NSW or a relevant government agency
  - General disclaimers about information currency, individual circumstances, or
    recommendations to verify current fees and requirements at service.nsw.gov.au

Answer with EXACTLY one of these three words:
  GROUNDED           — every factual claim is fully supported by the retrieved context
  PARTIALLY_GROUNDED — most claims are supported but at least one specific fact cannot
                       be verified from the context (e.g. a dollar amount, date, or
                       contact detail that does not appear in the retrieved chunks)
  NOT_GROUNDED       — the response makes significant unsupported claims or contradicts
                       the retrieved context"""


class GroundednessChecker:
    """LLM judge enforcing 'no citation → no response'. PARTIALLY_GROUNDED treated as NOT_GROUNDED. Fail-closed."""

    def __init__(self, model_id: str, location: str) -> None:
        # Builds the LangChain chain for the groundedness LLM judge.
        self._chain = llm_chain(model_id, location, _GROUNDEDNESS_PROMPT)

    # Runs the groundedness LLM judge; blocks on NOT_GROUNDED, PARTIALLY_GROUNDED, or unexpected verdicts
    async def check(self, answer: str, context_chunks: list, session_id: str) -> str:
        if not context_chunks:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="GroundednessChecker",
                layer="post-process", action="block",
                session_id=session_id, triggered=True,
                reason="No grounding chunks available — response blocked per no-citation policy",
            ))
            return _GROUNDEDNESS_BLOCK_MSG

        context = "\n\n".join(f"[{i+1}] {chunk}" for i, chunk in enumerate(context_chunks))

        try:
            verdict = await invoke_chain(self._chain, context=context, response=answer)

            if verdict.startswith("NOT_GROUNDED"):
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="GroundednessChecker",
                    layer="post-process", action="block",
                    session_id=session_id, triggered=True,
                    reason="Response contains ungrounded claims",
                    snippet=answer[:80],
                ))
                return _GROUNDEDNESS_BLOCK_MSG

            if verdict.startswith("PARTIALLY_GROUNDED"):
                # Logged separately from NOT_GROUNDED so the partial-failure rate is trackable.
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="GroundednessChecker",
                    layer="post-process", action="block",
                    session_id=session_id, triggered=True,
                    reason="Response is partially grounded — at least one claim unverified "
                           "(treated as NOT_GROUNDED per government safety policy)",
                    snippet=answer[:80],
                ))
                return _GROUNDEDNESS_BLOCK_MSG

            if not verdict.startswith("GROUNDED"):
                logger.warning(
                    f"[GroundednessChecker] Unexpected verdict {verdict!r} — "
                    f"fail-closed (session={session_id})"
                )
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="GroundednessChecker",
                    layer="post-process", action="block",
                    session_id=session_id, triggered=True,
                    reason=f"Unexpected judge verdict {verdict!r} — fail-closed to enforce groundedness policy",
                ))
                return _GROUNDEDNESS_BLOCK_MSG

        except Exception as exc:
            logger.error(f"[GroundednessChecker] LLM error (fail-closed): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="GroundednessChecker",
                layer="post-process", action="block",
                session_id=session_id, triggered=True,
                reason=f"LLM judge unavailable — blocking to enforce groundedness policy: {exc}",
            ))
            return _GROUNDEDNESS_BLOCK_MSG

        log_guardrail_event(GuardRailEvent(
            guardrail_name="GroundednessChecker",
            layer="post-process", action="allow",
            session_id=session_id, triggered=False,
        ))
        return answer
