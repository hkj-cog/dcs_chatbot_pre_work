import os

from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.tools import VertexAiSearchTool
from google.genai import types

from agent.guardrails import output_guardrail, tool_call_guardrail
from agent.prompt import INSTRUCTIONS
from agent.utils import get_gcp_project_id
from models import VertexAIAgent
from models.guard_rail import (
    DateTimeInjectorGuardRail,
    JailbreakGuardRail,
    ProfanityGuardRail,
)

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
_datastore_id = os.environ.get("DATASTORE_ID", "")
_model_id = os.environ.get("MODEL_ID", "gemini-2.5-flash")

# ---------------------------------------------------------------------------
# Session & memory services — module-level singletons
# ---------------------------------------------------------------------------
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
new_agent = VertexAIAgent(
    model_id=_model_id,
    user_id="user_123",
    instructions=INSTRUCTIONS.replace("{DATASTORE_ID}", _datastore_id),
    tools=[VertexAiSearchTool(data_store_id=_datastore_id, max_results=5)],
    agent_name="root_agent",
    agent_description="Helps users with questions by searching the document datastore.",

    # ── Guardrail: input (GuardRail ABC — via __before_model_callback)
    # Runs in order: datetime injection → jailbreak detection → profanity check
    input_guardrails=[
        DateTimeInjectorGuardRail(),       # injects current datetime into user text
        JailbreakGuardRail(),              # blocks jailbreak attempts (guardrails-ai)
        ProfanityGuardRail(threshold=0.5), # blocks profanity (Google Cloud NLP)
    ],

    # ── Guardrail: output (ADK after_model_callback)
    # Redacts 16-digit card numbers from LLM responses
    output_guardrails=[output_guardrail],

    # ── Guardrail: tool call (ADK before_tool_callback)
    # Whitelists vertex_ai_search, blocks unsafe/sensitive queries
    before_tool_guardrails=[tool_call_guardrail],

    # ── Guardrail: Gemini model-level harm filters
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

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
runner = Runner(
    app_name="adk-chatbot",
    agent=new_agent._agent,
    plugins=[LoggingPlugin()],
    session_service=session_service,
    memory_service=memory_service,
)