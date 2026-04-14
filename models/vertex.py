import asyncio
from typing import Callable, Union

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions import InMemorySessionService
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from google.genai.types import SafetySetting

from libs import logger
from models.guard_rail import GuardRail

InputOutputCallback = Callable[[CallbackContext, LlmRequest], None | LlmResponse]
ToolCallback = Callable[
    [BaseTool, dict[str, object], ToolContext], dict[str, str] | None
]
ToolAfterCallback = Callable[
    [BaseTool, dict[str, object], ToolContext, dict[object, object]],
    dict[str, str] | None,
]
AgentTool = Union[FunctionTool, BaseTool, BaseToolset]


class VertexAIAgent:
    def __init__(
        self,
        model_id: str,
        user_id: str,
        instructions: str,
        tools: list[AgentTool],
        agent_name: str,
        agent_description: str,
        input_guardrails: list[GuardRail] | None = None,
        output_guardrails: list[InputOutputCallback] | None = None,        # ← uncommented
        before_tool_guardrails: list[ToolCallback] | None = None,          # ← uncommented
        after_tool_guardrails: list[ToolAfterCallback] | None = None,      # ← uncommented
        safety_settings: list[SafetySetting] | None = None,
        translate: bool = False,
    ) -> None:
        self._agent: LlmAgent = LlmAgent(
            name=agent_name,
            model=model_id,
            tools=tools,
            instruction=instructions,
            description=agent_description,
            before_model_callback=(
                self.__before_model_callback(input_guardrails)
                if input_guardrails is not None
                else None
            ),
            after_model_callback=output_guardrails,        # ← uncommented
            before_tool_callback=before_tool_guardrails,   # ← uncommented
            after_agent_callback=after_tool_guardrails,    # ← uncommented
            generate_content_config=types.GenerateContentConfig(
                safety_settings=safety_settings or []
            ),
        )
        self._translate = translate
        self._in_memory_session_service: InMemorySessionService = (
            InMemorySessionService()
        )

    def __before_model_callback(self, guard_rails: list[GuardRail]):
        async def callback(
            callback_context: CallbackContext,
            llm_request: LlmRequest,
        ) -> LlmResponse | None:
            logger.info(
                f"[Before Model Callback] Processing LLM request for agent "
                f"'{callback_context.agent_name}' with {len(guard_rails)} guard rails."
            )
            if not llm_request.contents or llm_request.contents[-1].role != "user":
                return None

            user_content = llm_request.contents[-1]

            for part in (user_content.parts or []):
                if not part.text:
                    continue

                current_text = part.text
                tasks = [rail.process(current_text) for rail in guard_rails]
                outcomes = await asyncio.gather(*tasks)

                # Block if any rail signals a block
                for outcome in outcomes:
                    if outcome.is_blocked:
                        logger.warning(f"[Guard Rail Blocked]: {outcome.blocked_reason}")
                        return LlmResponse(
                            content=types.Content(
                                parts=[types.Part.from_text(text=outcome.blocked_reason)],
                                role="model",
                            )
                        )

                # Apply modifications from all rails in order
                final_text = current_text
                for outcome in outcomes:
                    if outcome.modified_text != "":
                        final_text = outcome.modified_text

                part.text = final_text

            return None

        return callback