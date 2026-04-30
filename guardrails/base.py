# Abstract base classes and GuardRailResult type shared across all guardrail layers
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class GuardRailResult:
    """Returned by every guardrail.process() call."""
    is_blocked: bool
    blocked_reason: str = ""
    modified_text: str = ""


class GuardRail(ABC):
    """Base class for input-layer guardrails (before_model_callback)."""

    # Implemented by each input guardrail to process text and optionally block it.
    @abstractmethod
    async def process(
        self,
        text: str,
        session_id: str = "",
        conversation_history: str = "",
        session_state: Optional[dict] = None,
    ) -> GuardRailResult: ...


class OutputGuardRailBase(ABC):
    """Base class for output-layer guardrails (after_model_callback)."""

    # Implemented by each output guardrail to process LLM text and optionally block or modify it.
    @abstractmethod
    async def process(
        self,
        text: str,
        session_id: str = "",
        session_state: Optional[dict] = None,
    ) -> GuardRailResult: ...
