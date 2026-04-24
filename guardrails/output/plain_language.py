# Output guardrail: LLM rewrites unexplained acronyms and jargon for citizen readability
from typing import Optional

from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.utils import invoke_chain_raw, llm_chain
from libs.logger import GuardRailEvent, log_guardrail_event, logger

_PLAIN_LANGUAGE_PROMPT = """\
You are a plain-language accessibility reviewer for an NSW Government citizen-facing chatbot.

Your task is narrowly scoped: identify only two specific issues that the LLM's general
instructions may have missed, and fix them inline without changing anything else.

Issue type 1 — UNEXPLAINED ACRONYMS: government, legal, or technical abbreviations used
without being spelled out or explained in the same response.
Examples that need fixing: "NDIS", "BASIX", "SEPP", "EPA", "LGA", "BAS", "PAYG", "NCAT",
"AVO", "IVF" — only when there is no explanation nearby in the same response.
Do NOT flag acronyms the response already explains (e.g. "Biodiversity Assessment Method
(BAM)" is fine).

Issue type 2 — UNEXPLAINED TECHNICAL LEGAL TERMS: specific legal or bureaucratic terms that
an average Australian adult would not understand without explanation.
Examples that need fixing: "statutory declaration", "encumbrance", "gazetted regulation",
"promulgated", "ex parte", "nunc pro tunc", "in camera proceedings".
Do NOT flag terms that are commonly understood (e.g. "fine", "appeal", "penalty", "licence").

If NEITHER issue is present: respond with only the word PLAIN

If one or both issues are present: respond in this EXACT format (no other text before REWRITTEN:):
REWRITTEN:
[the response with ONLY the specific problem terms expanded or explained inline.
Do not rephrase sentences, restructure paragraphs, or change any other wording.
For acronyms: spell out on first use — e.g. "NDIS" → "NDIS (National Disability Insurance Scheme)".
For technical terms: add a brief parenthetical — e.g. "statutory declaration" → "statutory declaration (a formal written statement witnessed by an authorised person)".]

Chatbot response:
{response}"""


class CitizenReadabilityOutputGuardRail(OutputGuardRailBase):
    """Checks and rewrites unexplained jargon/acronyms in LLM output for plain-language compliance. Fail-open."""

    def __init__(self, model_id: str, location: str) -> None:
        self._chain = llm_chain(model_id, location, _PLAIN_LANGUAGE_PROMPT)

    # Calls the plain-language LLM judge and returns the rewritten text when jargon is detected
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        try:
            verdict = await invoke_chain_raw(self._chain, response=text)

            if verdict.upper().startswith("PLAIN"):
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="CitizenReadabilityOutputGuardRail",
                    layer="output", action="allow",
                    session_id=session_id, triggered=False,
                ))
                return GuardRailResult(is_blocked=False)

            if verdict.upper().startswith("REWRITTEN:"):
                rewritten = verdict[len("REWRITTEN:"):].strip()
                if rewritten:
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="CitizenReadabilityOutputGuardRail",
                        layer="output", action="modify",
                        session_id=session_id, triggered=True,
                        reason="Response contained jargon or complex language — rewritten in plain English",
                        # snippet omitted: runs before DlpOutputGuardRail (position 2 vs 6)
                    ))
                    return GuardRailResult(is_blocked=False, modified_text=rewritten)

            # Unexpected format — fail-open, log for investigation
            logger.warning(
                f"[CitizenReadabilityOutputGuardRail] Unexpected verdict format "
                f"(fail-open): {verdict[:120].upper()!r}"
            )
            log_guardrail_event(GuardRailEvent(
                guardrail_name="CitizenReadabilityOutputGuardRail",
                layer="output", action="allow",
                session_id=session_id, triggered=False,
                reason="Unexpected verdict format — fail-open, original text returned",
            ))
            return GuardRailResult(is_blocked=False)

        except Exception as exc:
            logger.error(f"[CitizenReadabilityOutputGuardRail] LLM error (fail-open): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="CitizenReadabilityOutputGuardRail",
                layer="output", action="allow",
                session_id=session_id, triggered=False,
                reason=f"Readability check failed — fail-open, original text returned: {exc}",
            ))
            return GuardRailResult(is_blocked=False)
