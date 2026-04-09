from typing import Callable, Union
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai.types import SafetySetting

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
        input_guardrails: list[InputOutputCallback] | None = None,
        output_guardrails: list[InputOutputCallback] | None = None,
        before_tool_guardrails: list[ToolCallback] | None = None,
        after_tool_guardrails: list[ToolAfterCallback] | None = None,
        safety_settings: list[SafetySetting] | None = None,
        translate: bool = False,
    ) -> None:
        self._agent: LlmAgent = LlmAgent(
            name=agent_name,
            model=model_id,
            tools=tools,
            instruction=instructions,
            description=agent_description,
            before_model_callback=input_guardrails,
            after_model_callback=output_guardrails,
            before_tool_callback=before_tool_guardrails,
            after_agent_callback=after_tool_guardrails,
            generate_content_config=types.GenerateContentConfig(
                safety_settings=safety_settings
            ),
        )
        self._scorer = ConfidenceScorer(
            llm=model_id, location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        )
        self._translate = translate
        # Initialize an in-memory session service to manage conversation states
        # across multiple interactions without needing a database.
        self._in_memory_session_service: InMemorySessionService = (
            InMemorySessionService()
        )
        # Initialize the runner responsible for executing the agent's logic.
        # It links the agent to the session service.
        self._runner: Runner = Runner(
            agent=self._agent,
            app_name=agent_name,
            session_service=self._in_memory_session_service,
        )
        # Create and store a new memory session for the given user.
        # asyncio.run is used here to synchronously run the async `create_session` call
        # during the `__init__` method, which is typically synchronous.
        self._memory_session = asyncio.run(
            self._in_memory_session_service.create_session(
                app_name=agent_name, user_id=user_id
            )
        )
