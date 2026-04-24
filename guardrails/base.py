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
    @abstractmethod
    # Abstract interface — implemented by each input guardrail to process and optionally block user text
    async def process(
        self,
        text: str,
        session_id: str = "",
        conversation_history: str = "",
        session_state: Optional[dict] = None,
    ) -> GuardRailResult: ...


class OutputGuardRailBase(ABC):
    """Base class for output-layer guardrails (after_model_callback)."""
    @abstractmethod
    # Abstract interface — implemented by each output guardrail to process and optionally block LLM output
    async def process(
        self,
        text: str,
        session_id: str = "",
        session_state: Optional[dict] = None,
    ) -> GuardRailResult: ...
