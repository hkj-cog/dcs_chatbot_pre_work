import asyncio
from typing import Callable, Union
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from google.genai.types import SafetySetting

from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from libs import logger
from models.guard_rail import GuardRail, GuardRailResult

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
        # output_guardrails: list[InputOutputCallback] | None = None,
        # before_tool_guardrails: list[ToolCallback] | None = None,
        # after_tool_guardrails: list[ToolAfterCallback] | None = None,
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
            # after_model_callback=output_guardrails,
            # before_tool_callback=before_tool_guardrails,
            # after_agent_callback=after_tool_guardrails,
            generate_content_config=types.GenerateContentConfig(
                safety_settings=safety_settings
            ),
        )

        # self._scorer = ConfidenceScorer(
        #     llm=model_id, location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        # )
        self._translate = translate
        # Initialize an in-memory session service to manage conversation states
        # across multiple interactions without needing a database.
        self._in_memory_session_service: InMemorySessionService = (
            InMemorySessionService()
        )

    def __before_model_callback(self, guard_rails: list[GuardRail]):
        async def callback(
            callback_context: CallbackContext,
            llm_request: LlmRequest,
        ) -> LlmResponse | None:
            
            logger.info(f"[Before Model Callback] Processing LLM request for agent '{callback_context.agent_name}' with {len(guard_rails)} guard rails.")
            # 1. Extract the latest user message
            if not llm_request.contents or llm_request.contents[-1].role != "user":
                return None

            user_content = llm_request.contents[-1]
            
            for part in (user_content.parts or []):
                if not part.text:
                    continue
                    
                current_text = part.text

                # The * (splat) unpacks the list into individual coroutine arguments.
                tasks = [rail.process(current_text) for rail in guard_rails]
                outcomes = await asyncio.gather(*tasks)

                # 3. Evaluation Logic
                # Check if any rail wants to BLOCK
                for outcome in outcomes:
                    if outcome.is_blocked:
                        print(f"[Guard Rail Blocked]: {outcome.blocked_reason}")
                        return LlmResponse(
                            content=types.Content(
                                parts=[types.Part.from_text(text=outcome.blocked_reason)],
                                role="model"
                            )
                        )

                # 4. Merge Logic for MODIFY
                # If no blocks, apply all redactions/modifications found
                final_text = current_text
                for outcome in outcomes:
                    if outcome.modified_text != "":
                        # We apply the modified version of the text
                        # Note: If multiple rails modify, this logic assumes 
                        # they are modifying different parts or are additive.
                        final_text = outcome.modified_text

                # Update the request in-place with the final cleaned text
                part.text = final_text

            # Return None to allow the LLM call to proceed with the modified text
            return None

        return callback

