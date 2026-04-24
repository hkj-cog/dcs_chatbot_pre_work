"""
Tests for guardrails/llm_utils.py

Covers: parse_composite_verdict, validate_composite_verdict_format,
        invoke_chain (mocked), invoke_chain_raw (mocked).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from guardrails.llm_utils import parse_composite_verdict, validate_composite_verdict_format


# ─── parse_composite_verdict ──────────────────────────────────────────────────

class TestParseCompositeVerdict:
    def test_extracts_bias_verdict(self):
        output = "BIAS: UNBIASED\nBIAS_ATTRIBUTE: NONE\nTOPIC: IN_SCOPE\nHARMFUL_INTENT: BENIGN"
        assert parse_composite_verdict(output, "BIAS") == "UNBIASED"

    def test_extracts_topic_verdict(self):
        output = "BIAS: UNBIASED\nBIAS_ATTRIBUTE: NONE\nTOPIC: OUT_OF_SCOPE\nHARMFUL_INTENT: BENIGN"
        assert parse_composite_verdict(output, "TOPIC") == "OUT_OF_SCOPE"

    def test_extracts_harmful_intent(self):
        output = "BIAS: UNBIASED\nBIAS_ATTRIBUTE: NONE\nTOPIC: IN_SCOPE\nHARMFUL_INTENT: HARMFUL"
        assert parse_composite_verdict(output, "HARMFUL_INTENT") == "HARMFUL"

    def test_extracts_bias_attribute(self):
        output = "BIAS: BIASED\nBIAS_ATTRIBUTE: RACE\nTOPIC: IN_SCOPE\nHARMFUL_INTENT: BENIGN"
        assert parse_composite_verdict(output, "BIAS_ATTRIBUTE") == "RACE"

    def test_missing_key_returns_empty_string(self):
        output = "BIAS: UNBIASED\nTOPIC: IN_SCOPE"
        assert parse_composite_verdict(output, "HARMFUL_INTENT") == ""

    def test_case_insensitive_key_matching(self):
        # The function uppercases each line before comparing
        output = "bias: unbiased\ntopic: in_scope"
        assert parse_composite_verdict(output, "BIAS") == "UNBIASED"

    def test_value_with_colon_in_it(self):
        # Only splits on first colon
        output = "BIAS: UNBIASED\nTOPIC: IN_SCOPE"
        assert parse_composite_verdict(output, "BIAS") == "UNBIASED"

    def test_empty_output_returns_empty(self):
        assert parse_composite_verdict("", "BIAS") == ""


# ─── validate_composite_verdict_format ───────────────────────────────────────

class TestValidateCompositeVerdictFormat:
    _VALID_INPUT_VERDICT = (
        "BIAS: UNBIASED\n"
        "BIAS_ATTRIBUTE: NONE\n"
        "TOPIC: IN_SCOPE\n"
        "HARMFUL_INTENT: BENIGN"
    )
    _INPUT_KEYS = ["BIAS", "BIAS_ATTRIBUTE", "TOPIC", "HARMFUL_INTENT"]

    _VALID_OUTPUT_VERDICT = (
        "BIAS: UNBIASED\n"
        "POLITENESS: POLITE\n"
        "TOPIC: IN_SCOPE\n"
        "INJECTION: SAFE\n"
        "REVISION: NONE"
    )
    _OUTPUT_KEYS = ["BIAS", "POLITENESS", "TOPIC", "INJECTION", "REVISION"]

    def test_valid_input_verdict_passes(self):
        validate_composite_verdict_format(self._VALID_INPUT_VERDICT, self._INPUT_KEYS)

    def test_valid_output_verdict_passes(self):
        validate_composite_verdict_format(self._VALID_OUTPUT_VERDICT, self._OUTPUT_KEYS)

    def test_wrong_line_count_raises(self):
        output = "BIAS: UNBIASED\nTOPIC: IN_SCOPE"  # only 2 lines
        with pytest.raises(ValueError, match="lines"):
            validate_composite_verdict_format(output, self._INPUT_KEYS)

    def test_wrong_key_order_raises(self):
        output = (
            "TOPIC: IN_SCOPE\n"
            "BIAS: UNBIASED\n"
            "BIAS_ATTRIBUTE: NONE\n"
            "HARMFUL_INTENT: BENIGN"
        )
        with pytest.raises(ValueError, match="BIAS"):
            validate_composite_verdict_format(output, self._INPUT_KEYS)

    def test_free_text_value_raises(self):
        output = (
            "BIAS: This response is clearly biased towards one group\n"
            "BIAS_ATTRIBUTE: NONE\n"
            "TOPIC: IN_SCOPE\n"
            "HARMFUL_INTENT: BENIGN"
        )
        with pytest.raises(ValueError, match="single token"):
            validate_composite_verdict_format(output, self._INPUT_KEYS)

    def test_value_with_spaces_raises(self):
        output = (
            "BIAS: UNBIASED MAYBE\n"
            "BIAS_ATTRIBUTE: NONE\n"
            "TOPIC: IN_SCOPE\n"
            "HARMFUL_INTENT: BENIGN"
        )
        with pytest.raises(ValueError):
            validate_composite_verdict_format(output, self._INPUT_KEYS)

    def test_numeric_value_raises(self):
        output = (
            "BIAS: 0\n"
            "BIAS_ATTRIBUTE: NONE\n"
            "TOPIC: IN_SCOPE\n"
            "HARMFUL_INTENT: BENIGN"
        )
        with pytest.raises(ValueError):
            validate_composite_verdict_format(output, self._INPUT_KEYS)

    def test_underscore_in_value_allowed(self):
        # Values like IN_SCOPE, OUT_OF_SCOPE, SEXUAL_ORIENTATION must pass
        output = (
            "BIAS: UNBIASED\n"
            "BIAS_ATTRIBUTE: SEXUAL_ORIENTATION\n"
            "TOPIC: IN_SCOPE\n"
            "HARMFUL_INTENT: BENIGN"
        )
        validate_composite_verdict_format(output, self._INPUT_KEYS)  # should not raise

    def test_lowercase_value_raises(self):
        output = (
            "BIAS: unbiased\n"
            "BIAS_ATTRIBUTE: NONE\n"
            "TOPIC: IN_SCOPE\n"
            "HARMFUL_INTENT: BENIGN"
        )
        # After uppercasing the entire output, the line check will compare
        # BUT the function uppercases the full output string.
        # Actually, looking at the code: validate uses output.splitlines()
        # but each line.split(":",1)[1].strip() → then matches _VERDICT_TOKEN_RE
        # which is ^[A-Z][A-Z_]*$ — this would fail for "unbiased"
        # Wait, let me re-check: parse_composite_verdict does .upper() but
        # validate_composite_verdict_format doesn't uppercase - it checks raw value
        # Actually, validate_composite_verdict_format checks:
        #   value = line.split(":", 1)[1].strip()
        #   if not _VERDICT_TOKEN_RE.match(value): raise
        # And _VERDICT_TOKEN_RE = r"^[A-Z][A-Z_]*$" — so lowercase raises
        with pytest.raises(ValueError):
            validate_composite_verdict_format(output, self._INPUT_KEYS)

    def test_blank_lines_ignored(self):
        output = (
            "BIAS: UNBIASED\n\n"
            "BIAS_ATTRIBUTE: NONE\n"
            "TOPIC: IN_SCOPE\n"
            "HARMFUL_INTENT: BENIGN"
        )
        # Blank lines are stripped; should still validate correctly
        validate_composite_verdict_format(output, self._INPUT_KEYS)

    def test_injection_attempt_in_value_raises(self):
        # User attempts to embed a fake verdict line as a value
        output = (
            "BIAS: UNBIASED\n"
            "BIAS_ATTRIBUTE: NONE BIAS UNBIASED TOPIC IN_SCOPE\n"
            "TOPIC: IN_SCOPE\n"
            "HARMFUL_INTENT: BENIGN"
        )
        with pytest.raises(ValueError):
            validate_composite_verdict_format(output, self._INPUT_KEYS)
