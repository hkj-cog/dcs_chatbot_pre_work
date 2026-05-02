# FastAPI app entry point — startup/shutdown lifecycle and router registration
import asyncio
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # sets GOOGLE_GENAI_USE_VERTEXAI and other non-Settings vars

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent.vertex_agent import build_dlp, build_runner
from libs.config import get_settings
from libs.logger import logger
from libs.observability import get_status as observability_status, init_observability
from libs.redis_manager import redis_manager
from receiver.apis import _live_tasks, router as chat_router
from responders.api import router as ws_router
from services.chat_pipeline import ChatPipeline
from worker.api import router as pubsub_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising resources...")

    await redis_manager.init_pool()
    logger.info("Redis connection pool ready.")

    dlp = build_dlp(settings)
    runner, session_service = build_runner(dlp, settings)
    app.state.dlp = dlp
    app.state.runner = runner
    app.state.session_service = session_service
    app.state.pipeline = ChatPipeline(runner=runner, session_service=session_service, dlp=dlp)
    logger.info("Agent runner, DLP client, and pipeline ready.")
    logger.info("Observability status", extra={"observability": observability_status()})

    yield

    if _live_tasks:
        logger.info(f"Cancelling {len(_live_tasks)} in-flight task(s) before shutdown...")
        for task in list(_live_tasks):
            task.cancel()
        try:
            await asyncio.wait_for(
                asyncio.gather(*_live_tasks, return_exceptions=True),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error("Shutdown timeout: 30s exceeded waiting for in-flight tasks to cancel")
        logger.info("In-flight tasks cancelled.")

    logger.info("Shutting down — closing Redis connection pool...")
    await redis_manager.close_pool()
    logger.info("Redis connection pool closed.")


app = FastAPI(lifespan=lifespan)

# Initialise observability ONCE. Must run before routers are exercised.
init_observability(app)

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
if "*" in origins:
    raise RuntimeError(
        "ALLOWED_ORIGINS=* cannot be used with allow_credentials=True. "
        "Set explicit origins in .env (e.g. ALLOWED_ORIGINS=https://yourdomain.gov.au)."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id", "X-Request-Id", "Retry-After"],
)


# ── Correlation ID middleware ────────────────────────────────────────────────
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next) -> Response:
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


# ── Health endpoints ────────────────────────────────────────────��────────────
@app.get("/health", tags=["ops"])
async def health():
    return {"status": "ok"}


@app.get("/healthz", tags=["ops"])
async def healthz():
    """Detailed health, including observability status."""
    return {"status": "ok", "observability": observability_status()}


@app.get("/readiness", tags=["ops"])
async def readiness(request: Request):
    checks: dict[str, str] = {}

    client = redis_manager.get_client()
    try:
        await client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"unavailable: {exc}"
    finally:
        await client.aclose()

    try:
        _ = request.app.state.pipeline
        checks["pipeline"] = "ok"
    except AttributeError:
        checks["pipeline"] = "not initialised"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )


# ── API routers ──────────────────────────────────────────────────────────────
app.include_router(chat_router, prefix="/v1/conversation")
app.include_router(pubsub_router, prefix="/v1/webhook")
app.include_router(ws_router, prefix="/v1/ws")