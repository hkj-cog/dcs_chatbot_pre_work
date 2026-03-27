from typing import Annotated, Optional
from fastapi import APIRouter, Header, Response
from google.genai import types

from agent.vertex_agent import runner, session_service
from libs.logger import logger

from .models import ChatRequest

router = APIRouter()


@router.get("/test")  # Use @router, NOT @app
async def test_endpoint():
    return {"message": "Success"}


async def handle_user_query(
    user_id: str, session_id: str, user_input: str
) -> dict[str, str]:
    response: dict[str, str] = {}
    final_content = ""
    try:
        async for event in runner.run_async(
            user_id=user_id,  # Dynamic from header
            session_id=session_id,  # Dynamic from header
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_input)],  # Dynamic from body
            ),
        ):
            # 3. Handle the Events
            if event.is_final_response() and event.content:
                parts = getattr(event.content, "parts", [])
                if parts and hasattr(parts[0], "text"):
                    text_out = parts[0].text
                    print(f"Final Output: [{event.author}] {text_out}")
                    final_content += text_out
                else:
                    final_content += str(event.content)

            elif getattr(event, "error_code", None):
                final_content = "error"
    except Exception as e:
        logger.error(f"Error processing user query: {e}")
        final_content = "error"
    return {"sender": "system", "content": final_content}


@router.post("/chat")
async def save_chat(
    request: ChatRequest,
    user_id: Annotated[str, Header(alias="X-User-ID")],
    session_id: Annotated[Optional[str], Header(alias="x-session-id")] = None,
    response: Response = Response(),
):
    if session_id:
        session = await session_service.get_session(
            session_id=session_id,
            app_name="adk-chatbot",  # This should match the app_name used in your Agent definition
            user_id=user_id,
        )
        session_id = session_id

    if not session_id:
        session = await session_service.create_session(
            app_name="adk-chatbot",  # This should match the app_name used in your Agent definition
            user_id=user_id,
            # app_name should be defined globally or passed in
        )
        session_id = session.id
    final_response: dict[str, str] = await handle_user_query(
        user_id, session_id, request.user_input
    )
    return final_response
