# Post-process checker: LLM judge blocks off-topic responses and appends redirect note for partial answers
from guardrails.constants import _RELEVANCY_BLOCK_MSG
from guardrails.utils import invoke_chain, llm_chain
from libs.logger import GuardRailEvent, log_guardrail_event, logger

_RELEVANCY_PROMPT = """\
You are a relevancy-evaluation system for an NSW Government chatbot.

Conversation history (empty if this is the first message):
{history}

User question:
{question}

Chatbot response:
{response}

Evaluate the response on two dimensions:

1. Does this response directly and specifically address the user's question,
   taking into account the conversation context above?

2. Does the user's question contain MULTIPLE INDEPENDENT intents — i.e. questions
   about clearly separate topics (e.g. "renew my licence AND ask about first home
   buyer grant" = two independent topics)? Note: multiple aspects of the same topic
   (e.g. "what documents do I need AND how long does it take?" for the same application)
   is a SINGLE intent with multiple sub-questions, NOT multiple independent intents.

Answer with EXACTLY one word:
  RELEVANT        — response addresses the question asked (single or multi-aspect single intent),
                    with no significant off-topic content; OR asks a focused clarifying question
  PARTIAL_ANSWER  — response addresses at least one intent but the user asked about multiple
                    clearly independent topics and at least one was not addressed
  NOT_RELEVANT    — response ignores the question, provides only generic background unrelated
                    to what was asked, or addresses a substantially different topic"""

_MULTI_INTENT_NOTE = (
    "\n\nFor any remaining questions, please ask in a separate message, "
    "or contact Service NSW on 13 77 88 for assistance."
)


class RelevancyChecker:
    """LLM judge verifying the response addresses the question. PARTIAL_ANSWER appends a redirect note. Fail-closed."""

    def __init__(self, model_id: str, location: str) -> None:
        # Builds the LangChain chain for the relevancy LLM judge.
        self._chain = llm_chain(model_id, location, _RELEVANCY_PROMPT)

    # Runs the relevancy LLM judge; appends a multi-intent note on PARTIAL_ANSWER, blocks on NOT_RELEVANT
    async def check(
        self, question: str, answer: str, session_id: str, conversation_history: str = ""
    ) -> str:
        try:
            verdict = await invoke_chain(
                self._chain, question=question, response=answer, history=conversation_history
            )

            if verdict.startswith("NOT_RELEVANT"):
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="RelevancyChecker",
                    layer="post-process", action="block",
                    session_id=session_id, triggered=True,
                    reason="Response not relevant to user question",
                    snippet=answer[:80],
                ))
                return _RELEVANCY_BLOCK_MSG

            if verdict.startswith("PARTIAL_ANSWER"):
                # Append redirect note for missed intents — never name them (PII risk).
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="RelevancyChecker",
                    layer="post-process", action="modify",
                    session_id=session_id, triggered=True,
                    reason="Multi-intent query detected — appended redirect note for unaddressed intent(s)",
                    snippet=answer[:80],
                ))
                return answer + _MULTI_INTENT_NOTE

            if not verdict.startswith("RELEVANT"):
                logger.warning(
                    f"[RelevancyChecker] Unexpected verdict {verdict!r} — "
                    f"fail-closed (session={session_id})"
                )
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="RelevancyChecker",
                    layer="post-process", action="block",
                    session_id=session_id, triggered=True,
                    reason=f"Unexpected judge verdict {verdict!r} — fail-closed to maintain relevancy policy",
                ))
                return _RELEVANCY_BLOCK_MSG

        except Exception as exc:
            logger.error(f"[RelevancyChecker] LLM error (fail-closed): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="RelevancyChecker",
                layer="post-process", action="block",
                session_id=session_id, triggered=True,
                reason=f"LLM judge unavailable — returning fallback to maintain safety: {exc}",
            ))
            return _RELEVANCY_BLOCK_MSG

        log_guardrail_event(GuardRailEvent(
            guardrail_name="RelevancyChecker",
            layer="post-process", action="allow",
            session_id=session_id, triggered=False,
        ))
        return answer
