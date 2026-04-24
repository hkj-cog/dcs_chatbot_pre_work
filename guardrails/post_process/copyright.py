# Post-process checker: blocks verbatim reproduction of >50 words from source documents
from guardrails.constants import _COPYRIGHT_BLOCK_MSG
from guardrails.utils import invoke_chain, llm_chain
from libs.logger import GuardRailEvent, log_guardrail_event, logger

_COPYRIGHT_PROMPT = """\
You are an intellectual-property compliance checker for an NSW Government chatbot.

Retrieved context (source documents):
{context}

Chatbot response:
{response}

Does the chatbot response reproduce more than 50 consecutive words verbatim
from the retrieved context above, without paraphrasing?

Note: Brief direct quotes (under 50 words) for factual accuracy are acceptable.
Paraphrased summaries are always acceptable regardless of length.

Answer with EXACTLY one word: COMPLIANT or VERBATIM_REPRODUCTION"""


class CopyrightComplianceChecker:
    """Blocks verbatim reproduction of >50 words from source docs. Fail-open."""

    def __init__(self, model_id: str, location: str) -> None:
        self._chain = llm_chain(model_id, location, _COPYRIGHT_PROMPT)

    # Invokes the LLM copyright judge; returns the block message if verbatim reproduction is detected
    async def check(self, answer: str, context_chunks: list, session_id: str) -> str:
        if not context_chunks:
            return answer

        context = "\n\n".join(f"[{i+1}] {chunk}" for i, chunk in enumerate(context_chunks))

        try:
            verdict = await invoke_chain(self._chain, context=context, response=answer)
            if verdict.startswith("VERBATIM_REPRODUCTION"):
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="CopyrightComplianceChecker",
                    layer="post-process", action="block",
                    session_id=session_id, triggered=True,
                    reason="Response contains verbatim reproduction of source content (>50 words)",
                    snippet=answer[:80],
                ))
                return _COPYRIGHT_BLOCK_MSG
        except Exception as exc:
            logger.error(f"[CopyrightComplianceChecker] LLM error (fail-open): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="CopyrightComplianceChecker",
                layer="post-process", action="allow",
                session_id=session_id, triggered=True,
                reason=f"Copyright check failed — fail-open: {exc}",
            ))
            return answer

        log_guardrail_event(GuardRailEvent(
            guardrail_name="CopyrightComplianceChecker",
            layer="post-process", action="allow",
            session_id=session_id, triggered=False,
        ))
        return answer
