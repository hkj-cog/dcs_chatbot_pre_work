# Output guardrail: blocks LLM responses that drift to the wrong language
import asyncio
from typing import Optional

from agent.translate import Translator
from guardrails.base import OutputGuardRailBase, GuardRailResult
from guardrails.constants import _LANGUAGE_BLOCK_MSG, _LANGUAGE_NOT_SUPPORTED_MSG
from libs.config import get_settings
from libs.logger import GuardRailEvent, log_guardrail_event, logger


class LanguageCheckGuardRail(OutputGuardRailBase):
    """Blocks output in an unexpected language; skips when translation was requested."""

    # Detects output language and blocks if it falls outside the valid set for this session
    async def process(
        self, text: str, session_id: str = "", session_state: Optional[dict] = None
    ) -> GuardRailResult:
        state = session_state or {}
        translate_requested = state.get("translate_requested", False)
        user_language = state.get("user_language")  # None when detection was low-confidence

        if translate_requested:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="LanguageCheckGuardRail",
                layer="output", action="allow",
                session_id=session_id, triggered=False,
                reason="Skipped: translation requested — translation pipeline handles language normalisation",
            ))
            return GuardRailResult(is_blocked=False)

        try:
            output_language, confidence = await asyncio.to_thread(
                Translator.detect_language_with_confidence, text
            )
            s = get_settings()

            # Whitelisted non-English: accept user's language OR a service language.
            # Non-whitelisted or unknown: service language only.
            if (user_language
                    and user_language not in s.supported_output_languages
                    and user_language in s.supported_input_languages):
                valid_languages: set[str] = {user_language} | set(s.supported_output_languages)
            else:
                valid_languages = set(s.supported_output_languages)

            if output_language not in valid_languages:
                if confidence >= s.language_detection_confidence_threshold:
                    # Choose block msg: drift to third language vs. user's unsupported language.
                    is_non_whitelisted = (
                        user_language
                        and output_language == user_language
                        and user_language not in s.supported_input_languages
                    )
                    block_msg = _LANGUAGE_NOT_SUPPORTED_MSG if is_non_whitelisted else _LANGUAGE_BLOCK_MSG
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="LanguageCheckGuardRail",
                        layer="output", action="block",
                        session_id=session_id, triggered=True,
                        reason=(
                            f"Output language {output_language!r} not in valid set {sorted(valid_languages)} "
                            f"(confidence: {confidence:.2f})"
                            + (" — language not in SUPPORTED_INPUT_LANGUAGES" if is_non_whitelisted else "")
                        ),
                    ))
                    return GuardRailResult(is_blocked=True, blocked_reason=block_msg)
                else:
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="LanguageCheckGuardRail",
                        layer="output", action="allow",
                        session_id=session_id, triggered=True,
                        reason=(
                            f"Output language {output_language!r} not in valid set but "
                            f"detection confidence {confidence:.2f} below threshold "
                            f"{s.language_detection_confidence_threshold} — allowing through"
                        ),
                    ))
                    return GuardRailResult(is_blocked=False)
        except Exception as exc:
            logger.error(f"[LanguageCheckGuardRail] Error (fail-open): {exc}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="LanguageCheckGuardRail",
                layer="output", action="allow",
                session_id=session_id, triggered=True,
                reason=f"Language detection failed — fail-open, check skipped: {exc}",
            ))
            return GuardRailResult(is_blocked=False)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="LanguageCheckGuardRail",
            layer="output", action="allow",
            session_id=session_id, triggered=False,
            reason=f"Output language {output_language!r} is within valid set {sorted(valid_languages)}",
        ))
        return GuardRailResult(is_blocked=False)
