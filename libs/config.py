# Pydantic Settings for all env vars; cached singleton via get_settings()
import json
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for the shared judge model and policy version.
# BUMP GUARDRAILS_VERSION whenever any guardrail prompt, threshold, or policy changes.
JUDGE_MODEL = "gemini-2.5-flash"
GUARDRAILS_VERSION = "1.1.0"


class Settings(BaseSettings):
    project_id: str = Field(default="my-gcp-project", validation_alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="australia-southeast1", validation_alias="GOOGLE_CLOUD_LOCATION")
    queue_topic: str = Field(default="my-topic", validation_alias="QUEUE_TOPIC")
    pubsub_emulator_host: str = Field(
        default="", validation_alias="PUBSUB_EMULATOR_HOST"
    )

    redis_host: str = Field(
        default="127.0.0.1:6379", validation_alias="REDIS_HOST"
    )

    allowed_origins: str = Field(default="*", validation_alias="ALLOWED_ORIGINS")

    model_id: str = Field(default="gemini-2.5-flash", validation_alias="MODEL_ID")
    datastore_id: str = Field(default="", validation_alias="DATASTORE_ID")

    pii_data_types: List[str] = Field(
        default=[
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "IP_ADDRESS",
            "FIRST_NAME",
            "LAST_NAME",
            "STREET_ADDRESS",
            "DATE_OF_BIRTH",
            "CREDIT_CARD_NUMBER",
            "PASSPORT",
            "AUSTRALIA_TAX_FILE_NUMBER",
            "AUSTRALIA_MEDICARE_NUMBER",
            "AUSTRALIA_DRIVERS_LICENSE_NUMBER",
            "AUSTRALIA_ABN_NUMBER",  # identifies sole traders; DLP uses checksum validation
            "MAC_ADDRESS",           # unique hardware identifier; negligible false-positive rate
        ],
        validation_alias="PII_DATA_TYPES",
    )

    # Three-tier ban word lists. hard=always block, soft=softer block, warn=log only.
    banned_words: List[str] = Field(default=[], validation_alias="BANNED_WORDS")
    banned_words_soft: List[str] = Field(default=[], validation_alias="BANNED_WORDS_SOFT")
    banned_words_warn: List[str] = Field(default=[], validation_alias="BANNED_WORDS_WARN")
    # Regex patterns that reduce the effective ban tier by one (e.g. for legal citations).
    ban_word_context_allowlist: List[str] = Field(
        default=[],
        validation_alias="BAN_WORD_CONTEXT_ALLOWLIST",
    )

    # Sensitive query terms fuzzy-matched against the Vertex AI Search query string.
    blocked_query_terms: List[str] = Field(
        default=["financial records", "personal employee data"],
        validation_alias="BLOCKED_QUERY_TERMS",
    )

    rate_limit_per_minute: int = Field(
        default=60,
        validation_alias="RATE_LIMIT_PER_MINUTE",
    )

    # Triggers a CRITICAL escalation log when this many guardrail blocks occur within the window.
    session_threat_threshold: int = Field(
        default=5,
        validation_alias="SESSION_THREAT_THRESHOLD",
    )
    session_threat_window_seconds: int = Field(
        default=3600,
        validation_alias="SESSION_THREAT_WINDOW_SECONDS",
    )

    # Must stay consistent with the HTTP boundary check in receiver/models.py.
    max_input_chars: int = Field(
        default=4000,
        validation_alias="MAX_INPUT_CHARS",
    )
    max_output_chars: int = Field(
        default=8000,
        validation_alias="MAX_OUTPUT_CHARS",
    )

    # Total wall-clock budget for one pipeline run. Covers every step from DLP input to publish,
    # including the ADK agent call, all LLM judges, DLP, and translation. Prevents a hung
    # Vertex AI call from accumulating tasks indefinitely under load.
    pipeline_timeout_seconds: int = Field(
        default=120,
        validation_alias="PIPELINE_TIMEOUT_SECONDS",
    )

    # 0–100 fuzzy match threshold: higher = stricter, lower = catches more misspellings.
    ban_word_fuzzy_threshold: int = Field(
        default=85,
        validation_alias="BAN_WORD_FUZZY_THRESHOLD",
    )

    # LanguageCheckGuardRail ignores detections below this confidence (0.0–1.0).
    # Short inputs and code-switched phrases routinely fall below 0.80.
    language_detection_confidence_threshold: float = Field(
        default=0.80,
        validation_alias="LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD",
    )

    # Output is accepted in these languages OR the user's own detected language.
    # Blocks when the LLM drifts to a third language.
    supported_output_languages: List[str] = Field(
        default=["en"],
        validation_alias="SUPPORTED_OUTPUT_LANGUAGES",
    )

    # Governance-approved input languages that trigger auto-translation.
    # Extend only after safety testing and guardrail validation in the target language.
    supported_input_languages: List[str] = Field(
        default=["en"],
        validation_alias="SUPPORTED_INPUT_LANGUAGES",
    )

    # Must cover the full pipeline round-trip for slow queries.
    ws_session_ttl_seconds: int = Field(
        default=6000,
        validation_alias="WS_SESSION_TTL_SECONDS",
    )

    # OTLP HTTP endpoint for Arize Phoenix tracing. Empty = stub active (no spans emitted).
    # See libs/phoenix_tracer.py for activation steps.
    phoenix_endpoint: str = Field(
        default="",
        validation_alias="PHOENIX_ENDPOINT",
    )

    # Per-language ban words keyed by BCP-47 code; merged with the base tier lists at runtime.
    # No inflection expansion — English suffixes don't generalise. Add after governance approval.
    banned_words_by_language: dict = Field(
        default={},
        validation_alias="BANNED_WORDS_BY_LANGUAGE",
    )
    banned_words_soft_by_language: dict = Field(
        default={},
        validation_alias="BANNED_WORDS_SOFT_BY_LANGUAGE",
    )
    banned_words_warn_by_language: dict = Field(
        default={},
        validation_alias="BANNED_WORDS_WARN_BY_LANGUAGE",
    )

    # Emergency kill switches. NON_DISABLEABLE_GUARDRAILS are silently ignored.
    # Any effective entry emits a CRITICAL log at startup.
    disabled_guardrails: List[str] = Field(
        default=[],
        validation_alias="DISABLED_GUARDRAILS",
    )

    @field_validator(
        "pii_data_types", "banned_words", "banned_words_soft", "banned_words_warn",
        "blocked_query_terms", "supported_output_languages", "supported_input_languages",
        "ban_word_context_allowlist", "disabled_guardrails",
        mode="before",
    )
    @classmethod
    def parse_json_list(cls, v):
        """Accept a JSON string from .env or a plain list."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator(
        "banned_words_by_language", "banned_words_soft_by_language", "banned_words_warn_by_language",
        mode="before",
    )
    @classmethod
    def parse_json_dict(cls, v):
        """Accept a JSON string from .env or a plain dict."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    def model_post_init(self, __context) -> None:
        """Emit startup warnings for incomplete security configuration."""
        from libs.logger import logger as _log
        if not self.banned_words:
            _log.warning(
                "[Config] BANNED_WORDS is not configured (empty list). "
                "BanWordsInputGuardRail and BanWordsGuardRail are no-ops. "
                "Set BANNED_WORDS=[\"word1\",\"word2\"] in .env to activate."
            )
        if not self.supported_output_languages:
            _log.warning(
                "[Config] SUPPORTED_OUTPUT_LANGUAGES is empty. "
                "LanguageCheckGuardRail will block any output whose language differs from the "
                "user's detected input language — and will block ALL output when input "
                "language detection is low-confidence or unavailable. "
                "Set SUPPORTED_OUTPUT_LANGUAGES=[\"en\"] to allow the service primary language."
            )
        if self.disabled_guardrails:
            from guardrails.constants import NON_DISABLEABLE_GUARDRAILS
            effective = [g for g in self.disabled_guardrails if g not in NON_DISABLEABLE_GUARDRAILS]
            ignored = [g for g in self.disabled_guardrails if g in NON_DISABLEABLE_GUARDRAILS]
            if ignored:
                _log.warning(
                    f"[Config] DISABLED_GUARDRAILS contains non-disableable guardrails "
                    f"(silently ignored): {ignored}"
                )
            if effective:
                _log.critical(
                    f"[Config] GUARDRAIL KILL-SWITCHES ACTIVE — the following guardrails "
                    f"are DISABLED at startup: {effective}. "
                    "This reduces safety coverage. Ensure this is intentional and temporary."
                )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # allows SDK vars like GOOGLE_GENAI_USE_VERTEXAI without ValidationError
    )


@lru_cache
def get_settings() -> Settings:
    """Returns a cached Settings singleton (prevents re-reading .env on every call)."""
    return Settings()