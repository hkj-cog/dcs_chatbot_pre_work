import logging
import sys
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from fastapi import FastAPI

from libs.config import get_settings
from monitoring.session_processor import GlobalSessionIdProcessor

setting = get_settings()


# ---- 1. Tracer provider → Phoenix ----
resource = Resource.create({"service.name": "dcs_chatbot"})
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{setting.phoenix_collector_endpoint}/v1/traces")
    )
)
trace.set_tracer_provider(tracer_provider)


# ---- 2. Log → span event bridge ----
class SpanLogHandler(logging.Handler):
    """Attach every log record as an event on the current active span."""

    def emit(self, record: logging.LogRecord):
        span = trace.get_current_span()
        if span is None or not span.is_recording():
            return
        attrs = {
            "log.severity": record.levelname,
            "log.logger": record.name,
            "log.file": record.filename,
            "log.line": record.lineno,
        }
        # Let your existing session processor contribute here if needed
        span.add_event(name=record.getMessage()[:200], attributes=attrs)
        if record.exc_info and record.exc_info[1]:
            span.record_exception(record.exc_info[1])


def setup_app_logger(name: str = "dcs_chatbot") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(console)

        logger.addHandler(SpanLogHandler())

    return logger


logger = setup_app_logger("dcs_chatbot")
