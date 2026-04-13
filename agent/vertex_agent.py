from google.adk.agents.llm_agent import Agent
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.tools.function_tool import FunctionTool
from models import VertexAIAgent


def get_current_time(city: str) -> dict[str, str]:
    """Returns the current time in a specified city."""
    return {"status": "success", "city": city, "time": "10:30 AM"}


session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

new_agent = VertexAIAgent(
    model_id="gemini-2.5-flash",
    user_id="user_123",
    instructions="You are a helpful assistant that tells the current time in cities. Use the 'get_current_time' tool for this purpose.",
    tools=[FunctionTool(func=get_current_time)],
    agent_name="root_agent",
    agent_description="Tells the current time in a specified city.",
)

runner = Runner(
    app_name="adk-chatbot",
    agent=new_agent._agent, 
    plugins=[LoggingPlugin()],  # This activates the automatic request/response logs
    session_service=session_service,
    memory_service=memory_service,
)
