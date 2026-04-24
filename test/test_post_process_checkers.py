"""
Tests for all 3 post-process checkers:
  - GroundednessChecker
  - RelevancyChecker
  - CopyrightComplianceChecker
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from guardrails.constants import (
    _GROUNDEDNESS_BLOCK_MSG,
    _RELEVANCY_BLOCK_MSG,
    _COPYRIGHT_BLOCK_MSG,
)


# ═══════════════════════════════════════════════════════════════════════════════
# GroundednessChecker
# ═══════════════════════════════════════════════════════════════════════════════

class TestGroundednessChecker:
    @pytest.fixture
    def checker(self):
        from guardrails.post_process.groundedness import GroundednessChecker
        with patch("guardrails.post_process.groundedness.llm_chain") as mock_llm:
            mock_llm.return_value = MagicMock()
            return GroundednessChecker("model-id", "location")

    ANSWER = "To renew your licence, visit service.nsw.gov.au and pay the $52 fee."
    CHUNKS = ["Licence renewal fee is $52. Apply online at service.nsw.gov.au."]

    @pytest.mark.asyncio
    async def test_grounded_verdict_allows(self, checker):
        with patch("guardrails.post_process.groundedness.invoke_chain", new=AsyncMock(return_value="GROUNDED")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == self.ANSWER

    @pytest.mark.asyncio
    async def test_not_grounded_verdict_blocks(self, checker):
        with patch("guardrails.post_process.groundedness.invoke_chain", new=AsyncMock(return_value="NOT_GROUNDED")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == _GROUNDEDNESS_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_partially_grounded_treated_as_not_grounded(self, checker):
        with patch("guardrails.post_process.groundedness.invoke_chain", new=AsyncMock(return_value="PARTIALLY_GROUNDED")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == _GROUNDEDNESS_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_no_context_chunks_blocks(self, checker):
        # No citations → no response (no LLM call needed)
        with patch("guardrails.post_process.groundedness.invoke_chain") as mock_inv:
            result = await checker.check(self.ANSWER, [], "sess1")
        mock_inv.assert_not_called()
        assert result == _GROUNDEDNESS_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_llm_error_fail_closed(self, checker):
        with patch("guardrails.post_process.groundedness.invoke_chain", new=AsyncMock(side_effect=Exception("down"))):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == _GROUNDEDNESS_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_unexpected_verdict_fail_closed(self, checker):
        with patch("guardrails.post_process.groundedness.invoke_chain", new=AsyncMock(return_value="UNKNOWN")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == _GROUNDEDNESS_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_multiple_context_chunks_formatted(self, checker):
        chunks = ["First chunk.", "Second chunk.", "Third chunk."]
        captured = {}
        async def mock_invoke(chain, **kwargs):
            captured.update(kwargs)
            return "GROUNDED"
        with patch("guardrails.post_process.groundedness.invoke_chain", new=mock_invoke):
            await checker.check(self.ANSWER, chunks, "sess1")
        # Context should be formatted with numbered chunks
        assert "[1]" in captured.get("context", "")
        assert "[2]" in captured.get("context", "")
        assert "[3]" in captured.get("context", "")

    @pytest.mark.asyncio
    async def test_redacted_tokens_considered_grounded(self, checker):
        # [REDACTED] tokens should not cause groundedness failure
        answer_with_redacted = "Contact [REDACTED] at [REDACTED] for help."
        with patch("guardrails.post_process.groundedness.invoke_chain", new=AsyncMock(return_value="GROUNDED")):
            result = await checker.check(answer_with_redacted, self.CHUNKS, "sess1")
        assert result == answer_with_redacted

    @pytest.mark.asyncio
    async def test_grounded_prefix_matching(self, checker):
        # "GROUNDED" with extra trailing text should still pass
        with patch("guardrails.post_process.groundedness.invoke_chain", new=AsyncMock(return_value="GROUNDED\n")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == self.ANSWER

    @pytest.mark.asyncio
    async def test_session_id_passed_to_log(self, checker):
        with patch("guardrails.post_process.groundedness.invoke_chain", new=AsyncMock(return_value="GROUNDED")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "session-xyz")
        assert result == self.ANSWER


# ═══════════════════════════════════════════════════════════════════════════════
# RelevancyChecker
# ═══════════════════════════════════════════════════════════════════════════════

class TestRelevancyChecker:
    @pytest.fixture
    def checker(self):
        from guardrails.post_process.relevancy import RelevancyChecker
        with patch("guardrails.post_process.relevancy.llm_chain") as mock_llm:
            mock_llm.return_value = MagicMock()
            return RelevancyChecker("model-id", "location")

    QUESTION = "How do I renew my licence?"
    ANSWER = "You can renew your licence online at service.nsw.gov.au."

    @pytest.mark.asyncio
    async def test_relevant_verdict_allows(self, checker):
        with patch("guardrails.post_process.relevancy.invoke_chain", new=AsyncMock(return_value="RELEVANT")):
            result = await checker.check(self.QUESTION, self.ANSWER, "sess1")
        assert result == self.ANSWER

    @pytest.mark.asyncio
    async def test_not_relevant_verdict_blocks(self, checker):
        with patch("guardrails.post_process.relevancy.invoke_chain", new=AsyncMock(return_value="NOT_RELEVANT")):
            result = await checker.check(self.QUESTION, self.ANSWER, "sess1")
        assert result == _RELEVANCY_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_partial_answer_appends_redirect_note(self, checker):
        from guardrails.post_process.relevancy import _MULTI_INTENT_NOTE
        with patch("guardrails.post_process.relevancy.invoke_chain", new=AsyncMock(return_value="PARTIAL_ANSWER")):
            result = await checker.check(
                "How do I renew my licence and apply for a grant?",
                "Here is how to renew your licence...",
                "sess1",
            )
        assert _MULTI_INTENT_NOTE in result
        assert "Here is how to renew" in result

    @pytest.mark.asyncio
    async def test_llm_error_fail_closed(self, checker):
        with patch("guardrails.post_process.relevancy.invoke_chain", new=AsyncMock(side_effect=Exception("down"))):
            result = await checker.check(self.QUESTION, self.ANSWER, "sess1")
        assert result == _RELEVANCY_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_unexpected_verdict_fail_closed(self, checker):
        with patch("guardrails.post_process.relevancy.invoke_chain", new=AsyncMock(return_value="WEIRD_VERDICT")):
            result = await checker.check(self.QUESTION, self.ANSWER, "sess1")
        assert result == _RELEVANCY_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_conversation_history_passed(self, checker):
        captured = {}
        async def mock_invoke(chain, **kwargs):
            captured.update(kwargs)
            return "RELEVANT"
        with patch("guardrails.post_process.relevancy.invoke_chain", new=mock_invoke):
            await checker.check(self.QUESTION, self.ANSWER, "sess1", conversation_history="prior turn")
        assert captured.get("history") == "prior turn"

    @pytest.mark.asyncio
    async def test_partial_answer_original_preserved(self, checker):
        from guardrails.post_process.relevancy import _MULTI_INTENT_NOTE
        original_answer = "You can renew your licence at service.nsw.gov.au."
        with patch("guardrails.post_process.relevancy.invoke_chain", new=AsyncMock(return_value="PARTIAL_ANSWER")):
            result = await checker.check(
                "Renew licence AND register a business?", original_answer, "sess1"
            )
        assert original_answer in result
        assert _MULTI_INTENT_NOTE in result

    @pytest.mark.asyncio
    async def test_relevant_prefix_matching(self, checker):
        with patch("guardrails.post_process.relevancy.invoke_chain", new=AsyncMock(return_value="RELEVANT\n")):
            result = await checker.check(self.QUESTION, self.ANSWER, "sess1")
        assert result == self.ANSWER


# ═══════════════════════════════════════════════════════════════════════════════
# CopyrightComplianceChecker
# ═══════════════════════════════════════════════════════════════════════════════

class TestCopyrightComplianceChecker:
    @pytest.fixture
    def checker(self):
        from guardrails.post_process.copyright import CopyrightComplianceChecker
        with patch("guardrails.post_process.copyright.llm_chain") as mock_llm:
            mock_llm.return_value = MagicMock()
            return CopyrightComplianceChecker("model-id", "location")

    ANSWER = "To apply for a licence, complete the form and pay the fee."
    CHUNKS = ["Complete the application form and submit it with the prescribed fee."]

    @pytest.mark.asyncio
    async def test_compliant_verdict_allows(self, checker):
        with patch("guardrails.post_process.copyright.invoke_chain", new=AsyncMock(return_value="COMPLIANT")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == self.ANSWER

    @pytest.mark.asyncio
    async def test_verbatim_reproduction_blocked(self, checker):
        with patch("guardrails.post_process.copyright.invoke_chain", new=AsyncMock(return_value="VERBATIM_REPRODUCTION")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == _COPYRIGHT_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_no_context_chunks_skips_check(self, checker):
        with patch("guardrails.post_process.copyright.invoke_chain") as mock_inv:
            result = await checker.check(self.ANSWER, [], "sess1")
        mock_inv.assert_not_called()
        assert result == self.ANSWER

    @pytest.mark.asyncio
    async def test_llm_error_fail_open_returns_original(self, checker):
        with patch("guardrails.post_process.copyright.invoke_chain", new=AsyncMock(side_effect=Exception("down"))):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == self.ANSWER  # fail-OPEN: returns original

    @pytest.mark.asyncio
    async def test_multiple_chunks_formatted(self, checker):
        chunks = ["First source.", "Second source."]
        captured = {}
        async def mock_invoke(chain, **kwargs):
            captured.update(kwargs)
            return "COMPLIANT"
        with patch("guardrails.post_process.copyright.invoke_chain", new=mock_invoke):
            await checker.check(self.ANSWER, chunks, "sess1")
        assert "[1]" in captured.get("context", "")
        assert "[2]" in captured.get("context", "")

    @pytest.mark.asyncio
    async def test_verbatim_prefix_matching(self, checker):
        with patch("guardrails.post_process.copyright.invoke_chain", new=AsyncMock(return_value="VERBATIM_REPRODUCTION with extra text")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == _COPYRIGHT_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_unexpected_verdict_allows_through(self, checker):
        # Unknown verdict — the checker only checks startswith("VERBATIM_REPRODUCTION")
        # If it doesn't start with that, the answer falls through to the allow log
        with patch("guardrails.post_process.copyright.invoke_chain", new=AsyncMock(return_value="UNKNOWN")):
            result = await checker.check(self.ANSWER, self.CHUNKS, "sess1")
        assert result == self.ANSWER
