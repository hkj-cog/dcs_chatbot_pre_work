import asyncio
from datetime import datetime
from typing import Callable, Optional, Union
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
from opentelemetry import trace
from libs import logger
from models.guard_rail import GuardRail, GuardRailResult
from models.injectors import INJECTOR_REGISTRY, BaseInjector, InjectionContext

from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

from monitoring.gemini_eval import GeminiADKEvaluator

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
        model_id: str, # user_id: str,
        instructions: str,
        tools: list[AgentTool],
        agent_name: str,
        agent_description: str,
        agent_input_guardrails: list[GuardRail] | None,
        agent_input_injectors: list[BaseInjector] | None,
        safety_settings: list[SafetySetting] | None = None,
        translate: bool = False,
        evaluator: GeminiADKEvaluator | None = GeminiADKEvaluator("", "") 
    ) -> None:
        self._agent: LlmAgent = LlmAgent(
            name=agent_name,
            model=model_id,
            tools=tools,
            instruction=instructions,
            description=agent_description,
            before_agent_callback= self.__before_agent_callback(agent_input_guardrails, agent_input_injectors),
            generate_content_config=types.GenerateContentConfig(
                safety_settings=safety_settings
            ),
            after_agent_callback=self.__trigger_eval(evaluator)
        )

        self._translate = translate
        self._in_memory_session_service: InMemorySessionService = (
            InMemorySessionService()
        )
        # tracer_provider = register(
        #     project_name="dcs-chat",
        #     batch=False,  # Use sync export because Agent Engine pauses CPU after requests
        #     set_global_tracer_provider=False,  # Required: avoids conflict with Agent Engine's global provider
        # )
        # GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

    
    def __trigger_eval(self, evaluator: GeminiADKEvaluator | None):
        if evaluator is None:
            async def empty_callback(callback_context: CallbackContext) -> types.Content | None:
                return None
            return empty_callback
        
        async def modify_span_after_agent(callback_context: CallbackContext) -> Optional[types.Content]:
            # Extract user input
            user_input: str = ""
            if (
                callback_context.user_content
                and callback_context.user_content.parts
            ):
                user_input = " ".join(
                    part.text
                    for part in callback_context.user_content.parts
                    if hasattr(part, "text") and part.text
                ).strip()


            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                logger.info(f"[After Agent Callback] Setting eval attributes: input={user_input}, invocation_id={callback_context.invocation_id}")
                current_span.set_attribute("eval.input", user_input)
                current_span.set_attribute(
                    "eval.invocation_id", 
                    callback_context.invocation_id or ""
                )

            return None
        
        return modify_span_after_agent
     

    def __before_agent_callback(self, guard_rails: list[GuardRail] | None, input_injectors: list[BaseInjector]| None):

        if guard_rails is None or len(guard_rails) == 0 or input_injectors is None or len(input_injectors) == 0:
            async def empty_callback(callback_context: CallbackContext) -> types.Content | None:
                return None
            return empty_callback

        async def callback(callback_context: CallbackContext) -> types.Content | None:
            session = callback_context.session

            # --- NEW: INJECT SESSION DATA INTO TRACE ---
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                # Set Session ID
                current_span.set_attribute("session.id", session.id)
                
                # Get created_on from state with fallback
                state_dict = callback_context.state.to_dict() if hasattr(callback_context.state, "to_dict") else callback_context.state
                raw_date = state_dict.get("metadata", {}).get("created_on")
                
                if isinstance(raw_date, datetime):
                    iso_date = raw_date.isoformat()
                elif isinstance(raw_date, str):
                    iso_date = raw_date
                else:
                    iso_date = datetime(1970, 1, 1).isoformat()
                    
                current_span.set_attribute("session.created_on", iso_date)
            # ------------------------------------------
            
            # 1. Find the most recent user event (iterating backwards)
            for event in reversed(session.events):
                if event.author == "user" and event.content and event.content.parts:
                    
                    # 2. Extract original text
                    original_text = " ".join([p.text for p in event.content.parts if p.text])

                    tasks = [rail.process(original_text) for rail in guard_rails]
                    outcomes = await asyncio.gather(*tasks)

                    # 3. Evaluation Logic
                    # Check if any rail wants to BLOCK
                    for outcome in outcomes:
                        if outcome.is_blocked:
                            print(f"[Guard Rail Blocked]: {outcome.blocked_reason}")
                            return types.Content(
                                parts=[types.Part(text=f"Agent skipped by before_agent_callback due to state.")],
                                role="model" # Assign model role to the overriding response
                            )

                    
                    # 3. Run the Dynamic Injection Pipeline
                    ctx = InjectionContext(original_text=original_text)
                    for instance in input_injectors:
                        instance.inject(ctx)

                    context_str = "\n".join(ctx.lines)
                    modified_text = (
                        "--- SYSTEM CONTEXT\n"
                        f"{context_str}\n"
                        "---\n"
                        f"{original_text}\n"
                        "---"
                    )
                    
                 
                    logger.info(f"[Before Agent Callback] Modified Text: {modified_text}")
                    # 5. Update the event directly in the session
                    # We clear the old parts and add the single modified part
                    event.content.parts[:] = [types.Part(text=modified_text)]
                    
                    # Stop after fixing the most recent user input
                    break
                    
            # Return None to allow the agent to proceed with the modified session

            return None
    
        return callback

