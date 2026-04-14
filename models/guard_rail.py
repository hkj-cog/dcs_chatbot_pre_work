import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.cloud import language_v1
from google.genai import types
from guardrails import Guard
from guardrails.errors import ValidationError
from guardrails.hub import DetectJailbreak

from libs.logger import logger

@dataclass
class GuardRailResult:
    """Result returned by every GuardRail.process() call."""
    is_blocked: bool
    blocked_reason: str = ""
    modified_text: str = ""


class GuardRail(ABC):
    @abstractmethod
    async def process(self, text: str) -> GuardRailResult:
        
class DateTimeInjectorGuardRail(GuardRail):

    async def process(self, text: str) -> GuardRailResult:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        modified = f"[Context: Today is {now}]\n{text}"
        logger.info("[DateTimeInjectorGuardRail] Injected datetime context.")
        return GuardRailResult(is_blocked=False, modified_text=modified)

_jailbreak_guard = Guard().use(DetectJailbreak)

_JAILBREAK_BLOCK_MSG = (
    "I'm designed to follow my instructions carefully. "
    "Please rephrase your query if you intended something specific."
)


class JailbreakGuardRail(GuardRail):

    async def process(self, text: str) -> GuardRailResult:
        try:
            outcome = _jailbreak_guard.validate(text)
            if not outcome.validation_passed:
                logger.warning("[JailbreakGuardRail] Jailbreak detected — blocking.")
                return GuardRailResult(
                    is_blocked=True,
                    blocked_reason=_JAILBREAK_BLOCK_MSG,
                )
        except ValidationError as exc:
            logger.warning(f"[JailbreakGuardRail] ValidationError: {exc} — blocking.")
            return GuardRailResult(
                is_blocked=True,
                blocked_reason=_JAILBREAK_BLOCK_MSG,
            )
        return GuardRailResult(is_blocked=False)


class ProfanityGuardRail(GuardRail):

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold

    async def process(self, text: str) -> GuardRailResult:
        try:
            checker = ProfanityChecker(text, threshold=self.threshold)
            if checker.contains_profanity:
                logger.warning("[ProfanityGuardRail] Profanity detected — blocking.")
                return GuardRailResult(
                    is_blocked=True,
                    blocked_reason="Your message contains inappropriate language. Please rephrase.",
                )
        except Exception as exc:
            # Fail-open: log but do not block on infrastructure errors
            logger.error(f"[ProfanityGuardRail] Error during check (fail-open): {exc}")
        return GuardRailResult(is_blocked=False)


class ProfanityChecker:

    def __init__(self, text: str, language: str = "en", threshold: float = 0.5) -> None:
        self.text = text
        self.language = language
        self.threshold = threshold
        self.profanity_confidence: Optional[float] = None
        self.contains_profanity: bool = False
        self.moderation_categories: list = []

        try:
            client = language_v1.LanguageServiceClient()
            document = language_v1.Document(
                content=text,
                type_=language_v1.Document.Type.PLAIN_TEXT,
                language=self.language,
            )
            response = client.moderate_text(document=document)
            for category in response.moderation_categories:
                if category.name == "Profanity":
                    self.profanity_confidence = category.confidence
                    self.contains_profanity = category.confidence > self.threshold
                self.moderation_categories.append(
                    {"name": category.name, "confidence": category.confidence}
                )
        except Exception as exc:
            logger.info(f"[ProfanityChecker] API error (fail-open): {exc}")
            self.profanity_confidence = None
            self.contains_profanity = False
            self.moderation_categories = []

_CARD_NUMBER_RE = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b")


class OutputGuardRail:

    async def __call__(
        self,
        callback_context,
        llm_response: LlmResponse,
    ) -> LlmResponse:
        response_text = self._extract_text(llm_response)
        if not response_text:
            return llm_response

        redacted = _CARD_NUMBER_RE.sub("[REDACTED_CARD_NUMBER]", response_text)

        if redacted != response_text:
            logger.warning("[OutputGuardRail] Redacted card number from LLM response.")
            self._update_text(llm_response, redacted)

        return llm_response

    @staticmethod
    def _extract_text(llm_response: LlmResponse) -> str:
        if (
            hasattr(llm_response, "candidates")
            and llm_response.candidates
            and llm_response.candidates[-1].content
            and llm_response.candidates[-1].content.parts
        ):
            for part in llm_response.candidates[-1].content.parts:
                if getattr(part, "text", None):
                    return part.text
        return ""

    @staticmethod
    def _update_text(llm_response: LlmResponse, new_text: str) -> None:
        if (
            hasattr(llm_response, "candidates")
            and llm_response.candidates
            and llm_response.candidates[-1].content
        ):
            llm_response.candidates[-1].content.parts = [
                types.Part(text=new_text)
            ]

_ALLOWED_TOOLS = {"vertex_ai_search"}

_BLOCKED_QUERY_TERMS = {"financial records", "personal employee data"}


class ToolCallGuardRail:

    async def __call__(
        self,
        tool: BaseTool,
        tool_args: dict,
        tool_context: ToolContext,
    ) -> Optional[dict]:

        tool_name = tool.name if hasattr(tool, "name") else str(tool)

        logger.info(f"[ToolCallGuardRail] tool='{tool_name}' args={tool_args}")

        if tool_name not in _ALLOWED_TOOLS:
            logger.warning(
                f"[ToolCallGuardRail] Blocked unknown tool '{tool_name}'."
            )
            return {"error": f"Tool '{tool_name}' is not permitted."}

        if "query" in tool_args:
            query = tool_args["query"].lower().strip()

            if len(query.split()) < 2:
                logger.warning(
                    f"[ToolCallGuardRail] Blocked single-word query: '{query}'."
                )
                return {"error": "Query is too short. Please provide more context."}

            if any(term in query for term in _BLOCKED_QUERY_TERMS):
                logger.warning(
                    f"[ToolCallGuardRail] Blocked sensitive query: '{query}'."
                )
                return {"error": "Query contains restricted terms."}

        return None