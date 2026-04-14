import os

from google.adk.memory import InMemoryMemoryService
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import VertexAiSearchTool
from google.genai import types

from agent.prompt import INSTRUCTIONS
from models import VertexAIAgent
from models.guard_rail import (
    DateTimeInjectorGuardRail,
    JailbreakGuardRail,
    OutputGuardRail,
    ProfanityGuardRail,
    ToolCallGuardRail,
)

_datastore_id = os.environ.get("DATASTORE_ID", "")
_model_id = os.environ.get("MODEL_ID", "gemini-2.5-flash")

session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

_agent_wrapper = VertexAIAgent(
    model_id=_model_id,
    instructions=INSTRUCTIONS.replace("{DATASTORE_ID}", _datastore_id),
    tools=[VertexAiSearchTool(data_store_id=_datastore_id, max_results=5)],
    agent_name="adk-chatbot",
    agent_description="Helps users with questions by searching the document datastore.",

    input_guardrails=[
        DateTimeInjectorGuardRail(),        # prepend current datetime to user text
        JailbreakGuardRail(),               # block prompt-injection attempts
        ProfanityGuardRail(threshold=0.5),  # block profane content via Google NLP
    ],

    output_guardrail=OutputGuardRail(),

    tool_call_guardrail=ToolCallGuardRail(),

    safety_settings=[
        types.SafetySetting(
            method=types.HarmBlockMethod.PROBABILITY,
            category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
            threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        ),
        types.SafetySetting(
            method=types.HarmBlockMethod.PROBABILITY,
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        ),
        types.SafetySetting(
            method=types.HarmBlockMethod.PROBABILITY,
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        ),
        types.SafetySetting(
            method=types.HarmBlockMethod.PROBABILITY,
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        ),
        types.SafetySetting(
            method=types.HarmBlockMethod.PROBABILITY,
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        ),
    ],
)

runner = Runner(
    app_name="adk-chatbot",
    agent=_agent_wrapper._agent,
    plugins=[LoggingPlugin()],
    session_service=session_service,
    memory_service=memory_service,
)