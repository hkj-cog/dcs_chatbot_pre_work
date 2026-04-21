import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from opentelemetry import trace, _logs
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from libs.config import Settings
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

# TODO test
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     await redis_manager.init_pool()
#
#     # Pass the function 'process_redis_message' as the callback
#     sub_task = asyncio.create_task(
#         redis_manager.start_subscriber("user_*", process_redis_message)
#     )
#
#     yield
#
#     sub_task.cancel()
#     await redis_manager.close_pool()



# app = FastAPI(lifespan=lifespan)
tracer_provider = TracerProvider()
trace.set_tracer_provider(tracer_provider)

# 2. GCP Plugin: Add the Exporter
# This tells the Provider: "Whenever you finish a span, send it to Google Cloud Trace."
tracer_provider.add_span_processor(
    BatchSpanProcessor(CloudTraceSpanExporter())
)

GoogleADKInstrumentor().instrument(
    tracer_provider=trace.get_tracer_provider(),
    logger_provider=_logs.get_logger_provider()
)

app = FastAPI()

# Instrument FastAPI to capture traces
FastAPIInstrumentor.instrument_app(app)

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
