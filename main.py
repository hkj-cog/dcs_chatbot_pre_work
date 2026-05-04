import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry import trace, _logs
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from phoenix.otel import Resource, SimpleSpanProcessor, register
from phoenix.otel.otel import TracerProvider as PhoenixTracerProvider
from libs.config import Settings
from libs.context import session_ctx, user_ctx
from libs.logger import logger
from libs.phoenix_provider import phoenix_provider
from libs.redis_manager import redis_manager
from receiver.apis import router as save_router
from responders.api import router as ws_router
from worker.api import process_redis_message
from worker.api import router as pubsub_router
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
import os
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://localhost:6006"
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4317"

settings = Settings()


# ----- GCP provider: receives FastAPI + ADK spans -----
# gcp_provider = TracerProvider()
# gcp_provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
# trace.set_tracer_provider(gcp_provider)  # global → FastAPI uses this
#
# # ----- Phoenix provider: receives ADK spans only -----
# phoenix_provider = PhoenixTracerProvider(
#     resource=Resource.create({
#         "openinference.project.name": "dcs-chat",
#         "service.name": "dcs-chatbot-api",
#     })
# )
# phoenix_provider.add_span_processor(
#     SimpleSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:6006/v1/traces"))  # ✅ wrap it
# )
#
# # ----- Wire instrumentors -----
# app = FastAPI()
# FastAPIInstrumentor.instrument_app(app, tracer_provider=gcp_provider)
#
# # ADK fans out to BOTH providers
# GoogleADKInstrumentor().instrument(tracer_provider=phoenix_provider)
# GoogleADKInstrumentor().instrument(tracer_provider=gcp_provider)


PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"

gcp_provider = TracerProvider(
    resource=Resource.create({
        "openinference.project.name": "dcs-chat",
        "service.name": "dcs-chatbot-api",
    })
)
class RootSpanOnlyProcessor(SpanProcessor):
    def __init__(self, wrapped):
        self._wrapped = wrapped
    def on_start(self, span, parent_context=None):
        self._wrapped.on_start(span, parent_context)
    def on_end(self, span):
        if span.parent is None and span.kind == trace.SpanKind.SERVER:
            self._wrapped.on_end(span)
    def shutdown(self):
        self._wrapped.shutdown()
    def force_flush(self, timeout_millis=30_000):
        return self._wrapped.force_flush(timeout_millis)


gcp_provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
#
# trace.set_tracer_provider(gcp_provider)

# tracer_provider = register(
#     project_name="dcs-chat",
#     endpoint="http://localhost:6006/v1/traces",
#     auto_instrument=True,   # picks up installed OpenInference instrumentors
#     set_global_tracer_provider=True,
# )

# tracer_provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
app = FastAPI()
FastAPIInstrumentor.instrument_app(app, tracer_provider=phoenix_provider)
GoogleADKInstrumentor().instrument(tracer_provider=phoenix_provider)
trace.set_tracer_provider(gcp_provider)

raw_origins = settings.allowed_origins

origins = [o.strip() for o in raw_origins.split(",") if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id"],
)
app.include_router(save_router, prefix="/conversation")
app.include_router(pubsub_router, prefix="/webhook")
app.include_router(ws_router, prefix="/ws")
