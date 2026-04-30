# Input guardrail: regex + LLM crisis/self-harm detection; returns support resources (fail-open)
import re

from guardrails.base import GuardRail, GuardRailResult
from guardrails.constants import _CRISIS_SUPPORT_MSG
from guardrails.utils import invoke_chain, llm_chain
from libs.logger import GuardRailEvent, log_guardrail_event, logger

# Unambiguous first-person crisis phrases — match = immediate response, no LLM call needed.
_CRISIS_KEYWORDS_RE = re.compile(
    r"\b(?:"
    r"suicid(?:al|e|ing)|"
    r"kill\s+my\s*self|"
    r"end\s+my\s+life|end\s+it\s+all|"
    r"take\s+my\s+(?:own\s+)?life|"
    r"(?:want\s+to|going\s+to|plan(?:ning)?\s+to)\s+die|"
    r"don'?t\s+want\s+to\s+(?:live|be\s+alive)|"
    r"self[\s\-]harm(?:ing)?|"
    r"hurt\s+my\s*self|"
    r"no\s+(?:reason|point)\s+(?:to\s+live|(?:in\s+)?going\s+on)"
    r")\b",
    re.I,
)

_CRISIS_DETECTION_PROMPT = """\
You are a safety system for an NSW Government citizen-facing chatbot.

Your task is to detect whether the user message indicates that the person may be
experiencing a personal crisis, including:
  - Suicidal ideation or intent (e.g. "I want to end it all", "I don't want to live anymore")
  - Self-harm (e.g. "I want to hurt myself", "I've been cutting")
  - Acute emotional distress with signs of safety risk (e.g. "I can't go on",
    "everything is hopeless and I have a plan")
  - Domestic or family violence situation requiring immediate safety support
  - Severe mental health episode

Do NOT flag:
  - General expressions of frustration or stress ("this is so stressful", "I'm upset")
  - Grief or sadness without safety risk indicators
  - Questions about mental health services or crisis support (e.g. "what mental health
    support does NSW provide?") — these are legitimate service enquiries
  - Descriptions of past events that are not indicating current risk

User message:
{query}

Always respond in English regardless of the language of the user message.
Answer with EXACTLY one word: CRISIS or SAFE"""


class CrisisDetectionInputGuardRail(GuardRail):
    """Two-layer crisis detection (regex then LLM judge); returns support resources instead of blocking. Fail-open."""

    def __init__(self, model_id: str, location: str) -> None:
        # Builds the LangChain chain for the LLM-based crisis detection judge.
        self._chain = llm_chain(model_id, location, _CRISIS_DETECTION_PROMPT)

    # Checks user input for crisis signals via regex then LLM; returns support resources instead of blocking
    async def process(self, text: str, session_id: str = "", conversation_history: str = "", session_state: dict = None) -> GuardRailResult:
        if _CRISIS_KEYWORDS_RE.search(text):  # fast regex path — no LLM call
            log_guardrail_event(GuardRailEvent(
                guardrail_name="CrisisDetectionInputGuardRail",
                layer="input", action="block",
                session_id=session_id, triggered=True,
                reason="High-confidence crisis keyword detected (regex) — returning support resources",
                snippet=text[:80],
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_CRISIS_SUPPORT_MSG)

        try:
            verdict = await invoke_chain(self._chain, query=text)
            if verdict.startswith("CRISIS"):
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="CrisisDetectionInputGuardRail",
                    layer="input", action="block",
                    session_id=session_id, triggered=True,
                    reason="Crisis signal detected (LLM judge) — returning support resources",
                    snippet=text[:80],
                ))
                return GuardRailResult(is_blocked=True, blocked_reason=_CRISIS_SUPPORT_MSG)

        except Exception as exc:
            logger.error(f"[CrisisDetectionInputGuardRail] LLM error (fail-open): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="CrisisDetectionInputGuardRail",
                layer="input", action="allow",
                session_id=session_id, triggered=False,
                reason=f"Crisis LLM judge unavailable — regex did not match, passing through: {exc}",
            ))
            return GuardRailResult(is_blocked=False)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="CrisisDetectionInputGuardRail",
            layer="input", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
