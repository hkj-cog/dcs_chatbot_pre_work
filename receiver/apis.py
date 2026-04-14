import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Annotated, List, Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from google.genai import types

from agent.scoring import ConfidenceScorer
from agent.translate import Translator
from agent.utils import get_gcp_project_id
from agent.vertex_agent import runner, session_service
from libs.config import get_settings
from libs.dlp import GoogleDlp          # ← fix: use production-grade DLP from libs/
from libs.logger import logger
from libs.pubsub import send_message_to_pubsub
from .models import ChatRequest

router = APIRouter()

_settings = get_settings()

_dlp = GoogleDlp(
    project=get_gcp_project_id() or _settings.project_id,
    info_types=_settings.pii_data_types,
)

_scorer = ConfidenceScorer(
    llm=_settings.model_id,
    location=_settings.google_cloud_location,
)

@dataclass
class Reference:
    chunk: str
    url: str
    title: str

@router.get("/test")
async def test_endpoint():
    return {"message": "Success"}

async def handle_user_query(
    user_id: str,
    session_id: str,
    user_input: str,
    translate: bool = False,
) -> None:
    final_content: str = ""
    references: List[Reference] = []
    score: Optional[str] = None

    try:
        sanitized_input = _dlp.invoke(user_input)

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=sanitized_input)],
            ),
        ):
            if event.is_final_response() and event.content:
                parts = event.content.parts
                if parts:
                    text_out = getattr(parts[0], "text", None)
                    if isinstance(text_out, str):
                        final_content = text_out.strip()
                        logger.info(
                            f"Final agent output [{event.author}]: {final_content[:80]}…"
                        )
                    else:
                        final_content = str(event.content)
                else:
                    final_content = str(event.content)
                if (
                    event.grounding_metadata
                    and event.grounding_metadata.grounding_chunks
                ):
                    for chunk in event.grounding_metadata.grounding_chunks:
                        ctx = chunk.retrieved_context
                        references.append(
                            Reference(
                                chunk=ctx.text or "",
                                url=ctx.uri or "",
                                title=ctx.title or "",
                            )
                        )

            elif getattr(event, "error_code", None):
                logger.error(f"Agent returned error_code: {event.error_code}")
                final_content = "error"

        if translate and final_content and final_content != "error":
            is_different, translated = Translator.translate(
                user_input, final_content
            )
            if is_different:
                final_content = translated
                # Also translate reference titles
                references = [
                    Reference(
                        chunk=r.chunk,
                        url=r.url,
                        title=Translator.translate(user_input, r.title)[1]
                        if r.title
                        else "",
                    )
                    for r in references
                ]

        if references and final_content not in ("", "error"):
            try:
                score = _scorer.invoke(
                    question=sanitized_input,
                    answer=final_content,
                    context=", ".join(r.chunk for r in references),
                )
            except Exception as score_err:
                logger.warning(f"Confidence scoring failed (non-fatal): {score_err}")
                score = None

        payload = {
            "sender": "system",
            "content": final_content,
            "references": [asdict(r) for r in references],
            "score": score,
        }
        await send_message_to_pubsub(payload, session_id=session_id)

    except Exception as e:
        logger.error(f"Error processing user query for session_id={session_id}: {e}")
        await send_message_to_pubsub(
            {
                "sender": "system",
                "content": "system_error",
                "references": [],
                "score": None,
            },
            session_id=session_id,
        )
        raise


@router.post("/chat")
async def save_chat(
    request: ChatRequest,
    user_id: Annotated[str, Header(alias="X-User-ID")],
    session_id: Annotated[str | None, Header(alias="x-session-id")] = None,
) -> JSONResponse:

    if session_id:
        await session_service.get_session(
            session_id=session_id,
            app_name="adk-chatbot",
            user_id=user_id,
        )
    else:
        session = await session_service.create_session(
            app_name="adk-chatbot",
            user_id=user_id,
        )
        session_id = session.id

    asyncio.create_task(
        handle_user_query(user_id, session_id, request.user_input)
    )

    return JSONResponse(
        content={"reply": "accepted"},
        headers={"x-session-id": str(session_id)},
    )