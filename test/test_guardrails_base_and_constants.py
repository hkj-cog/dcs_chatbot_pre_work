"""Tests for guardrails/base.py and guardrails/constants.py."""

import pytest
from guardrails.base import GuardRailResult, GuardRail, OutputGuardRailBase
from guardrails.constants import (
    ALL_BLOCK_MESSAGES,
    SECURITY_BLOCK_MESSAGES,
    NON_DISABLEABLE_GUARDRAILS,
    _CRISIS_SUPPORT_MSG,
    _SECRETS_BLOCK_MSG,
    _JAILBREAK_BLOCK_MSG,
    _INPUT_TOO_LONG_MSG,
    _OUTPUT_TOO_LONG_MSG,
    _GROUNDEDNESS_BLOCK_MSG,
)


# ─── GuardRailResult ──────────────────────────────────────────────────────────

class TestGuardRailResult:
    def test_blocked_result(self):
        r = GuardRailResult(is_blocked=True, blocked_reason="reason")
        assert r.is_blocked is True
        assert r.blocked_reason == "reason"
        assert r.modified_text == ""

    def test_allowed_result(self):
        r = GuardRailResult(is_blocked=False)
        assert r.is_blocked is False
        assert r.blocked_reason == ""
        assert r.modified_text == ""

    def test_modified_result(self):
        r = GuardRailResult(is_blocked=False, modified_text="rewritten text")
        assert r.is_blocked is False
        assert r.modified_text == "rewritten text"

    def test_all_fields_set(self):
        r = GuardRailResult(is_blocked=True, blocked_reason="msg", modified_text="mod")
        assert r.is_blocked
        assert r.blocked_reason == "msg"
        assert r.modified_text == "mod"

    def test_default_modified_text_is_empty(self):
        r = GuardRailResult(is_blocked=True, blocked_reason="x")
        assert r.modified_text == ""

    def test_default_blocked_reason_is_empty(self):
        r = GuardRailResult(is_blocked=False)
        assert r.blocked_reason == ""


# ─── Abstract classes ─────────────────────────────────────────────────────────

class TestAbstractClasses:
    def test_guardrail_is_abstract(self):
        with pytest.raises(TypeError):
            GuardRail()  # type: ignore

    def test_output_guardrail_base_is_abstract(self):
        with pytest.raises(TypeError):
            OutputGuardRailBase()  # type: ignore

    def test_guardrail_subclass_must_implement_process(self):
        class NoProcess(GuardRail):
            pass
        with pytest.raises(TypeError):
            NoProcess()  # type: ignore

    def test_valid_guardrail_subclass(self):
        class Valid(GuardRail):
            async def process(self, text, session_id="", conversation_history=""):
                return GuardRailResult(is_blocked=False)
        gr = Valid()
        assert gr is not None

    def test_valid_output_guardrail_subclass(self):
        class Valid(OutputGuardRailBase):
            async def process(self, text, session_id="", session_state=None):
                return GuardRailResult(is_blocked=False)
        gr = Valid()
        assert gr is not None


# ─── Constants: ALL_BLOCK_MESSAGES ───────────────────────────────────────────

class TestAllBlockMessages:
    def test_is_frozenset(self):
        assert isinstance(ALL_BLOCK_MESSAGES, frozenset)

    def test_contains_secrets_message(self):
        assert _SECRETS_BLOCK_MSG in ALL_BLOCK_MESSAGES

    def test_contains_jailbreak_message(self):
        assert _JAILBREAK_BLOCK_MSG in ALL_BLOCK_MESSAGES

    def test_contains_crisis_message(self):
        assert _CRISIS_SUPPORT_MSG in ALL_BLOCK_MESSAGES

    def test_contains_input_too_long(self):
        assert _INPUT_TOO_LONG_MSG in ALL_BLOCK_MESSAGES

    def test_contains_output_too_long(self):
        assert _OUTPUT_TOO_LONG_MSG in ALL_BLOCK_MESSAGES

    def test_contains_groundedness_block(self):
        assert _GROUNDEDNESS_BLOCK_MSG in ALL_BLOCK_MESSAGES

    def test_non_empty(self):
        assert len(ALL_BLOCK_MESSAGES) > 0

    def test_all_strings(self):
        assert all(isinstance(m, str) for m in ALL_BLOCK_MESSAGES)


# ─── Constants: SECURITY_BLOCK_MESSAGES ──────────────────────────────────────

class TestSecurityBlockMessages:
    def test_is_frozenset(self):
        assert isinstance(SECURITY_BLOCK_MESSAGES, frozenset)

    def test_is_subset_of_all_block_messages(self):
        assert SECURITY_BLOCK_MESSAGES.issubset(ALL_BLOCK_MESSAGES)

    def test_crisis_message_excluded(self):
        # Crisis support message is NOT a security block — person in distress is not an attacker
        assert _CRISIS_SUPPORT_MSG not in SECURITY_BLOCK_MESSAGES

    def test_secrets_message_included(self):
        assert _SECRETS_BLOCK_MSG in SECURITY_BLOCK_MESSAGES

    def test_jailbreak_message_included(self):
        assert _JAILBREAK_BLOCK_MSG in SECURITY_BLOCK_MESSAGES

    def test_non_empty(self):
        assert len(SECURITY_BLOCK_MESSAGES) > 0


# ─── Constants: NON_DISABLEABLE_GUARDRAILS ───────────────────────────────────

class TestNonDisableableGuardrails:
    def test_is_frozenset(self):
        assert isinstance(NON_DISABLEABLE_GUARDRAILS, frozenset)

    def test_contains_secrets_input(self):
        assert "SecretsInputGuardRail" in NON_DISABLEABLE_GUARDRAILS

    def test_contains_secrets_output(self):
        assert "SecretsOutputGuardRail" in NON_DISABLEABLE_GUARDRAILS

    def test_contains_jailbreak(self):
        assert "JailbreakGuardRail" in NON_DISABLEABLE_GUARDRAILS

    def test_contains_dlp_output(self):
        assert "DlpOutputGuardRail" in NON_DISABLEABLE_GUARDRAILS

    def test_contains_groundedness(self):
        assert "GroundednessChecker" in NON_DISABLEABLE_GUARDRAILS

    def test_all_strings(self):
        assert all(isinstance(name, str) for name in NON_DISABLEABLE_GUARDRAILS)
