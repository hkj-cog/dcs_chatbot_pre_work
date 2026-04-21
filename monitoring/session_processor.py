from openinference.instrumentation import (
    get_attributes_from_context,
)
from opentelemetry.sdk._logs import (
    LogData,
    LogRecordProcessor,
)

class GlobalSessionIdProcessor(LogRecordProcessor):
    def on_emit(self, log_data: LogData):
        record = log_data.log_record
        
        context_attrs = dict(get_attributes_from_context())
        
        session_id = context_attrs.get("session_id") or context_attrs.get("session.id")
        user_id = context_attrs.get("user_id") or context_attrs.get("user.id")

        if record.attributes is None:
            record.attributes = {}
        
        # 3. Safely inject attributes into the log record
        if session_id:
            record.attributes["session_id"] = str(session_id)
            
        if user_id:
            record.attributes["user_id"] = str(user_id)

    def shutdown(self) -> None:
        """Required by the LogRecordProcessor interface"""
        pass

    def force_flush(self, timeout_millis: int = 30000):
        """Required by the LogRecordProcessor interface"""
        return None
