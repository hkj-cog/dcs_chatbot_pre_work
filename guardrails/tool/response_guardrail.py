# Tool guardrail: scans datastore documents for secrets, jailbreak, PII, banned words, and moderation
import asyncio
from typing import Any, List, Optional

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from guardrails.moderation_utils import MODERATION_CATEGORIES_INPUT, check_moderation_categories
from guardrails.regex_utils import (
    JAILBREAK_REGEX_PATTERNS,
    normalise,
    check_banned_words,
    extract_tool_response_text,
    redact_secrets,
    redact_tool_response,
)
from libs.logger import GuardRailEvent, log_guardrail_event, logger

_TOOL_RESPONSE_BLOCKED = {"error": "Tool response blocked by content guardrail."}


class ToolResponseGuardRail:
    """Guards retrieved documents before they reach the LLM: secrets, jailbreak, DLP, banned words, moderation."""

    def __init__(
        self,
        banned_words: Optional[List[str]] = None,
        threshold: Optional[int] = None,
        dlp=None,
    ) -> None:
        # Stores banned words, fuzzy threshold, and optional DLP client for tool response scanning.
        self._banned = [w.lower() for w in (banned_words or []) if w.strip()]
        if threshold is not None:
            self._threshold = threshold
        else:
            from libs.config import get_settings
            self._threshold = get_settings().ban_word_fuzzy_threshold
        self._dlp = dlp

    async def __call__(
        self,
        tool: BaseTool,
        tool_args: dict,
        tool_context: ToolContext,
        tool_response: dict,
    ) -> Optional[dict]:
        # Scans the tool response for secrets, jailbreak patterns, PII, banned words, and moderation categories.
        session_id = ""
        try:
            session_id = tool_context._invocation_context.session.id or ""
        except AttributeError:
            logger.debug("[ToolResponseGuardRail] Could not read session_id from tool_context")

        response_text = extract_tool_response_text(tool_response)
        if not response_text.strip():
            return None

        redacted_response = tool_response
        _, found_secrets = redact_secrets(response_text)
        if found_secrets:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="ToolResponseGuardRail",
                layer="tool", action="modify",
                session_id=session_id, triggered=True,
                reason=f"Secrets redacted from tool response: {', '.join(found_secrets)}",
            ))
            redacted_response = redact_tool_response(tool_response)
            response_text = extract_tool_response_text(redacted_response)

        # Two-pass jailbreak check: raw text then leet/symbol-normalised (catches poisoned datastore docs).
        _jailbreak_hit = None
        for pattern in JAILBREAK_REGEX_PATTERNS:
            if pattern.search(response_text):
                _jailbreak_hit = pattern
                break
        if _jailbreak_hit is None:
            response_norm = normalise(response_text)
            if response_norm != response_text.lower():
                for pattern in JAILBREAK_REGEX_PATTERNS:
                    if pattern.search(response_norm):
                        _jailbreak_hit = pattern
                        break
        if _jailbreak_hit is not None:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="ToolResponseGuardRail",
                layer="tool", action="block",
                session_id=session_id, triggered=True,
                reason=f"Prompt-injection pattern in tool response: {_jailbreak_hit.pattern[:80]}",
                # snippet omitted: DLP hasn't run yet — document text may contain PII
            ))
            return _TOOL_RESPONSE_BLOCKED

        dlp_modified = False
        if self._dlp is not None:
            try:
                dlp_check = await asyncio.to_thread(self._dlp.invoke, response_text)
                if dlp_check != response_text:
                    redacted_response = await _redact_fields_with_dlp(redacted_response, self._dlp)
                    response_text = extract_tool_response_text(redacted_response)
                    dlp_modified = True
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="ToolResponseGuardRail",
                        layer="tool", action="modify",
                        session_id=session_id, triggered=True,
                        reason="PII redacted from tool response via Cloud DLP",
                        snippet=response_text[:80],
                    ))
            except Exception as exc:
                logger.error(f"[ToolResponseGuardRail] DLP error (fail-closed): {exc}")
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="ToolResponseGuardRail",
                    layer="tool", action="block",
                    session_id=session_id, triggered=True,
                    reason=f"DLP unavailable — blocking tool response to maintain Privacy Act compliance: {exc}",
                ))
                return _TOOL_RESPONSE_BLOCKED

        if self._banned:
            matched = check_banned_words(response_text, self._banned, self._threshold)
            if matched:
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="ToolResponseGuardRail",
                    layer="tool", action="block",
                    session_id=session_id, triggered=True,
                    reason=f"Banned words in tool response (fuzzy): {', '.join(matched)}",
                    snippet=response_text[:80],
                ))
                return _TOOL_RESPONSE_BLOCKED

        try:
            triggered = await asyncio.to_thread(
                check_moderation_categories, response_text, MODERATION_CATEGORIES_INPUT
            )
            if triggered:
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="ToolResponseGuardRail",
                    layer="tool", action="block",
                    session_id=session_id, triggered=True,
                    reason=f"Tool response blocked — moderation categories: {', '.join(triggered)}",
                    snippet=response_text[:80],
                ))
                return _TOOL_RESPONSE_BLOCKED
        except Exception as exc:
            logger.error(f"[ToolResponseGuardRail] Moderation API error (fail-closed): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="ToolResponseGuardRail",
                layer="tool", action="block",
                session_id=session_id, triggered=True,
                reason=f"Moderation API unavailable — blocking tool response to maintain safety: {exc}",
            ))
            return _TOOL_RESPONSE_BLOCKED

        log_guardrail_event(GuardRailEvent(
            guardrail_name="ToolResponseGuardRail",
            layer="tool", action="allow",
            session_id=session_id, triggered=False,
        ))
        return redacted_response if (found_secrets or dlp_modified) else None


async def _redact_fields_with_dlp(obj: Any, dlp) -> Any:
    """Recursively redacts PII from all string fields in a tool response using Cloud DLP."""
    if isinstance(obj, str):
        return await asyncio.to_thread(dlp.invoke, obj)
    if isinstance(obj, dict):
        return {k: await _redact_fields_with_dlp(v, dlp) for k, v in obj.items()}
    if isinstance(obj, list):
        return [await _redact_fields_with_dlp(i, dlp) for i in obj]
    return obj
