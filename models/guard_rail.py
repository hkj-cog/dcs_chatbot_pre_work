from dataclasses import dataclass
from typing import Optional
from google.cloud import language_v1 
from abc import ABC, abstractmethod

from libs.logger import logger

@dataclass
class GuardRailResult:
    is_blocked: bool
    blocked_reason: str = "" 
    modified_text: str="" 

class GuardRail(ABC):
    @abstractmethod
    async def process(self, text: str) -> GuardRailResult:
        """Processes the text and decides to block or modify."""
        pass


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
            return GuardRailResult(is_blocked=True, blocked_reason="Profanity detectiong error")
        return GuardRailResult(is_blocked=False)


class ProfanityChecker:
    """
    Uses Google Cloud Natural Language API's moderateText to check for profanity and other moderation categories.
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
            self.moderation_categories = []
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
