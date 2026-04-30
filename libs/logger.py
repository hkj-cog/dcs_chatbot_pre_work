# Structured JSON logging with OTel trace correlation, GuardRailEvent dataclass, and SIEM escalation helpers.
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from libs.config import GUARDRAILS_VERSION, get_settings


class _TraceContextFilter(logging.Filter):
    """Injects current OTel trace_id/span_id (if any) into every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace  # local import — avoids hard dep at logger import time
            span = trace.get_current_span()
            ctx = span.get_span_context() if span else None
            if ctx and ctx.is_valid:
                record.trace_id = format(ctx.trace_id, "032x")
                record.span_id = format(ctx.span_id, "016x")
                return True
        except Exception:
            pass
        record.trace_id = ""
        record.span_id = ""
        return True


class _JsonFormatter(logging.Formatter):
    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "file": record.filename,
            "line": record.lineno,
            "trace_id": getattr(record, "trace_id", ""),
            "span_id": getattr(record, "span_id", ""),
        }
        for k, v in record.__dict__.items():
            if k not in self._RESERVED and not k.startswith("_") and k not in payload:
                payload[k] = v
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_app_logger(name: str = "dcs_chatbot") -> logging.Logger:
    """Creates and configures the structured stdout logger used across the entire application."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    # Fall back to JSON if Settings isn't importable yet (e.g. during Settings.model_post_init).
    try:
        log_format = get_settings().observability_log_format
    except Exception:
        log_format = "json"

    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s "
                "trace=%(trace_id)s span=%(span_id)s — %(message)s"
            )
        )
    handler.addFilter(_TraceContextFilter())
    logger.addHandler(handler)
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
    payload = asdict(event)
    if event.action == "block":
        logger.warning("guardrail_event", extra={"guardrail_event": payload})
    else:
        logger.info("guardrail_event", extra={"guardrail_event": payload})


def log_escalation_event(
    session_id: str,
    trigger_count: int,
    last_guardrail: str,
    reason: str,
) -> None:
    """Emits a CRITICAL structured escalation log when a session exceeds the threat threshold."""
    logger.critical(
        "escalation_event",
        extra={
            "escalation_event": {
                "session_id": session_id,
                "trigger_count": trigger_count,
                "last_guardrail": last_guardrail,
                "reason": reason,
            }
        },
    )