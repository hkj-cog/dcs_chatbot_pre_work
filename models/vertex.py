import asyncio
from typing import List, Optional, Union

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.function_tool import FunctionTool
from google.genai import types
from google.genai.types import SafetySetting

from libs import logger
from models.guard_rail import GuardRail, OutputGuardRail, ToolCallGuardRail

AgentTool = Union[FunctionTool, BaseTool, BaseToolset]


class VertexAIAgent:
    def __init__(
        self,
        model_id: str,
        instructions: str,
        tools: List[AgentTool],
        agent_name: str,
        agent_description: str,

        input_guardrails: Optional[List[GuardRail]] = None,

        output_guardrail: Optional[OutputGuardRail] = None,

        tool_call_guardrail: Optional[ToolCallGuardRail] = None,

        safety_settings: Optional[List[SafetySetting]] = None,

        translate: bool = False,
    ) -> None:
        self._agent: LlmAgent = LlmAgent(
            name=agent_name,
            model=model_id,
            tools=tools,
            instruction=instructions,
            description=agent_description,
            before_model_callback=(
                self._build_before_model_callback(input_guardrails)
                if input_guardrails
                else None
            ),
            after_model_callback=(
                output_guardrail if output_guardrail else None
            ),
            before_tool_callback=(
                tool_call_guardrail if tool_call_guardrail else None
            ),
            generate_content_config=types.GenerateContentConfig(
                safety_settings=safety_settings or []
            ),
        )
        self._translate = translate

    def _build_before_model_callback(
        self, guard_rails: List[GuardRail]
    ) -> callable:

        async def callback(
            callback_context: CallbackContext,
            llm_request: LlmRequest,
        ) -> Optional[LlmResponse]:
            logger.info(
                f"[BeforeModelCallback] agent='{callback_context.agent_name}' "
                f"rails={len(guard_rails)}"
            )

            if (
                not llm_request.contents
                or llm_request.contents[-1].role != "user"
            ):
                return None

            user_content = llm_request.contents[-1]

            for part in user_content.parts or []:
                if not part.text:
                    continue

                current_text = part.text

                outcomes = await asyncio.gather(
                    *[rail.process(current_text) for rail in guard_rails]
                )

                for outcome in outcomes:
                    if outcome.is_blocked:
                        logger.warning(
                            f"[GuardRail BLOCKED] reason='{outcome.blocked_reason}'"
                        )
                        return LlmResponse(
                            content=types.Content(
                                role="model",
                                parts=[
                                    types.Part.from_text(
                                        text=outcome.blocked_reason
                                    )
                                ],
                            )
                        )

                for outcome in outcomes:
                    if outcome.modified_text:
                        current_text = outcome.modified_text

                part.text = current_text

            return None

        return callback