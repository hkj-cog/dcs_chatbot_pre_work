import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry import trace, _logs
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from phoenix.otel import register
from libs.config import Settings
from libs.phoenix_logger import SpanLogHandler, tracer_provider
from libs.redis_manager import redis_manager
from receiver.apis import router as save_router
from responders.api import router as ws_router
from worker.api import process_redis_message
from worker.api import router as pubsub_router
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

settings = Settings()

tracer_provider = register(
    project_name="dcs-chat",
    batch=False,  # Use sync export because Agent Engine pauses CPU after requests
    set_global_tracer_provider=False,  # Required: avoids conflict with Agent Engine's global provider
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

app = FastAPI()


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
