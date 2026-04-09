import logging
import os
import re
from datetime import datetime

from google.adk.models.llm_response import LlmResponse
from google.genai import types
from guardrails import Guard
from guardrails.errors import ValidationError
from guardrails.hub import DetectJailbreak

# Configure logging for better visibility
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

api_key = os.getenv("GUARDRAILS_API_KEY")
logger.info(f"api_key: {api_key}")
# Setup Guard
guard = Guard().use(DetectJailbreak)


async def inject_date_time_context(llm_request, callback_context):
    now = datetime.now()
    llm_request.append_instructions(
        [f"Todays date and time is: {now.strftime("%Y-%m-%d %H:%M:%S")}"]
    )
    return None


# --- Guardrail Functions ---
async def input_guardrail(llm_request, callback_context):
    """
    Guardrail to preprocess the LLM request (user input).
    - Checks for sensitive keywords or disallowed topics in the user's message.
    - Can be extended to sanitize input, detect prompt injection, etc.
    """
    query_text = ""

    # Safely access content parts, as structure might vary
    if (
        hasattr(llm_request, "contents")
        and llm_request.contents
        and llm_request.contents[-1].parts
    ):
        for part in llm_request.contents[-1].parts:
            if hasattr(part, "text") and part.text:
                query_text = part.text
                break  # Assuming the first text part is the primary query

    logger.info(
        f"Input Guardrail: Processing query '{query_text}' (Context: {callback_context.agent_name if hasattr(callback_context, 'agent_name') else 'N/A'})"
    )

    try:
        vallidationOutcome = guard.validate(query_text)
        print(f"vallidationOutcome:{vallidationOutcome}")
        if vallidationOutcome.validation_passed == False:
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text="I'm designed to follow my instructions carefully. Please rephrase your query if you intended something specific."
                        )
                    ],
                )
            )
    except ValidationError as e:
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        text="I'm designed to follow my instructions carefully. Please rephrase your query if you intended something specific."
                    )
                ],
            )
        )
    return None


async def output_guardrail(llm_response, callback_context):
    """
    Guardrail to post-process the LLM response before sending to the user.
    - Filters out sensitive information from the response.
    - Ensures the response is helpful and within scope.
    """

    response_text = ""
    # Safely access content parts, as structure might vary
    if (
        hasattr(llm_response, "candidates")
        and llm_response.candidates
        and llm_response.candidates[-1].content
        and llm_response.candidates[-1].content.parts
    ):
        for part in llm_response.candidates[-1].content.parts:
            if hasattr(part, "text") and part.text:
                response_text = part.text
                break

    logger.info(
        f"Output Guardrail: Processing response '{response_text[:50]}...' (Context: {callback_context.agent_name if hasattr(callback_context, 'agent_name') else 'N/A'})"
    )

    #  Redact sensitive numbers (simple example, expand as needed)
    redacted_response_text = re.sub(
        r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b",
        "[REDACTED_CARD_NUMBER]",
        response_text,
    )
    if redacted_response_text != response_text:
        logger.warning("Output Guardrail: Redacted sensitive number from response.")
        response_text = redacted_response_text
        # Update the response content if it was modified
        if (
            hasattr(llm_response, "candidates")
            and llm_response.candidates
            and llm_response.candidates[-1].content
        ):
            llm_response.candidates[-1].content.parts = [types.Part(text=response_text)]

    return llm_response


# --- TOOL CALL GUARDRAIL ---
async def tool_call_guardrail(
    tool_name: str, tool_args: dict, callback_context
) -> bool:
    """
    Guardrail to control tool execution.
    Returns True to allow the tool call, False to block it.
    """
    logger.info(
        f"Tool Call Guardrail: Checking tool '{tool_name}' with args {tool_args} (Context: {callback_context.agent_name if hasattr(callback_context, 'agent_name') else 'N/A'})"
    )

    # Example 1: Only allow VertexAiSearchTool
    if tool_name != "vertex_ai_search":
        logger.warning(f"Tool Call Guardrail: Blocked unknown tool '{tool_name}'.")
        return False

    # Example 2: Prevent search queries that are too broad or sensitive (simple example)
    if tool_name == "vertex_ai_search" and "query" in tool_args:
        search_query = tool_args["query"].lower()
        if len(search_query.split()) < 2:
            logger.warning(
                f"Tool Call Guardrail: Blocked single-word search query: '{search_query}'."
            )
            return False
        if (
            "financial records" in search_query
            or "personal employee data" in search_query
        ):
            logger.warning(
                f"Tool Call Guardrail: Blocked sensitive search query: '{search_query}'."
            )
            return False

    return True
