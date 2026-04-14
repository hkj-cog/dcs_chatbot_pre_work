import asyncio
from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from google.genai import types

from agent.dlp import GoogleDlp
from agent.utils import get_gcp_project_id
from agent.vertex_agent import runner, session_service
from libs.config import get_settings
from libs.logger import logger
from libs.pubsub import send_message_to_pubsub
from .models import ChatRequest

router = APIRouter()

# DLP singleton — initialised once at module load, reused for all requests
_settings = get_settings()
_dlp = GoogleDlp(
    project=get_gcp_project_id() or _settings.project_id,
    info_types=_settings.pii_data_types,
)


@router.get("/test")
async def test_endpoint():
    return {"message": "Success"}


async def handle_user_query(user_id: str, session_id: str, user_input: str):
    final_content = ""
    try:
        # ── Guardrail: DLP — strip PII before agent sees the input ──────────
        sanitized_input = _dlp.invoke(user_input)

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=sanitized_input)],  # sanitized
            ),
        ):
            if event.is_final_response() and event.content:
                parts = event.content.parts
                if parts:
                    text_out = getattr(parts[0], "text", None)
                    if isinstance(text_out, str):
                        print(f"Final Output: [{event.author}] {text_out}")
                        final_content += text_out
                    else:
                        final_content += str(event.content)
                else:
                    final_content += str(event.content)
            elif getattr(event, "error_code", None):
                final_content = "error"

        await send_message_to_pubsub(
            {"sender": "system", "content": final_content}, session_id=session_id
        )
    except Exception as e:
        logger.error(f"Error processing user query: {e}")
        await send_message_to_pubsub(
            {"sender": "system", "content": "system_error"}, session_id=session_id
        )
        raise e


@router.post("/chat")
async def save_chat(
    request: ChatRequest,
    user_id: Annotated[str, Header(alias="X-User-ID")],
    session_id: Annotated[str | None, Header(alias="x-session-id")] = None,
):
    if session_id:
        await session_service.get_session(
            session_id=session_id,
            app_name="adk-chatbot",
            user_id=user_id,
        )

    if not session_id:
        session = await session_service.create_session(
            app_name="adk-chatbot",
            user_id=user_id,
        )
        session_id = session.id

    _ = asyncio.create_task(handle_user_query(user_id, session_id, request.user_input))

    return JSONResponse(
        content={"reply": "accepted"}, headers={"x-session-id": str(session_id)}
    )