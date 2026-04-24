# Input guardrail: 3-tier (hard/soft/warn) fuzzy ban word check with inflection expansion and per-language lists
from typing import List, Optional

from guardrails.base import GuardRail, GuardRailResult
from guardrails.constants import _BAN_WORDS_BLOCK_MSG, _IMPROPER_BLOCK_MSG, _SOFT_BAN_BLOCK_MSG
from guardrails.regex_utils import check_banned_words_tiered, expand_inflections
from libs.logger import GuardRailEvent, log_guardrail_event


class BanWordsInputGuardRail(GuardRail):
    """Three-tier fuzzy ban-word check on user input (hard/soft/warn). Inflections pre-expanded at init."""

    def __init__(
        self,
        banned_words: Optional[List[str]] = None,
        banned_words_soft: Optional[List[str]] = None,
        banned_words_warn: Optional[List[str]] = None,
        context_allowlist: Optional[List[str]] = None,
        threshold: Optional[int] = None,
    ) -> None:
        from libs.config import get_settings
        s = get_settings()
        self._threshold = threshold if threshold is not None else s.ban_word_fuzzy_threshold

        raw_hard = [w.lower() for w in (banned_words or s.banned_words) if w.strip()]
        raw_soft = [w.lower() for w in (banned_words_soft or s.banned_words_soft) if w.strip()]
        raw_warn = [w.lower() for w in (banned_words_warn or s.banned_words_warn) if w.strip()]

        self._hard = expand_inflections(raw_hard)
        self._soft = expand_inflections(raw_soft)
        self._warn = expand_inflections(raw_warn)
        self._context_allowlist = context_allowlist or s.ban_word_context_allowlist

        # Per-language lists (no inflection expansion — English suffixes don't generalise).
        self._lang_hard: dict = {
            lang: [w.lower() for w in words if w.strip()]
            for lang, words in s.banned_words_by_language.items()
        }
        self._lang_soft: dict = {
            lang: [w.lower() for w in words if w.strip()]
            for lang, words in s.banned_words_soft_by_language.items()
        }
        self._lang_warn: dict = {
            lang: [w.lower() for w in words if w.strip()]
            for lang, words in s.banned_words_warn_by_language.items()
        }

    # Runs the 3-tier ban-word check on user input, merging per-language lists when available
    async def process(
        self,
        text: str,
        session_id: str = "",
        conversation_history: str = "",
        session_state: Optional[dict] = None,
    ) -> GuardRailResult:
        user_language = (session_state or {}).get("user_language")
        if user_language:
            effective_hard = self._hard + self._lang_hard.get(user_language, [])
            effective_soft = self._soft + self._lang_soft.get(user_language, [])
            effective_warn = self._warn + self._lang_warn.get(user_language, [])
        else:
            effective_hard, effective_soft, effective_warn = self._hard, self._soft, self._warn

        if not effective_hard and not effective_soft and not effective_warn:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="BanWordsInputGuardRail",
                layer="input", action="allow",
                session_id=session_id, triggered=False,
                reason="No banned words configured",
            ))
            return GuardRailResult(is_blocked=False)

        tier, matched = check_banned_words_tiered(
            text, effective_hard, effective_soft, effective_warn,
            self._context_allowlist, self._threshold,
        )

        if tier == "hard":
            log_guardrail_event(GuardRailEvent(
                guardrail_name="BanWordsInputGuardRail",
                layer="input", action="block",
                session_id=session_id, triggered=True,
                reason=f"Hard-banned words in user input: {', '.join(matched)}",
                snippet=text[:80],
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_IMPROPER_BLOCK_MSG)

        if tier == "soft":
            log_guardrail_event(GuardRailEvent(
                guardrail_name="BanWordsInputGuardRail",
                layer="input", action="block",
                session_id=session_id, triggered=True,
                reason=f"Soft-banned words in user input: {', '.join(matched)}",
                snippet=text[:80],
            ))
            return GuardRailResult(is_blocked=True, blocked_reason=_SOFT_BAN_BLOCK_MSG)

        if tier == "warn":
            log_guardrail_event(GuardRailEvent(
                guardrail_name="BanWordsInputGuardRail",
                layer="input", action="allow",
                session_id=session_id, triggered=True,
                reason=f"Warn-tier words detected (allowed through): {', '.join(matched)}",
            ))
            return GuardRailResult(is_blocked=False)

        log_guardrail_event(GuardRailEvent(
            guardrail_name="BanWordsInputGuardRail",
            layer="input", action="allow",
            session_id=session_id, triggered=False,
        ))
        return GuardRailResult(is_blocked=False)
