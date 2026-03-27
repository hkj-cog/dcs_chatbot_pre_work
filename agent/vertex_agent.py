from google.adk.agents.llm_agent import Agent
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner


def get_current_time(city: str) -> dict[str, str]:
    """Returns the current time in a specified city."""
    return {"status": "success", "city": city, "time": "10:30 AM"}


session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

root_agent = Agent(
    model="gemini-2.5-flash",  # Note: Using available model versions
    name="root_agent",
    description="Tells the current time in a specified city.",
    instruction="You are a helpful assistant that tells the current time in cities. Use the 'get_current_time' tool for this purpose.",
    tools=[get_current_time],
)


runner = Runner(
    app_name="adk-chatbot",
    agent=root_agent,
    plugins=[LoggingPlugin()],  # This activates the automatic request/response logs
    session_service=session_service,
    memory_service=memory_service,
)
