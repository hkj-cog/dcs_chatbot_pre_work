"""End-to-end processing pipeline for a single user query. Stateless; all mutable state in PipelineContext."""

import asyncio
from dataclasses import dataclass, field
from typing import List, Optional

from google.genai import types

from agent.scoring import ConfidenceScorer
from agent.translate import Translator
from guardrails import ALL_BLOCK_MESSAGES, SECURITY_BLOCK_MESSAGES
from guardrails.constants import _AGENT_ERROR_MSG, _OUTPUT_BLOCK_MSG, _SECRETS_BLOCK_MSG
from guardrails.moderation_utils import MODERATION_CATEGORIES_OUTPUT, check_moderation_categories
from guardrails.post_process import (
    CopyrightComplianceChecker,
    GroundednessChecker,
    RelevancyChecker,
)
from guardrails.utils import redact_secrets
from libs.config import GUARDRAILS_VERSION, JUDGE_MODEL, get_settings
from libs.logger import GuardRailEvent, log_guardrail_event, logger
from libs.phoenix_tracer import PhoenixTracer
from libs.pubsub import send_message_to_pubsub
from libs.session_threat_tracker import SessionThreatTracker
from models.chat_models import Reference


@dataclass
class PipelineContext:
    user_id: str
    session_id: str
    user_input: str
    translate: bool
    request_id: str
    sanitized_input: str = ""
    final_content: str = ""
    references: List[Reference] = field(default_factory=list)
    score: Optional[str] = None
    conversation_history: str = ""  # prior turns only; populated before agent runs
    detected_language: Optional[str] = None        # language detected from sanitized_input in _step_enrich_session
    detected_language_confidence: float = 0.0      # detection confidence; reused in _verify_translation
    # Both flags must be True before _step_publish sends content to citizens.
    dlp_input_complete: bool = False    # DLP input sanitisation ran
    agent_output_complete: bool = False  # ADK runner completed (after_model_callback fired)


class ChatPipeline:
    """Orchestrates the 8-step pipeline: DLP → session enrichment → agent → post-process → (DLP refs + score) → translate → threat-track → publish."""

    def __init__(self, runner, session_service, dlp, settings=None):
        s = settings or get_settings()
        location = s.google_cloud_location

        self._runner = runner
        self._session_service = session_service
        self._dlp = dlp
        self._pipeline_timeout = s.pipeline_timeout_seconds

        self._scorer = ConfidenceScorer(llm=JUDGE_MODEL, location=location)
        self._groundedness = GroundednessChecker(model_id=JUDGE_MODEL, location=location)
        self._relevancy = RelevancyChecker(model_id=JUDGE_MODEL, location=location)
        self._copyright = CopyrightComplianceChecker(model_id=JUDGE_MODEL, location=location)
        self._threat_tracker = SessionThreatTracker(
            threshold=s.session_threat_threshold,
            window_seconds=s.session_threat_window_seconds,
        )
        self._phoenix = PhoenixTracer(endpoint=s.phoenix_endpoint or None)

    # Entry point: executes all 8 pipeline steps in order; publishes a safe fallback on timeout or error
    async def run(self, ctx: PipelineContext) -> None:
        try:
            async with asyncio.timeout(self._pipeline_timeout):
                await self._step_dlp_input(ctx)
                await self._step_enrich_session(ctx)
                await self._step_run_agent(ctx)
                await self._step_post_process(ctx)
                await asyncio.gather(
                    self._step_dlp_references(ctx),
                    self._step_confidence_score(ctx),
                )
                await self._step_translate(ctx)
                await self._step_threat_track(ctx)
                await self._step_publish(ctx)
        except TimeoutError:
            logger.error(
                f"[Pipeline] Timeout after {self._pipeline_timeout}s "
                f"session={ctx.session_id} request={ctx.request_id}"
            )
            await send_message_to_pubsub(
                {"sender": "system", "content": _AGENT_ERROR_MSG, "references": [], "score": None},
                session_id=ctx.session_id,
            )
        except Exception as exc:
            logger.error(
                f"[Pipeline] Unhandled error session={ctx.session_id} "
                f"request={ctx.request_id}: {exc}"
            )
            await send_message_to_pubsub(
                {"sender": "system", "content": "system_error", "references": [], "score": None},
                session_id=ctx.session_id,
            )

    # Step 1: redacts PII from user input via Cloud DLP and runs a secrets pre-check before ADK session storage
    async def _step_dlp_input(self, ctx: PipelineContext) -> None:
        try:
            sanitized = await asyncio.to_thread(self._dlp.invoke, ctx.user_input)
            pii_detected = sanitized != ctx.user_input
            log_guardrail_event(GuardRailEvent(
                guardrail_name="DlpInputGuardRail",
                layer="input",
                action="modify" if pii_detected else "allow",
                session_id=ctx.session_id,
                triggered=pii_detected,
                reason="PII redacted from user input via Cloud DLP" if pii_detected else "",
            ))
            if pii_detected:
                await self._threat_tracker.record_pii_event(
                    session_id=ctx.session_id,
                    pii_types=["DLP_REDACTED"],
                )
            ctx.sanitized_input = sanitized
            ctx.dlp_input_complete = True

            # Secrets pre-check: ADK stores the user message before before_model_callback fires,
            # so SecretsInputGuardRail would be too late. Abort here to prevent credential storage.
            # SecretsInputGuardRail stays in the chain as defence-in-depth for direct agent calls.
            _, found_secrets = redact_secrets(ctx.sanitized_input)
            if found_secrets:
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="SecretsInputPreCheckGuardRail",
                    layer="input", action="block",
                    session_id=ctx.session_id, triggered=True,
                    reason=(
                        f"Credentials detected before ADK session storage — pipeline aborted: "
                        f"{', '.join(found_secrets)}"
                    ),
                ))
                ctx.final_content = _SECRETS_BLOCK_MSG
                ctx.agent_output_complete = True

        except Exception as dlp_err:
            log_guardrail_event(GuardRailEvent(
                guardrail_name="DlpInputGuardRail",
                layer="input", action="block",
                session_id=ctx.session_id, triggered=True,
                reason=f"DLP API unavailable — input rejected to protect PII: {dlp_err}",
            ))
            raise

    # Step 2: detects input language, stores user_language/translate_requested in session state, snapshots history
    async def _step_enrich_session(self, ctx: PipelineContext) -> None:
        try:
            session = await self._session_service.get_session(
                app_name="adk_chatbot",
                user_id=ctx.user_id,
                session_id=ctx.session_id,
            )
            if session is not None:
                lang, confidence = await asyncio.to_thread(
                    Translator.detect_language_with_confidence, ctx.sanitized_input
                )
                ctx.detected_language = lang
                ctx.detected_language_confidence = confidence
                s = get_settings()
                if confidence >= s.language_detection_confidence_threshold:
                    session.state["user_language"] = lang

                    # Auto-enable translation for governance-approved non-English input languages.
                    if (lang not in s.supported_output_languages
                            and lang in s.supported_input_languages):
                        ctx.translate = True
                        logger.info(
                            f"[Pipeline] Auto-translation enabled: detected language "
                            f"{lang!r} is whitelisted (session={ctx.session_id})"
                        )

                    # Prepend language context so the LLM knows what language the user is writing in.
                    if lang != "en":
                        ctx.sanitized_input = (
                            f"[Language context: The user is writing in language code "
                            f"'{lang}'. Acknowledge their language if appropriate, but "
                            f"formulate your response — the pipeline will handle "
                            f"language normalisation.]\n{ctx.sanitized_input}"
                        )
                else:
                    logger.info(
                        f"[Pipeline] Language detection confidence {confidence:.2f} below "
                        f"threshold {s.language_detection_confidence_threshold} for session "
                        f"{ctx.session_id} — user_language not stored; "
                        "LanguageCheckGuardRail will enforce service-language check only."
                    )
                session.state["translate_requested"] = ctx.translate

                # Snapshot prior turns before the agent runs (turns 1…n-1 only).
                try:
                    events = getattr(session, "events", [])
                    recent = events[-(5 * 2):]  # 5-turn window
                    parts = []
                    for event in recent:
                        content = getattr(event, "content", None)
                        if not content:
                            continue
                        event_parts = getattr(content, "parts", None) or []
                        text = " ".join(
                            p.text for p in event_parts if getattr(p, "text", None)
                        ).strip()
                        if text:
                            role = "User" if getattr(content, "role", "") == "user" else "Assistant"
                            parts.append(f"{role}: {text}")
                    ctx.conversation_history = "\n".join(parts)
                except Exception as hist_err:
                    logger.info(f"[Pipeline] History extraction skipped (session={ctx.session_id}): {hist_err}")
            else:
                logger.error(
                    f"[Pipeline] Session {ctx.session_id} not found — "
                    "user_language and translate_requested not stored; "
                    "LanguageCheckGuardRail will enforce service-language check only."
                )
        except Exception as err:
            logger.error(
                f"[Pipeline] Failed to write session state for {ctx.session_id}: {err} — "
                "user_language not stored; LanguageCheckGuardRail will enforce service-language check only."
            )

    # Step 3: streams the ADK runner for the user query; captures final content and grounding references
    async def _step_run_agent(self, ctx: PipelineContext) -> None:
        # Skip if pipeline was pre-blocked (e.g. secrets in _step_dlp_input).
        if ctx.final_content in ALL_BLOCK_MESSAGES:
            return

        async for event in self._runner.run_async(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=ctx.sanitized_input)],
            ),
        ):
            if event.is_final_response() and event.content:
                parts = event.content.parts
                if parts:
                    text_out = getattr(parts[0], "text", None)
                    ctx.final_content = text_out.strip() if isinstance(text_out, str) else str(event.content)
                else:
                    ctx.final_content = str(event.content)

                if event.grounding_metadata and event.grounding_metadata.grounding_chunks:
                    for chunk in event.grounding_metadata.grounding_chunks:
                        rc = chunk.retrieved_context
                        if rc is None:
                            continue
                        ctx.references.append(
                            Reference(chunk=rc.text or "", url=rc.uri or "", title=rc.title or "")
                        )

            elif getattr(event, "error_code", None):
                logger.error(f"[Pipeline] Agent error_code: {event.error_code}")
                ctx.final_content = _AGENT_ERROR_MSG

        if not ctx.final_content:
            logger.error(f"[Pipeline] Agent produced no final text for session={ctx.session_id}")
            ctx.final_content = _AGENT_ERROR_MSG

        ctx.agent_output_complete = True

        ref_count = len(ctx.references)
        if ref_count == 0:
            logger.warning(
                f"[Pipeline] Retrieval: 0 grounding chunks (session={ctx.session_id}) — "
                "groundedness check will block per no-citation policy"
            )
        else:
            logger.info(
                f"[Pipeline] Retrieval: {ref_count} grounding chunk(s) "
                f"(session={ctx.session_id})"
            )

    # Step 4: runs relevancy, groundedness, and copyright checkers on the agent response
    async def _step_post_process(self, ctx: PipelineContext) -> None:
        if not ctx.final_content or ctx.final_content in ALL_BLOCK_MESSAGES:
            return

        context_chunks = [r.chunk for r in ctx.references if r.chunk.strip()]

        if not context_chunks:
            # No datastore — groundedness and copyright require context, but relevancy can still run.
            logger.warning(
                f"[Pipeline] No datastore context — skipping groundedness and copyright checks "
                f"(session={ctx.session_id}). Not suitable for production."
            )
            ctx.final_content = await self._relevancy.check(
                question=ctx.sanitized_input,
                answer=ctx.final_content,
                session_id=ctx.session_id,
                conversation_history=ctx.conversation_history,
            )
            return

        # Relevancy first — an irrelevant response doesn't need a groundedness check.
        relevancy_result = await self._relevancy.check(
            question=ctx.sanitized_input,
            answer=ctx.final_content,
            session_id=ctx.session_id,
            conversation_history=ctx.conversation_history,
        )
        if relevancy_result in ALL_BLOCK_MESSAGES:
            ctx.final_content = relevancy_result
            return  # genuine block — skip downstream

        ctx.final_content = relevancy_result  # may have multi-intent note appended

        # Groundedness and copyright are independent — run concurrently to reduce latency.
        groundedness_result, copyright_result = await asyncio.gather(
            self._groundedness.check(
                answer=ctx.final_content,
                context_chunks=context_chunks,
                session_id=ctx.session_id,
            ),
            self._copyright.check(
                answer=ctx.final_content,
                context_chunks=context_chunks,
                session_id=ctx.session_id,
            ),
        )

        # Groundedness takes precedence — it is non-disableable.
        if groundedness_result in ALL_BLOCK_MESSAGES:
            ctx.final_content = groundedness_result
            return
        if copyright_result in ALL_BLOCK_MESSAGES:
            ctx.final_content = copyright_result

    # Step 5: scores response confidence via LLM judge and appends a caveat on low-confidence answers
    async def _step_confidence_score(self, ctx: PipelineContext) -> None:
        if not ctx.references:
            if ctx.final_content and ctx.final_content not in ALL_BLOCK_MESSAGES:
                ctx.score = "low"
                ctx.final_content += (
                    "\n\n*Note: I'm not fully certain about this information. "
                    "Please verify with Service NSW or the relevant agency "
                    "before acting on it.*"
                )
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="ConfidenceGuardRail",
                    layer="post-process", action="modify",
                    session_id=ctx.session_id, triggered=True,
                    reason="No grounding references — response flagged as low-confidence",
                ))
            return
        if not ctx.final_content:
            logger.debug(f"[Pipeline] Confidence scoring skipped — empty response for session {ctx.session_id}")
            return
        if ctx.final_content in ALL_BLOCK_MESSAGES:
            return

        try:
            ctx.score = await self._scorer.invoke(
                question=ctx.sanitized_input,
                answer=ctx.final_content,
                context=", ".join(r.chunk for r in ctx.references),
            )
            if ctx.score == "low" and ctx.final_content not in ALL_BLOCK_MESSAGES:
                ctx.final_content += (
                    "\n\n*Note: I'm not fully certain about this information. "
                    "Please verify with Service NSW or the relevant agency "
                    "before acting on it.*"
                )
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="ConfidenceGuardRail",
                    layer="post-process", action="modify",
                    session_id=ctx.session_id, triggered=True,
                    reason="Low-confidence response flagged with advisory caveat",
                ))
        except Exception as exc:
            logger.warning(f"[Pipeline] Confidence scoring failed (non-fatal): {exc}")
            ctx.score = None

    async def _step_dlp_references(self, ctx: PipelineContext) -> None:
        """DLP-scans grounding chunks before delivery. Defence-in-depth — chunks may contain pre-DLP datastore PII."""
        if not ctx.references:
            return

        # DLP-scans a single reference chunk; clears the chunk and logs if DLP is unavailable
        async def _scan(ref: Reference) -> Reference:
            if not ref.chunk.strip():
                return ref
            try:
                scanned = await asyncio.to_thread(self._dlp.invoke, ref.chunk)
                return Reference(chunk=scanned, url=ref.url, title=ref.title)
            except Exception as exc:
                logger.warning(
                    f"[Pipeline] DLP error on reference chunk "
                    f"(session={ctx.session_id}) — chunk cleared to protect PII: {exc}"
                )
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="DlpReferencesGuardRail",
                    layer="output", action="modify",
                    session_id=ctx.session_id, triggered=True,
                    reason=f"DLP unavailable for reference chunk — chunk cleared: {exc}",
                ))
                return Reference(chunk="", url=ref.url, title=ref.title)

        ctx.references = list(await asyncio.gather(*(_scan(r) for r in ctx.references)))

    # Step 7: translates response into user's language; re-validates secrets, DLP, and moderation
    async def _step_translate(self, ctx: PipelineContext) -> None:
        if not ctx.translate or not ctx.final_content:
            return
        if ctx.final_content in ALL_BLOCK_MESSAGES:
            return

        is_different, translated_content = await asyncio.to_thread(
            Translator.translate, ctx.sanitized_input, ctx.final_content
        )
        if not is_different:
            return

        translation_ok = await self._verify_translation(ctx, translated_content)
        if not translation_ok:
            return

        # Re-validate the translated output: secrets, DLP, moderation.
        # Composite LLM judges (bias, politeness, etc.) are skipped — English output already passed them.
        try:
            cleaned, _ = redact_secrets(translated_content)
            translated_content = cleaned
        except Exception as exc:
            logger.warning(f"[Pipeline] Post-translation secrets redaction error: {exc}")

        try:  # DLP fail-closed: revert to original if unavailable
            translated_content = await asyncio.to_thread(self._dlp.invoke, translated_content)
            log_guardrail_event(GuardRailEvent(
                guardrail_name="PostTranslationDlpGuardRail",
                layer="post-process", action="allow",
                session_id=ctx.session_id, triggered=False,
            ))
        except Exception as dlp_err:
            logger.error(f"[Pipeline] DLP error on translated output (fail-closed): {dlp_err}")
            log_guardrail_event(GuardRailEvent(
                guardrail_name="PostTranslationDlpGuardRail",
                layer="post-process", action="block",
                session_id=ctx.session_id, triggered=True,
                reason=f"DLP unavailable on translated output — reverting to original: {dlp_err}",
            ))
            return  # keep original

        try:  # Content moderation fail-open: translation rarely introduces new harm
            triggered = await asyncio.to_thread(
                check_moderation_categories, translated_content, MODERATION_CATEGORIES_OUTPUT
            )
            if triggered:
                logger.warning(
                    f"[Pipeline] Content moderation triggered on translated output "
                    f"({triggered}) — reverting to original"
                )
                log_guardrail_event(GuardRailEvent(
                    guardrail_name="PostTranslationModerationGuardRail",
                    layer="post-process", action="block",
                    session_id=ctx.session_id, triggered=True,
                    reason=f"Translated output flagged by content moderation: {triggered}",
                    snippet=translated_content[:80],
                ))
                return  # keep original
            log_guardrail_event(GuardRailEvent(
                guardrail_name="PostTranslationModerationGuardRail",
                layer="post-process", action="allow",
                session_id=ctx.session_id, triggered=False,
            ))
        except Exception as mod_err:
            logger.warning(f"[Pipeline] Post-translation moderation error (fail-open): {mod_err}")

        # Banned words check skipped on translation: English terms don't fuzzy-match reliably in other languages.
        ctx.final_content = translated_content

        async def _translate_ref(r: Reference) -> Reference:
            title = (
                (await asyncio.to_thread(Translator.translate, ctx.sanitized_input, r.title))[1]
                if r.title
                else ""
            )
            return Reference(chunk=r.chunk, url=r.url, title=title)

        ctx.references = list(await asyncio.gather(*(_translate_ref(r) for r in ctx.references)))

    # Verifies the translated output is in the expected language; discards it if high-confidence mismatch
    async def _verify_translation(self, ctx: PipelineContext, translated_content: str) -> bool:
        try:
            expected_lang = ctx.detected_language
            expected_conf = ctx.detected_language_confidence
            actual_lang, actual_conf = await asyncio.to_thread(
                Translator.detect_language_with_confidence, translated_content
            )
            if actual_lang != expected_lang:
                threshold = get_settings().language_detection_confidence_threshold
                if expected_conf >= threshold and actual_conf >= threshold:
                    # Both detections are high-confidence: treat as a genuine mismatch.
                    logger.warning(
                        f"[Pipeline] Translation language mismatch: "
                        f"expected={expected_lang!r} (conf: {expected_conf:.2f}) "
                        f"got={actual_lang!r} (conf: {actual_conf:.2f}) — discarding"
                    )
                    log_guardrail_event(GuardRailEvent(
                        guardrail_name="TranslationVerificationGuardRail",
                        layer="post-process", action="block",
                        session_id=ctx.session_id, triggered=True,
                        reason=(
                            f"Translation language mismatch: expected={expected_lang} "
                            f"(conf: {expected_conf:.2f}), actual={actual_lang} "
                            f"(conf: {actual_conf:.2f})"
                        ),
                    ))
                    return False
                else:
                    # Low-confidence detection — allow through rather than discard correct output.
                    logger.info(
                        f"[Pipeline] Translation language mismatch but low-confidence "
                        f"detection (expected={expected_lang!r}/{expected_conf:.2f}, "
                        f"actual={actual_lang!r}/{actual_conf:.2f}) — allowing through"
                    )
        except Exception as exc:
            logger.error(f"[Pipeline] Translation verification failed (fail-open): {exc}")
        return True

    # Step 8a: records a security block event in the Redis sliding window for threat detection
    async def _step_threat_track(self, ctx: PipelineContext) -> None:
        if ctx.final_content in SECURITY_BLOCK_MESSAGES:
            await self._threat_tracker.record_trigger(
                session_id=ctx.session_id,
                guardrail_name="guardrail_chain",
                reason="Security guardrail blocked a request in this session",
            )

    # Step 8b: validates guardrail gate flags then publishes the final payload to Pub/Sub and Phoenix
    async def _step_publish(self, ctx: PipelineContext) -> None:
        # Both flags must be True — if either is False a required stage was skipped (code defect).
        if not ctx.dlp_input_complete or not ctx.agent_output_complete:
            logger.critical(
                f"[Pipeline] GUARDRAIL ENFORCEMENT VIOLATION — "
                f"dlp_input_complete={ctx.dlp_input_complete} "
                f"agent_output_complete={ctx.agent_output_complete} "
                f"session={ctx.session_id} request={ctx.request_id}. "
                f"Publishing safe fallback instead of unguarded content."
            )
            await send_message_to_pubsub(
                {"sender": "system", "content": _OUTPUT_BLOCK_MSG, "references": [], "score": None},
                session_id=ctx.session_id,
            )
            return

        payload = {
            "sender": "system",
            "content": ctx.final_content,
            "references": [r.model_dump() for r in ctx.references],
            "score": ctx.score,
        }
        await send_message_to_pubsub(payload, session_id=ctx.session_id)

        # Trace after publish — tracing never blocks delivery.
        self._phoenix.trace_pipeline(
            session_id=ctx.session_id,
            sanitized_input=ctx.sanitized_input,
            final_content=ctx.final_content,
            score=ctx.score,
            was_blocked=ctx.final_content in ALL_BLOCK_MESSAGES,
            guardrail_policy_version=GUARDRAILS_VERSION,
            reference_count=len(ctx.references),
        )
