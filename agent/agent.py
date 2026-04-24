# VertexAIAgent wrapper — chains input/output guardrails into ADK LlmAgent callbacks
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

from guardrails.base import GuardRail, OutputGuardRailBase
from guardrails.tool import ToolCallGuardRail, ToolResponseGuardRail
from libs import logger

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
        output_guardrails: Optional[List[OutputGuardRailBase]] = None,
        tool_call_guardrail: Optional[ToolCallGuardRail] = None,
        tool_response_guardrail: Optional[ToolResponseGuardRail] = None,
        safety_settings: Optional[List[SafetySetting]] = None,
        translate: bool = False,
    ) -> None:
        # Both guardrail chains are required — fail loudly if either is missing.
        if not input_guardrails:
            raise ValueError(
                "VertexAIAgent requires at least one input guardrail. "
                "The agent must never process unguarded user input."
            )
        if not output_guardrails:
            raise ValueError(
                "VertexAIAgent requires at least one output guardrail. "
                "Citizens must never receive unguarded LLM output."
            )
        if tools and not tool_call_guardrail:
            logger.warning(
                "[VertexAIAgent] Tools registered without a ToolCallGuardRail — "
                "tool calls will be unguarded. Provide tool_call_guardrail for DCS compliance."
            )
        if tools and not tool_response_guardrail:
            logger.warning(
                "[VertexAIAgent] Tools registered without a ToolResponseGuardRail — "
                "tool responses will reach the LLM unguarded. "
                "Provide tool_response_guardrail for DCS compliance."
            )

        # Audit: log the full guardrail chain at startup.
        logger.info(
            f"[VertexAIAgent] Bidirectional guardrail chain registered — "
            f"input={[g.__class__.__name__ for g in input_guardrails]} | "
            f"output={[g.__class__.__name__ for g in output_guardrails]}"
        )

        self._agent: LlmAgent = LlmAgent(
            name=agent_name,
            model=model_id,
            tools=tools,
            instruction=instructions,
            description=agent_description,
            before_model_callback=self._build_before_model_callback(input_guardrails),
            after_model_callback=self._build_after_model_callback(output_guardrails),
            before_tool_callback=tool_call_guardrail or None,
            after_tool_callback=tool_response_guardrail or None,
            generate_content_config=types.GenerateContentConfig(
                safety_settings=safety_settings or []
            ),
        )
        self._tool_response_guardrail = tool_response_guardrail
        self._translate = translate

    # Exposes the underlying ADK LlmAgent for Runner construction
    @property
    def agent(self) -> LlmAgent:
        return self._agent

    # Formats the last N conversation turns into a human-readable string for guardrail context
    @staticmethod
    def _format_history(contents, last_n_turns: int = 5) -> str:
        prior = contents[:-1]
        recent = prior[-(last_n_turns * 2):]
        lines = []
        for content in recent:
            role = "User" if content.role == "user" else "Assistant"
            text = " ".join(
                part.text for part in (content.parts or []) if getattr(part, "text", None)
            ).strip()
            if text:
                lines.append(f"{role}: {text}")
        return "\n".join(lines)

    # Builds the ADK before_model_callback that chains all input guardrails before each LLM call
    def _build_before_model_callback(self, guard_rails: List[GuardRail]) -> callable:
        # Runs each input guardrail in sequence; short-circuits on first block
        async def callback(
            callback_context: CallbackContext,
            llm_request: LlmRequest,
        ) -> Optional[LlmResponse]:
            session_id = getattr(callback_context, "session_id", "") or ""
            logger.info(
                f"[BeforeModelCallback] agent='{callback_context.agent_name}' "
                f"session='{session_id}' rails={len(guard_rails)}"
            )

            if not llm_request.contents or llm_request.contents[-1].role != "user":
                return None

            try:
                session_state = dict(callback_context.state)
            except Exception:
                session_state = {}

            conversation_history = self._format_history(llm_request.contents)
            user_content = llm_request.contents[-1]

            for part in user_content.parts or []:
                if not getattr(part, "text", None):
                    # Skip non-text parts (function calls, tool blobs, etc.)
                    continue
                current_text = part.text
                for rail in guard_rails:
                    outcome = await rail.process(
                        current_text,
                        session_id=session_id,
                        conversation_history=conversation_history,
                        session_state=session_state,
                    )
                    if outcome.is_blocked:
                        logger.warning(
                            f"[InputGuardRail BLOCKED] rail={rail.__class__.__name__} "
                            f"reason='{outcome.blocked_reason[:60]}'"
                        )
                        return LlmResponse(
                            content=types.Content(
                                role="model",
                                parts=[types.Part.from_text(text=outcome.blocked_reason)],
                            )
                        )
                    if outcome.modified_text:
                        current_text = outcome.modified_text
                part.text = current_text

            return None

        return callback

    # Builds the ADK after_model_callback that chains all output guardrails on each LLM response
    def _build_after_model_callback(self, guard_rails: List[OutputGuardRailBase]) -> callable:
        # Runs each output guardrail in sequence; short-circuits on first block
        async def callback(
            callback_context: CallbackContext,
            llm_response: LlmResponse,
        ) -> LlmResponse:
            session_id = getattr(callback_context, "session_id", "") or ""
            try:
                session_state = dict(callback_context.state)
            except Exception:
                session_state = {}

            for candidate in getattr(llm_response, "candidates", []):
                if not (candidate.content and candidate.content.parts):
                    continue
                for part in candidate.content.parts:
                    if not getattr(part, "text", None):
                        # Skip non-text parts — ADK-internal routing signals, not user-visible.
                        continue
                    current_text = part.text
                    blocked = False
                    for rail in guard_rails:
                        outcome = await rail.process(
                            current_text,
                            session_id=session_id,
                            session_state=session_state,
                        )
                        if outcome.is_blocked:
                            logger.warning(
                                f"[OutputGuardRail BLOCKED] rail={rail.__class__.__name__} "
                                f"reason='{outcome.blocked_reason[:60]}'"
                            )
                            part.text = outcome.blocked_reason
                            blocked = True
                            break
                        if outcome.modified_text:
                            current_text = outcome.modified_text
                    if not blocked:
                        part.text = current_text

            return llm_response

        return callback
