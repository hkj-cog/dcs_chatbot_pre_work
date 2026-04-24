# HTTP chat endpoint (/v1/conversation/chat) — rate-limiting, session init, and pipeline dispatch
import asyncio
import time
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from libs.config import get_settings
from libs.logger import logger
from libs.redis_manager import redis_manager
from libs.validation import SESSION_ID_RE, USER_ID_RE
from services.chat_pipeline import PipelineContext
from .models import ChatRequest

router = APIRouter()

_settings = get_settings()
_live_tasks: set[asyncio.Task] = set()


async def _check_rate_limit(user_id: str) -> None:
    """
    Sliding-window rate limiter backed by Redis (ZSET per user_id).
    Raises HTTP 429 if the configured limit is exceeded.
    Fail-open: Redis unavailable allows the request through.
    """
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


# Smoke-test endpoint to confirm the router is reachable
@router.get("/test")
async def test_endpoint():
    return {"message": "Success"}


# HTTP entry point for chat: validates headers, enforces rate limit, resolves session, dispatches pipeline
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
            session_id=session_id,
            app_name="adk_chatbot",
            user_id=user_id,
        )
        if existing is None:
            return JSONResponse(
                status_code=404,
                content={"error": "Session not found. Please start a new session."},
            )
    else:
        session = await session_service.create_session(
            app_name="adk_chatbot",
            user_id=user_id,
        )
        session_id = session.id

    request_id = str(uuid.uuid4())

    ctx = PipelineContext(
        user_id=user_id,
        session_id=session_id,
        user_input=body.user_input,
        translate=body.translate,
        request_id=request_id,
    )

    task = asyncio.create_task(request.app.state.pipeline.run(ctx))
    _live_tasks.add(task)
    task.add_done_callback(_live_tasks.discard)

    return JSONResponse(
        content={"reply": "accepted", "request_id": request_id},
        headers={"x-session-id": str(session_id)},
    )
