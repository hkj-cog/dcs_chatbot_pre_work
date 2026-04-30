# HTTP chat endpoint (/v1/conversation/chat) — rate-limiting, session init, and pipeline dispatch
import asyncio
import time
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from opentelemetry import context as otel_context
from opentelemetry import trace

from libs.config import get_settings
from libs.logger import logger
from libs.observability import record_exception_on_span, with_session_attrs
from libs.redis_manager import redis_manager
from libs.validation import SESSION_ID_RE, USER_ID_RE
from monitoring.redaction import default_redactor
from services.chat_pipeline import PipelineContext

from .models import ChatRequest

router = APIRouter()

_settings = get_settings()
_redactor = default_redactor()
_live_tasks: set[asyncio.Task] = set()


async def _check_rate_limit(user_id: str) -> None:
    limit = _settings.rate_limit_per_minute
    window = 60
    now = time.time()
    key = f"rate_limit:{user_id}"
    client = redis_manager.get_client()
    try:
        async with client.pipeline() as pipe:
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window)
            results = await pipe.execute()
        count = results[2]
        if count > limit:
            logger.warning(f"[RateLimiter] user={user_id!r} exceeded {limit} req/min (count={count})")
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {limit} requests per minute.",
                headers={"Retry-After": "60"},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"[RateLimiter] Redis unavailable (fail-open): {exc}")
    finally:
        await client.aclose()


@router.get("/test")
async def test_endpoint():
    return {"message": "Success"}


async def _run_pipeline_with_context(pipeline, ctx: "PipelineContext", otel_ctx) -> None:
    """Background task wrapper: re-attaches the OTel context so the pipeline's spans
    inherit the request's trace_id, session.id and user.id baggage."""
    token = otel_context.attach(otel_ctx)
    try:
        with with_session_attrs(session_id=ctx.session_id, user_id=ctx.user_id):
            await pipeline.run(ctx)
    except Exception as e:
        record_exception_on_span(e)
        logger.exception(
            "Pipeline task failed",
            extra={"session_id": ctx.session_id, "user_id": ctx.user_id, "request_id": ctx.request_id},
        )
        raise
    finally:
        otel_context.detach(token)


@router.post("/chat")
async def save_chat(
    request: Request,
    body: ChatRequest,
    user_id: Annotated[str, Header(alias="X-User-ID")],
    session_id: Annotated[Optional[str], Header(alias="x-session-id")] = None,
) -> JSONResponse:
    if not USER_ID_RE.match(user_id):
        raise HTTPException(status_code=400, detail="Invalid X-User-ID format")
    if session_id and not SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid x-session-id format")

    await _check_rate_limit(user_id)

    session_service = request.app.state.session_service

    if session_id:
        existing = await session_service.get_session(
            session_id=session_id, app_name="adk_chatbot", user_id=user_id,
        )
        if existing is None:
            return JSONResponse(
                status_code=404,
                content={"error": "Session not found. Please start a new session."},
            )
    else:
        session = await session_service.create_session(
            app_name="adk_chatbot", user_id=user_id,
        )
        session_id = session.id

    # Re-use the X-Request-Id the correlation middleware already stamped on this request.
    request_id = request.state.request_id

    # Tag the FastAPI server span with the IDs and a redacted preview of the input.
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute("session.id", str(session_id))
        current_span.set_attribute("user.id", user_id)
        current_span.set_attribute("request.id", request_id)
        # Length only — never raw input — plus a redacted preview for debugging.
        current_span.set_attribute("input.length", len(body.user_input or ""))
        current_span.set_attribute(
            "input.preview.redacted",
            _redactor.redact((body.user_input or ""))[:256],
        )

    ctx = PipelineContext(
        user_id=user_id,
        session_id=session_id,
        user_input=body.user_input,
        translate=body.translate,
        request_id=request_id,
    )

    # Captures OTel context so the background pipeline span is a child of the HTTP request span.
    otel_ctx = otel_context.get_current()

    with with_session_attrs(session_id=session_id, user_id=user_id):
        logger.info(
            "Accepted chat request",
            extra={"session_id": session_id, "user_id": user_id, "request_id": request_id},
        )
        task = asyncio.create_task(
            _run_pipeline_with_context(request.app.state.pipeline, ctx, otel_ctx)
        )
        _live_tasks.add(task)
        task.add_done_callback(_live_tasks.discard)

    return JSONResponse(
        content={"reply": "accepted", "request_id": request_id},
        headers={"x-session-id": str(session_id)},
    )