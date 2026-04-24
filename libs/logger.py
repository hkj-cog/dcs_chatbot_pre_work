# Structured JSON logging — GuardRailEvent dataclass and SIEM escalation helpers
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from typing import Literal

from libs.config import GUARDRAILS_VERSION


# Creates and configures the structured stdout logger used across the entire application
def setup_app_logger(name: str = "dcs_chatbot") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger


logger = setup_app_logger()


@dataclass
class GuardRailEvent:
    """Structured record emitted for every guardrail decision, consumed by Cloud Logging and SIEM."""
    guardrail_name: str
    layer: Literal["input", "output", "post-process", "tool"]
    action: Literal["block", "modify", "allow"]
    session_id: str
    triggered: bool
    reason: str = ""
    snippet: str = ""  # first ≤80 chars of checked text — never raw PII
    policy_version: str = field(default_factory=lambda: GUARDRAILS_VERSION)


def log_guardrail_event(event: GuardRailEvent) -> None:
    """Emits a structured JSON guardrail event line. Block events use WARNING severity."""
    payload = json.dumps({"guardrail_event": asdict(event)})
    if event.action == "block":
        logger.warning(payload)
    else:
        logger.info(payload)


def log_escalation_event(
    session_id: str,
    trigger_count: int,
    last_guardrail: str,
    reason: str,
) -> None:
    """Emits a CRITICAL structured escalation log when a session exceeds the threat threshold."""
    logger.critical(json.dumps({
        "escalation_event": {
            "session_id": session_id,
            "trigger_count": trigger_count,
            "last_guardrail": last_guardrail,
            "reason": reason,
        }
    }))
