"""Copies session_id/user_id from the active OTel span into log records. Active only when GCP Cloud Logging bridge is wired."""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk._logs import LogData, LogRecordProcessor

# _logs is the only path in OTel SDK ≤1.38.0; revisit when the public logging API stabilises.


class GlobalSessionIdProcessor(LogRecordProcessor):
    def on_emit(self, log_data: LogData) -> None:
        # Copies session_id and user_id from the active OTel span into the log record attributes.
        record = log_data.log_record
        span = trace.get_current_span()
        if not (span and span.is_recording()):
            return
        attrs = span.attributes or {}
        session_id = attrs.get("session.id")
        user_id = attrs.get("user.id")
        if record.attributes is None:
            record.attributes = {}
        if session_id:
            record.attributes["session_id"] = str(session_id)
        if user_id:
            record.attributes["user_id"] = str(user_id)

    def shutdown(self) -> None:  # pragma: no cover
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # pragma: no cover
        return True
