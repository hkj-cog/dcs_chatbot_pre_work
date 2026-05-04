
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import SpanProcessor
from phoenix.otel import Resource
from phoenix.otel.otel import BatchSpanProcessor, SimpleSpanProcessor, TracerProvider

from libs.context import chain_input_ctx, root_span_ctx, session_ctx
from libs.logger import logger

class OpenInferenceEnricher(SpanProcessor):
    def on_start(self, span, parent_context=None):
        current_value = session_ctx.get()
        logger.info(f"Processor triggered. Context value: {current_value}") # Is this None?
        
        if current_value:
            span.set_attribute("session.id", current_value)
    def on_end(self, span): pass
    def shutdown(self): pass
    def force_flush(self, timeout_millis=30_000): return True

class ChainInputCapture(SpanProcessor):
    def on_start(self, span, parent_context=None):
        attrs = span.attributes or {}
        if attrs.get("openinference.span.kind") == "CHAIN":
            input_value = attrs.get("input.value")
            if input_value and chain_input_ctx.get() is None:
                # Only capture the outermost CHAIN, not nested sub-agent CHAINs
                chain_input_ctx.set(str(input_value))

    def on_end(self, span):
        attrs = span.attributes or {}
        if attrs.get("openinference.span.kind") == "CHAIN":
            if chain_input_ctx.get() == attrs.get("input.value"):
                chain_input_ctx.set(None)

    def shutdown(self): pass
    def force_flush(self, timeout_millis=30_000): return True

class RootInputMirror(SpanProcessor):
    def on_start(self, span, parent_context=None):
        attrs = span.attributes or {}

        # 1. Capture the root span (no valid parent in this process)
        if span.parent is None or not span.parent.is_valid:
            root_span_ctx.set(span)
            return

        # 2. When the CHAIN span starts, copy its input.value to the root
        if attrs.get("openinference.span.kind") == "CHAIN":
            input_value = attrs.get("input.value")
            if not input_value:
                return
            root = root_span_ctx.get()
            if root is not None:
                root.set_attribute("input.value", input_value)
                mime = attrs.get("input.mime_type")
                if mime:
                    root.set_attribute("input.mime_type", mime)

    def on_end(self, span):
        if root_span_ctx.get() is span:
            root_span_ctx.set(None)

    def shutdown(self): pass
    def force_flush(self, timeout_millis=30_000): return True

phoenix_provider = TracerProvider(
    resource=Resource.create({
        "openinference.project.name": "dcs-chat",
        "service.name": "dcs-chatbot-api",
    })
)
phoenix_exporter = OTLPSpanExporter(
    endpoint="http://localhost:6006/v1/traces",
    headers={"Phoenix-Project-Name": "dcs-chat"},
)
phoenix_provider.add_span_processor(RootInputMirror())
phoenix_provider.add_span_processor(BatchSpanProcessor(phoenix_exporter))


