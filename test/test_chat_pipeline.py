"""
Unit tests for ChatPipeline — orchestration logic, gate enforcement, and regression
coverage for all fixes applied in this session:
  - PARTIAL_ANSWER no longer skips GroundednessChecker / CopyrightComplianceChecker
  - Empty agent output falls back to _AGENT_ERROR_MSG (agent_output_complete set first)
  - Pipeline timeout publishes _AGENT_ERROR_MSG via asyncio.timeout()
  - Zero grounding references → score="low" + caveat appended without calling scorer
  - Dual gate (dlp_input_complete + agent_output_complete) enforced in _step_publish
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from guardrails.constants import (
    _AGENT_ERROR_MSG,
    _GROUNDEDNESS_BLOCK_MSG,
    _OUTPUT_BLOCK_MSG,
    _RELEVANCY_BLOCK_MSG,
    _SECRETS_BLOCK_MSG,
)
from guardrails.post_process.relevancy import _MULTI_INTENT_NOTE
from models.chat_models import Reference
from services.chat_pipeline import ChatPipeline, PipelineContext


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_ctx(**kwargs) -> PipelineContext:
    defaults = dict(
        user_id="u1",
        session_id="s1",
        user_input="What is the fee for a driver licence?",
        translate=False,
        request_id="r1",
    )
    defaults.update(kwargs)
    return PipelineContext(**defaults)


def make_pipeline() -> ChatPipeline:
    """ChatPipeline with all external dependencies replaced by controllable mocks."""
    with (
        patch("services.chat_pipeline.ConfidenceScorer"),
        patch("services.chat_pipeline.GroundednessChecker"),
        patch("services.chat_pipeline.RelevancyChecker"),
        patch("services.chat_pipeline.CopyrightComplianceChecker"),
        patch("services.chat_pipeline.SessionThreatTracker"),
        patch("services.chat_pipeline.PhoenixTracer"),
    ):
        settings = MagicMock()
        settings.google_cloud_location = "australia-southeast1"
        settings.session_threat_threshold = 5
        settings.session_threat_window_seconds = 3600
        settings.pipeline_timeout_seconds = 30
        settings.phoenix_endpoint = ""

        p = ChatPipeline(
            runner=MagicMock(),
            session_service=AsyncMock(),
            dlp=MagicMock(invoke=MagicMock(side_effect=lambda x: x)),
            settings=settings,
        )

    # Replace auto-created constructor mocks with async-capable pass-through mocks.
    # Checkers return their input unchanged by default so tests can assert selectively.
    p._scorer = AsyncMock(return_value="high")
    p._groundedness = AsyncMock(side_effect=lambda answer, **_: answer)
    p._relevancy = AsyncMock(side_effect=lambda question, answer, **_: answer)
    p._copyright = AsyncMock(side_effect=lambda answer, **_: answer)
    p._threat_tracker = AsyncMock()
    p._phoenix = MagicMock()
    p._pipeline_timeout = 30
    return p


@pytest.fixture
def pipeline() -> ChatPipeline:
    return make_pipeline()


# ── _step_publish: dual gate enforcement ──────────────────────────────────────

class TestStepPublish:
    @pytest.mark.asyncio
    async def test_missing_dlp_flag_publishes_fallback(self, pipeline):
        ctx = make_ctx(final_content="A valid response")
        ctx.dlp_input_complete = False
        ctx.agent_output_complete = True

        with patch("services.chat_pipeline.send_message_to_pubsub", new_callable=AsyncMock) as pub:
            await pipeline._step_publish(ctx)

        pub.assert_called_once()
        assert pub.call_args[0][0]["content"] == _OUTPUT_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_missing_agent_flag_publishes_fallback(self, pipeline):
        ctx = make_ctx(final_content="A valid response")
        ctx.dlp_input_complete = True
        ctx.agent_output_complete = False

        with patch("services.chat_pipeline.send_message_to_pubsub", new_callable=AsyncMock) as pub:
            await pipeline._step_publish(ctx)

        pub.assert_called_once()
        assert pub.call_args[0][0]["content"] == _OUTPUT_BLOCK_MSG

    @pytest.mark.asyncio
    async def test_both_flags_present_publishes_content(self, pipeline):
        ctx = make_ctx(final_content="Driver licence fee is $52.")
        ctx.dlp_input_complete = True
        ctx.agent_output_complete = True

        with patch("services.chat_pipeline.send_message_to_pubsub", new_callable=AsyncMock) as pub:
            await pipeline._step_publish(ctx)

        pub.assert_called_once()
        assert pub.call_args[0][0]["content"] == "Driver licence fee is $52."

    @pytest.mark.asyncio
    async def test_references_and_score_included_in_payload(self, pipeline):
        ctx = make_ctx(final_content="The fee is $52.")
        ctx.dlp_input_complete = True
        ctx.agent_output_complete = True
        ctx.references = [Reference(chunk="Fee is $52.", url="https://nsw.gov.au", title="Fees")]
        ctx.score = "high"

        with patch("services.chat_pipeline.send_message_to_pubsub", new_callable=AsyncMock) as pub:
            await pipeline._step_publish(ctx)

        payload = pub.call_args[0][0]
        assert payload["score"] == "high"
        assert len(payload["references"]) == 1


# ── _step_run_agent: empty output guard ──────────────────────────────────────

class TestStepRunAgent:
    @pytest.mark.asyncio
    async def test_no_final_response_event_falls_back_to_error_msg(self, pipeline):
        """Runner emits only non-final events → ctx.final_content = _AGENT_ERROR_MSG."""
        async def tool_events_only(*_, **__):
            event = MagicMock()
            event.is_final_response.return_value = False
            event.error_code = None
            yield event

        pipeline._runner.run_async = MagicMock(return_value=tool_events_only())
        ctx = make_ctx()

        await pipeline._step_run_agent(ctx)

        assert ctx.final_content == _AGENT_ERROR_MSG
        assert ctx.agent_output_complete is True

    @pytest.mark.asyncio
    async def test_agent_output_complete_set_before_empty_guard(self, pipeline):
        """agent_output_complete must be True even when content is empty (runner did complete)."""
        async def empty_gen(*_, **__):
            return
            yield  # make it a generator

        pipeline._runner.run_async = MagicMock(return_value=empty_gen())
        ctx = make_ctx()

        await pipeline._step_run_agent(ctx)

        assert ctx.agent_output_complete is True
        assert ctx.final_content == _AGENT_ERROR_MSG

    @pytest.mark.asyncio
    async def test_final_response_event_captures_text(self, pipeline):
        async def final_event(*_, **__):
            event = MagicMock()
            event.is_final_response.return_value = True
            event.content = MagicMock()
            event.content.parts = [MagicMock(text="Driver licence fee is $52.")]
            event.grounding_metadata = None
            event.error_code = None
            yield event

        pipeline._runner.run_async = MagicMock(return_value=final_event())
        ctx = make_ctx()

        await pipeline._step_run_agent(ctx)

        assert ctx.final_content == "Driver licence fee is $52."
        assert ctx.agent_output_complete is True

    @pytest.mark.asyncio
    async def test_pre_blocked_pipeline_skips_runner(self, pipeline):
        """Secrets pre-block in _step_dlp_input must prevent the agent from running."""
        ctx = make_ctx()
        ctx.final_content = _SECRETS_BLOCK_MSG

        await pipeline._step_run_agent(ctx)

        pipeline._runner.run_async.assert_not_called()


# ── _step_post_process: relevancy / groundedness / copyright ─────────────────

class TestStepPostProcess:
    ANSWER = "Driver licence fee is $52. Renew at service.nsw.gov.au."
    CHUNK = "The driver licence renewal fee is $52."

    def _ctx_with_refs(self, answer: str) -> PipelineContext:
        ctx = make_ctx()
        ctx.final_content = answer
        ctx.sanitized_input = "What is the driver licence fee?"
        ctx.references = [Reference(chunk=self.CHUNK, url="https://nsw.gov.au", title="Fees")]
        return ctx

    @pytest.mark.asyncio
    async def test_partial_answer_still_runs_groundedness_and_copyright(self, pipeline):
        """PARTIAL_ANSWER appends a redirect note but must NOT skip groundedness or copyright.
        This is the regression test for the ctx.final_content != pre bug."""
        partial = self.ANSWER + _MULTI_INTENT_NOTE
        pipeline._relevancy = AsyncMock(return_value=partial)
        pipeline._groundedness = AsyncMock(return_value=partial)
        pipeline._copyright = AsyncMock(return_value=partial)

        ctx = self._ctx_with_refs(self.ANSWER)
        await pipeline._step_post_process(ctx)

        pipeline._groundedness.assert_called_once()
        pipeline._copyright.assert_called_once()
        assert ctx.final_content == partial

    @pytest.mark.asyncio
    async def test_not_relevant_blocks_and_skips_groundedness(self, pipeline):
        pipeline._relevancy = AsyncMock(return_value=_RELEVANCY_BLOCK_MSG)

        ctx = self._ctx_with_refs(self.ANSWER)
        await pipeline._step_post_process(ctx)

        assert ctx.final_content == _RELEVANCY_BLOCK_MSG
        pipeline._groundedness.assert_not_called()
        pipeline._copyright.assert_not_called()

    @pytest.mark.asyncio
    async def test_relevant_passes_through_to_groundedness_and_copyright(self, pipeline):
        pipeline._relevancy = AsyncMock(return_value=self.ANSWER)
        pipeline._groundedness = AsyncMock(return_value=self.ANSWER)
        pipeline._copyright = AsyncMock(return_value=self.ANSWER)

        ctx = self._ctx_with_refs(self.ANSWER)
        await pipeline._step_post_process(ctx)

        pipeline._groundedness.assert_called_once()
        pipeline._copyright.assert_called_once()
        assert ctx.final_content == self.ANSWER

    @pytest.mark.asyncio
    async def test_groundedness_block_takes_precedence_over_copyright(self, pipeline):
        """Both run concurrently; groundedness block wins when both checks have results."""
        pipeline._relevancy = AsyncMock(return_value=self.ANSWER)
        pipeline._groundedness = AsyncMock(return_value=_GROUNDEDNESS_BLOCK_MSG)
        pipeline._copyright = AsyncMock(return_value=self.ANSWER)

        ctx = self._ctx_with_refs(self.ANSWER)
        await pipeline._step_post_process(ctx)

        assert ctx.final_content == _GROUNDEDNESS_BLOCK_MSG
        # Copyright still ran — it executes in parallel with groundedness
        pipeline._copyright.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_context_chunks_runs_relevancy_only(self, pipeline):
        """No datastore context → relevancy runs, groundedness and copyright must not."""
        pipeline._relevancy = AsyncMock(return_value=self.ANSWER)

        ctx = make_ctx()
        ctx.final_content = self.ANSWER
        ctx.references = []

        await pipeline._step_post_process(ctx)

        pipeline._relevancy.assert_called_once()
        pipeline._groundedness.assert_not_called()
        pipeline._copyright.assert_not_called()

    @pytest.mark.asyncio
    async def test_block_message_content_skips_all_checks(self, pipeline):
        ctx = self._ctx_with_refs(_AGENT_ERROR_MSG)
        ctx.final_content = _AGENT_ERROR_MSG

        await pipeline._step_post_process(ctx)

        pipeline._relevancy.assert_not_called()
        pipeline._groundedness.assert_not_called()
        pipeline._copyright.assert_not_called()


# ── _step_confidence_score: zero-reference caveat ────────────────────────────

class TestStepConfidenceScore:
    @pytest.mark.asyncio
    async def test_zero_references_sets_low_score_without_calling_scorer(self, pipeline):
        """No references → definitively low confidence; scorer must not be called."""
        ctx = make_ctx()
        ctx.final_content = "Here is some information about NSW services."
        ctx.references = []

        await pipeline._step_confidence_score(ctx)

        assert ctx.score == "low"
        assert "Please verify" in ctx.final_content
        pipeline._scorer.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_references_block_message_unchanged(self, pipeline):
        """Block messages must not receive the zero-reference caveat."""
        ctx = make_ctx()
        ctx.final_content = _AGENT_ERROR_MSG
        ctx.references = []
        original = ctx.final_content

        await pipeline._step_confidence_score(ctx)

        assert ctx.score is None
        assert ctx.final_content == original
        pipeline._scorer.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_references_calls_scorer(self, pipeline):
        pipeline._scorer = AsyncMock(return_value="high")
        ctx = make_ctx()
        ctx.final_content = "The fee is $52."
        ctx.references = [Reference(chunk="Fee is $52.", url="", title="")]

        await pipeline._step_confidence_score(ctx)

        pipeline._scorer.assert_called_once()
        assert ctx.score == "high"
        assert "Please verify" not in ctx.final_content

    @pytest.mark.asyncio
    async def test_low_score_appends_caveat(self, pipeline):
        pipeline._scorer = AsyncMock(return_value="low")
        ctx = make_ctx()
        ctx.final_content = "The fee is approximately $52."
        ctx.references = [Reference(chunk="Fee is $52.", url="", title="")]

        await pipeline._step_confidence_score(ctx)

        assert ctx.score == "low"
        assert "Please verify" in ctx.final_content

    @pytest.mark.asyncio
    async def test_scorer_failure_sets_score_none(self, pipeline):
        pipeline._scorer = AsyncMock(side_effect=Exception("LLM unavailable"))
        ctx = make_ctx()
        ctx.final_content = "The fee is $52."
        ctx.references = [Reference(chunk="Fee is $52.", url="", title="")]
        original = ctx.final_content

        await pipeline._step_confidence_score(ctx)

        assert ctx.score is None
        assert ctx.final_content == original


# ── run(): timeout and unhandled error handling ───────────────────────────────

class TestPipelineRun:
    @pytest.mark.asyncio
    async def test_timeout_publishes_agent_error_msg(self, pipeline):
        """asyncio.timeout() must cancel a hung step and publish _AGENT_ERROR_MSG."""
        async def hang(ctx):
            await asyncio.sleep(1000)

        pipeline._step_dlp_input = hang
        pipeline._pipeline_timeout = 0.01  # 10 ms

        with patch("services.chat_pipeline.send_message_to_pubsub", new_callable=AsyncMock) as pub:
            await pipeline.run(make_ctx())

        pub.assert_called_once()
        assert pub.call_args[0][0]["content"] == _AGENT_ERROR_MSG

    @pytest.mark.asyncio
    async def test_unhandled_exception_publishes_system_error(self, pipeline):
        async def boom(ctx):
            raise RuntimeError("unexpected failure")

        pipeline._step_dlp_input = boom

        with patch("services.chat_pipeline.send_message_to_pubsub", new_callable=AsyncMock) as pub:
            await pipeline.run(make_ctx())

        pub.assert_called_once()
        assert pub.call_args[0][0]["content"] == "system_error"
