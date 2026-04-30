# Tool guardrail: restricts queries to vertex_ai_search, blocks short and banned search terms
from typing import List, Optional

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from guardrails.utils import matches_banned_word
from libs.logger import GuardRailEvent, log_guardrail_event, logger

_ALLOWED_TOOLS = {"vertex_ai_search"}
_DEFAULT_BLOCKED_QUERY_TERMS = ["financial records", "personal employee data"]


class ToolCallGuardRail:
    """Validates tool calls: only vertex_ai_search allowed, queries ≥ 2 words, no blocked terms."""

    def __init__(
        self,
        blocked_query_terms: Optional[List[str]] = None,
        threshold: int = 85,
    ) -> None:
        # Normalises blocked query terms for fuzzy matching at call time.
        raw = blocked_query_terms if blocked_query_terms is not None else _DEFAULT_BLOCKED_QUERY_TERMS
        self._blocked = [t.lower() for t in raw if t.strip()]
        self._threshold = threshold

    async def __call__(
        self,
        tool: BaseTool,
        tool_args: dict,
        tool_context: ToolContext,
    ) -> Optional[dict]:
        # Validates tool name, query length, and blocked terms before the ADK executes the tool.
        tool_name = tool.name if hasattr(tool, "name") else str(tool)
        session_id = ""
        try:
            session_id = tool_context._invocation_context.session.id or ""
        except AttributeError:
            logger.debug("[ToolCallGuardRail] Could not read session_id — events will have empty session_id")

        logger.info(f"[ToolCallGuardRail] tool='{tool_name}' args={tool_args}")

        if tool_name not in _ALLOWED_TOOLS:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="ToolCallGuardRail",
                layer="input", action="block",
                session_id=session_id, triggered=True,
                reason=f"Unknown tool blocked: '{tool_name}'",
            ))
            return {"error": f"Tool '{tool_name}' is not permitted."}

        if "query" in tool_args:
            query = tool_args["query"].lower().strip()

            if len(query.split()) < 2:
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="ToolCallGuardRail",
                    layer="input", action="block",
                    session_id=session_id, triggered=True,
                    reason=f"Single-word query blocked: '{query}'",
                ))
                return {"error": "Query is too short. Please provide more context."}

            matched_terms = [
                term for term in self._blocked
                if matches_banned_word(term, query, self._threshold)
            ]
            if matched_terms:
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="ToolCallGuardRail",
                    layer="input", action="block",
                    session_id=session_id, triggered=True,
                    reason=f"Restricted query terms blocked (fuzzy): {', '.join(matched_terms)}",
                    snippet=query[:80],
                ))
                return {"error": "Query contains restricted terms."}

        log_guardrail_event(GuardRailEvent(
            guardrail_name="ToolCallGuardRail",
            layer="input", action="allow",
            session_id=session_id, triggered=False,
        ))
        return None
