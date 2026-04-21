from google.adk.agents.llm_agent import Agent
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.tools.function_tool import FunctionTool
from models import VertexAIAgent
from models.guard_rail import ProfanityGuardRail
from models.injectors import DateTimeInjector, LocationInjector
from datetime import datetime
from zoneinfo import ZoneInfo
from google.adk.tools.google_search_tool import google_search

# Maps common city names to their IANA timezone identifiers
CITY_TIMEZONES: dict[str, str] = {
    "new york":     "America/New_York",
    "los angeles":  "America/Los_Angeles",
    "chicago":      "America/Chicago",
    "london":       "Europe/London",
    "paris":        "Europe/Paris",
    "berlin":       "Europe/Berlin",
    "dubai":        "Asia/Dubai",
    "moscow":       "Europe/Moscow",
    "mumbai":       "Asia/Kolkata",
    "delhi":        "Asia/Kolkata",
    "singapore":    "Asia/Singapore",
    "hong kong":    "Asia/Hong_Kong",
    "tokyo":        "Asia/Tokyo",
    "sydney":       "Australia/Sydney",
    "auckland":     "Pacific/Auckland",
    "são paulo":    "America/Sao_Paulo",
    "mexico city":  "America/Mexico_City",
    "toronto":      "America/Toronto",
    "cairo":        "Africa/Cairo",
    "johannesburg": "Africa/Johannesburg",
}

def get_current_time(city: str) -> dict[str, str]:
    """Returns the current time in a specified city."""
    timezone_id = CITY_TIMEZONES.get(city.lower())

    if not timezone_id:
        return {
            "status": "error",
            "city": city,
            "message": f"Unknown city '{city}'. Please provide a recognised city name.",
        }

    current_time = datetime.now(ZoneInfo(timezone_id))
    return {
        "status": "success",
        "city": city,
        "timezone": timezone_id,
        "time": current_time.strftime("%I:%M %p"),       # e.g. 10:30 AM
        "datetime": current_time.strftime("%Y-%m-%d %H:%M:%S %Z"),  # e.g. 2026-04-17 10:30:00 AEST
    }


session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

new_agent = VertexAIAgent(
    model_id="gemini-2.5-flash",
    instructions="Answer questions using Google Search when needed. Always cite sources.",
    tools=[google_search],
    agent_name="root_agent",
    agent_description="Tells the current time in a specified city.",
    agent_input_guardrails= [ProfanityGuardRail()],
    agent_input_injectors=[DateTimeInjector(), LocationInjector()]
)

runner = Runner(
    app_name="adk-chatbot",
    agent=new_agent._agent, 
    plugins=[LoggingPlugin()],  # This activates the automatic request/response logs
    session_service=session_service,
    memory_service=memory_service,
)
