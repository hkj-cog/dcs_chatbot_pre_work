"""Agent factory — builds the ADK Runner, session service, and shared DLP client."""

import logging

from google.adk.memory import InMemoryMemoryService
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import VertexAiSearchTool
from google.genai import types

from agent.agent import VertexAIAgent
from agent.prompt import INSTRUCTIONS
from agent.utils import get_gcp_project_id
from guardrails.constants import NON_DISABLEABLE_GUARDRAILS
from guardrails import (
    InputLengthGuardRail,
    SecretsInputGuardRail,
    DateTimeInjectorGuardRail,
    BanWordsInputGuardRail,
    JailbreakGuardRail,
    CrisisDetectionInputGuardRail,
    ImproperContentGuardRail,
    CompositeInputJudgeGuardRail,
    OutputLengthGuardRail,
    CreditCardRedactionGuardRail,
    SecretsOutputGuardRail,
    JailbreakOutputGuardRail,
    DlpOutputGuardRail,
    ContentModerationOutputGuardRail,
    BanWordsGuardRail,
    CitizenReadabilityOutputGuardRail,
    LanguageCheckGuardRail,
    CompositeOutputJudgeGuardRail,
    NSWAIComplianceGuardRail,
    RequiredInclusionsGuardRail,
    InformationCurrencyGuardRail,
    ToolCallGuardRail,
    ToolResponseGuardRail,
)
from libs.config import JUDGE_MODEL, get_settings
from libs.dlp import GoogleDlp
from libs.logger import logger

_log = logging.getLogger("dcs_chatbot")


def build_dlp(settings=None) -> GoogleDlp:
    """Creates the shared DLP client used by both input redaction and DlpOutputGuardRail."""
    s = settings or get_settings()
    project_id = get_gcp_project_id() or s.project_id
    return GoogleDlp(
        project=project_id,
        info_types=s.pii_data_types,
        location=s.google_cloud_location,
    )


def build_session_service(settings=None):
    """Returns VertexAiSessionService in production, InMemorySessionService locally (PUBSUB_EMULATOR_HOST set)."""
    s = settings or get_settings()
    if s.pubsub_emulator_host:
        logger.info(
            "[SESSION] Using InMemorySessionService (local dev — PUBSUB_EMULATOR_HOST is set). "
            "Sessions are not persisted across restarts."
        )
        return InMemorySessionService()
    project_id = get_gcp_project_id() or s.project_id
    location = s.google_cloud_location
    try:
        from google.adk.sessions import VertexAiSessionService
        service = VertexAiSessionService(project=project_id, location=location)
        logger.info(
            "[SESSION] Using VertexAiSessionService — sessions persist across restarts "
            "and are shared across all instances."
        )
        return service
    except Exception as err:
        logger.warning(
            f"[SESSION] VertexAiSessionService unavailable ({err}). "
            "Falling back to InMemorySessionService — not suitable for production scaling."
        )
        return InMemorySessionService()


def _filter_disabled(guardrails: list, disabled: set) -> list:
    """Removes guardrails in `disabled`, skipping NON_DISABLEABLE_GUARDRAILS. Logs CRITICAL for each removal."""
    result = []
    for g in guardrails:
        name = g.__class__.__name__
        if name in disabled and name not in NON_DISABLEABLE_GUARDRAILS:
            _log.critical(
                f"[KillSwitch] Guardrail '{name}' DISABLED via DISABLED_GUARDRAILS config. "
                "Safety coverage is reduced. Ensure this is intentional and temporary."
            )
        else:
            result.append(g)
    return result


def build_runner(dlp: GoogleDlp, settings=None) -> tuple:
    """Assembles the full ADK Runner with all guardrails wired in."""
    s = settings or get_settings()
    location = s.google_cloud_location
    model_id = s.model_id
    datastore_id = s.datastore_id
    disabled = set(s.disabled_guardrails) - NON_DISABLEABLE_GUARDRAILS

    if datastore_id:
        tools = [VertexAiSearchTool(data_store_id=datastore_id, max_results=5)]
    elif s.pubsub_emulator_host:
        logger.warning(
            "[Agent] DATASTORE_ID not set — running without Vertex AI Search (local dev only). "
            "Groundedness and copyright post-process checks will be skipped."
        )
        tools = []
    else:
        raise ValueError("DATASTORE_ID must be configured for production use.")

    agent_wrapper = VertexAIAgent(
        model_id=model_id,
        instructions=INSTRUCTIONS,
        tools=tools,
        agent_name="adk_chatbot",
        agent_description="Helps users with questions by searching the NSW Government document datastore.",

        input_guardrails=_filter_disabled([
            InputLengthGuardRail(max_chars=s.max_input_chars),
            SecretsInputGuardRail(),
            DateTimeInjectorGuardRail(),
            BanWordsInputGuardRail(
                banned_words=s.banned_words,
                banned_words_soft=s.banned_words_soft,
                banned_words_warn=s.banned_words_warn,
                context_allowlist=s.ban_word_context_allowlist,
                threshold=s.ban_word_fuzzy_threshold,
            ),
            # Crisis runs before jailbreak so distress messages get a compassionate response, not a security block.
            CrisisDetectionInputGuardRail(model_id=JUDGE_MODEL, location=location),
            JailbreakGuardRail(model_id=JUDGE_MODEL, location=location),
            ImproperContentGuardRail(),
            CompositeInputJudgeGuardRail(model_id=JUDGE_MODEL, location=location),
        ], disabled),

        output_guardrails=_filter_disabled([
            OutputLengthGuardRail(max_chars=s.max_output_chars),
            # Plain-language rewrite runs second so downstream guardrails evaluate the final text.
            CitizenReadabilityOutputGuardRail(model_id=JUDGE_MODEL, location=location),
            CreditCardRedactionGuardRail(),
            SecretsOutputGuardRail(),
            JailbreakOutputGuardRail(),
            DlpOutputGuardRail(dlp=dlp),
            ContentModerationOutputGuardRail(),
            BanWordsGuardRail(
                banned_words=s.banned_words,
                banned_words_soft=s.banned_words_soft,
                banned_words_warn=s.banned_words_warn,
                context_allowlist=s.ban_word_context_allowlist,
                threshold=s.ban_word_fuzzy_threshold,
            ),
            LanguageCheckGuardRail(),
            CompositeOutputJudgeGuardRail(model_id=JUDGE_MODEL, location=location),
            NSWAIComplianceGuardRail(model_id=JUDGE_MODEL, location=location),
            RequiredInclusionsGuardRail(model_id=JUDGE_MODEL, location=location),
            InformationCurrencyGuardRail(model_id=JUDGE_MODEL, location=location),  # wraps the fully-validated response
        ], disabled),

        tool_call_guardrail=ToolCallGuardRail(blocked_query_terms=s.blocked_query_terms),
        tool_response_guardrail=ToolResponseGuardRail(
            banned_words=s.banned_words,
            threshold=s.ban_word_fuzzy_threshold,
            dlp=dlp,
        ),

        safety_settings=[
            types.SafetySetting(
                method=types.HarmBlockMethod.PROBABILITY,
                category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
            types.SafetySetting(
                method=types.HarmBlockMethod.PROBABILITY,
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
            types.SafetySetting(
                method=types.HarmBlockMethod.PROBABILITY,
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
            types.SafetySetting(
                method=types.HarmBlockMethod.PROBABILITY,
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
            types.SafetySetting(
                method=types.HarmBlockMethod.PROBABILITY,
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            ),
        ],
    )

    session_service = build_session_service(s)

    return Runner(
        app_name="adk_chatbot",
        agent=agent_wrapper.agent,
        plugins=[LoggingPlugin()],
        session_service=session_service,
        memory_service=InMemoryMemoryService(),
    ), session_service
