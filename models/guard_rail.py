from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from google.cloud import language_v1
from guardrails import Guard
from guardrails.errors import ValidationError
from guardrails.hub import DetectJailbreak

from libs.logger import logger


# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------
@dataclass
class GuardRailResult:
    is_blocked: bool
    blocked_reason: str = ""
    modified_text: str = ""


class GuardRail(ABC):
    @abstractmethod
    async def process(self, text: str) -> GuardRailResult:
        """Processes the text and decides to block or modify."""
        pass


# ---------------------------------------------------------------------------
# 1. Date/Time injection — prepends current datetime to user text
#    Mirrors inject_date_time_context from agent/guardrails.py
# ---------------------------------------------------------------------------
class DateTimeInjectorGuardRail(GuardRail):
    """
    Prepends the current date and time to the user message so the LLM is
    always temporally aware. Returns a MODIFY result (never blocks).
    """
    async def process(self, text: str) -> GuardRailResult:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        modified = f"[Context: Today is {now}]\n{text}"
        logger.info(f"[DateTimeInjectorGuardRail] Injected datetime context.")
        return GuardRailResult(is_blocked=False, modified_text=modified)


# ---------------------------------------------------------------------------
# 2. Jailbreak detection — blocks prompt injection / jailbreak attempts
#    Mirrors input_guardrail from agent/guardrails.py
# ---------------------------------------------------------------------------
_jailbreak_guard = Guard().use(DetectJailbreak)


class JailbreakGuardRail(GuardRail):
    """
    Validates user input against the guardrails-ai DetectJailbreak validator.
    Blocks the request if a jailbreak attempt is detected.
    Requires: guardrails hub install hub://guardrails/detect_jailbreak
    """
    async def process(self, text: str) -> GuardRailResult:
        try:
            outcome = _jailbreak_guard.validate(text)
            if not outcome.validation_passed:
                logger.warning(f"[JailbreakGuardRail] Jailbreak detected. Blocking.")
                return GuardRailResult(
                    is_blocked=True,
                    blocked_reason=(
                        "I'm designed to follow my instructions carefully. "
                        "Please rephrase your query if you intended something specific."
                    ),
                )
        except ValidationError as e:
            logger.warning(f"[JailbreakGuardRail] ValidationError: {e}. Blocking.")
            return GuardRailResult(
                is_blocked=True,
                blocked_reason=(
                    "I'm designed to follow my instructions carefully. "
                    "Please rephrase your query if you intended something specific."
                ),
            )
        return GuardRailResult(is_blocked=False)


# ---------------------------------------------------------------------------
# 3. Profanity detection — uses Google Cloud NLP moderateText API
# ---------------------------------------------------------------------------
class ProfanityGuardRail(GuardRail):
    def __init__(self, threshold=0.5):
        self.threshold = threshold

    async def process(self, text: str) -> GuardRailResult:
        try:
            checker = ProfanityChecker(text, threshold=self.threshold)
            if checker.contains_profanity:
                return GuardRailResult(is_blocked=True, blocked_reason="Profanity detected")
        except Exception as e:
            logger.error(f"Error in ProfanityGuardRail: {e}")
            return GuardRailResult(is_blocked=True, blocked_reason="Profanity detection error")
        return GuardRailResult(is_blocked=False)


class ProfanityChecker:
    """
    Uses Google Cloud Natural Language API's moderateText to check for
    profanity and other moderation categories.
    """

    def __init__(self, text: str, language: str = "en", threshold: float = 0.5):
        self.text = text
        self.language = language
        self.threshold = threshold
        self.profanity_confidence = None
        self.contains_profanity = False
        self.moderation_categories = []
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
        except Exception as e:
            logger.info(f"[ProfanityChecker] Error: {e}")
            self.profanity_confidence = None
            self.contains_profanity = False
            self.moderation_categories = []