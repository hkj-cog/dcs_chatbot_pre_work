import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Type

# Replace with your actual imports
# from google.cloud.aiplatform_v1beta1.types import content as types
# from your_framework import CallbackContext

logger = logging.getLogger(__name__)

# --- 1. Data Structures ---

@dataclass
class InjectionContext:
    """Container to accumulate context lines during the injection phase."""
    lines: List[str] = field(default_factory=list)
    original_text: str = ""

# --- 2. Registry Mechanism ---

INJECTOR_REGISTRY: Dict[str, 'BaseInjector'] = {}

def injector(name: str):
    """Decorator to register an injector automatically by name."""
    def wrapper(cls: Type['BaseInjector']):
        INJECTOR_REGISTRY[name] = cls()
        return cls
    return wrapper

class BaseInjector(ABC):
    @abstractmethod
    def inject(self, ctx: InjectionContext):
        """Add lines to ctx.lines based on specific logic."""
        pass

# --- 3. Concrete Injector Examples ---

@injector("datetime")
class DateTimeInjector(BaseInjector):
    def inject(self, ctx: InjectionContext):
        now = datetime.now().strftime("%Y-%m-%d")
        ctx.lines.append(f"Current date is {now}")

@injector("location")
class LocationInjector(BaseInjector):
    def inject(self, ctx: InjectionContext):
        # This could be dynamic (e.g., pulled from a lookup service)
        ctx.lines.append("Location is Sydney")
