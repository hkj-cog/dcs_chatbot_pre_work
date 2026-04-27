"""LogRecordProcessor that copies session_id/user_id from OpenInference context
into the OTel log record. Used only when the OTel→GCP log bridge is enabled."""
from __future__ import annotations

from typing import Any

# opentelemetry.sdk.logs (public) does not exist in SDK ≤1.38.0; _logs is the only path.
# Revisit when OTel stabilises the public logging API across the installed version range.
from opentelemetry.sdk._logs import LogData, LogRecordProcessor

try:
    from openinference.instrumentation import get_attributes_from_context
except Exception:  # pragma: no cover
    def get_attributes_from_context() -> dict[str, Any]:
        return {}


class GlobalSessionIdProcessor(LogRecordProcessor):
    def on_emit(self, log_data: LogData) -> None:
        record = log_data.log_record
        ctx_attrs = dict(get_attributes_from_context())

        session_id = ctx_attrs.get("session_id") or ctx_attrs.get("session.id")
        user_id = ctx_attrs.get("user_id") or ctx_attrs.get("user.id")

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