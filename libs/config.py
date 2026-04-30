# Pydantic Settings for all env vars; cached singleton via get_settings()
import json
from functools import lru_cache
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source for judge model and policy version — bump GUARDRAILS_VERSION on any policy change.
JUDGE_MODEL = "gemini-2.5-flash"
GUARDRAILS_VERSION = "1.1.0"


class Settings(BaseSettings):
    # --- core GCP / runtime ---
    project_id: str = Field(default="my-gcp-project", validation_alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="australia-southeast1", validation_alias="GOOGLE_CLOUD_LOCATION")
    queue_topic: str = Field(default="my-topic", validation_alias="QUEUE_TOPIC")
    pubsub_emulator_host: str = Field(default="", validation_alias="PUBSUB_EMULATOR_HOST")
    redis_host: str = Field(default="127.0.0.1:6379", validation_alias="REDIS_HOST")
    allowed_origins: str = Field(default="*", validation_alias="ALLOWED_ORIGINS")
    model_id: str = Field(default="gemini-2.5-flash", validation_alias="MODEL_ID")
    datastore_id: str = Field(default="", validation_alias="DATASTORE_ID")

    # --- DLP / PII ---
    pii_data_types: List[str] = Field(
        default=[
            "EMAIL_ADDRESS", "PHONE_NUMBER", "IP_ADDRESS", "FIRST_NAME", "LAST_NAME",
            "STREET_ADDRESS", "DATE_OF_BIRTH", "CREDIT_CARD_NUMBER", "PASSPORT",
            "AUSTRALIA_TAX_FILE_NUMBER", "AUSTRALIA_MEDICARE_NUMBER",
            "AUSTRALIA_DRIVERS_LICENSE_NUMBER", "AUSTRALIA_ABN_NUMBER", "MAC_ADDRESS",
        ],
        validation_alias="PII_DATA_TYPES",
    )

    # --- ban-word / guardrail tuning ---
    banned_words: List[str] = Field(default=[], validation_alias="BANNED_WORDS")
    banned_words_soft: List[str] = Field(default=[], validation_alias="BANNED_WORDS_SOFT")
    banned_words_warn: List[str] = Field(default=[], validation_alias="BANNED_WORDS_WARN")
    ban_word_context_allowlist: List[str] = Field(default=[], validation_alias="BAN_WORD_CONTEXT_ALLOWLIST")
    blocked_query_terms: List[str] = Field(
        default=["financial records", "personal employee data"],
        validation_alias="BLOCKED_QUERY_TERMS",
    )
    rate_limit_per_minute: int = Field(default=60, validation_alias="RATE_LIMIT_PER_MINUTE")
    session_threat_threshold: int = Field(default=5, validation_alias="SESSION_THREAT_THRESHOLD")
    session_threat_window_seconds: int = Field(default=3600, validation_alias="SESSION_THREAT_WINDOW_SECONDS")
    max_input_chars: int = Field(default=4000, validation_alias="MAX_INPUT_CHARS")
    max_output_chars: int = Field(default=8000, validation_alias="MAX_OUTPUT_CHARS")
    pipeline_timeout_seconds: int = Field(default=120, validation_alias="PIPELINE_TIMEOUT_SECONDS")
    ban_word_fuzzy_threshold: int = Field(default=85, validation_alias="BAN_WORD_FUZZY_THRESHOLD")
    language_detection_confidence_threshold: float = Field(
        default=0.80, validation_alias="LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD"
    )
    supported_output_languages: List[str] = Field(default=["en"], validation_alias="SUPPORTED_OUTPUT_LANGUAGES")
    supported_input_languages: List[str] = Field(default=["en"], validation_alias="SUPPORTED_INPUT_LANGUAGES")
    ws_session_ttl_seconds: int = Field(default=6000, validation_alias="WS_SESSION_TTL_SECONDS")

    banned_words_by_language: dict = Field(default={}, validation_alias="BANNED_WORDS_BY_LANGUAGE")
    banned_words_soft_by_language: dict = Field(default={}, validation_alias="BANNED_WORDS_SOFT_BY_LANGUAGE")
    banned_words_warn_by_language: dict = Field(default={}, validation_alias="BANNED_WORDS_WARN_BY_LANGUAGE")
    disabled_guardrails: List[str] = Field(default=[], validation_alias="DISABLED_GUARDRAILS")

    # --- observability (GCP Cloud Trace + Cloud Logging) ---
    # Master switch. Set to false to disable all tracing/instrumentation.
    observability_enabled: bool = Field(default=True, validation_alias="OBSERVABILITY_ENABLED")

    # OpenTelemetry resource attributes
    service_name: str = Field(default="dcs_chatbot", validation_alias="OTEL_SERVICE_NAME")

    # Export OTel spans + logs to GCP; set false for local dev without GCP credentials.
    observability_export_to_gcp: bool = Field(default=True, validation_alias="OBSERVABILITY_EXPORT_TO_GCP")

    # ParentBased(TraceIdRatioBased(...)). 1.0 = sample everything, 0.1 = 10%.
    observability_sample_ratio: float = Field(default=1.0, validation_alias="OBSERVABILITY_SAMPLE_RATIO")

    # Apply redaction to span attributes / log messages before they leave the process.
    observability_redact_pii: bool = Field(default=True, validation_alias="OBSERVABILITY_REDACT_PII")

    # Log format. "json" recommended in prod for trace<->log correlation.
    observability_log_format: Literal["json", "text"] = Field(default="json", validation_alias="LOG_FORMAT")

    # Cursor file used by the GCP Cloud Logging evaluator to track processed entries.
    eval_cursor_file: str = Field(default="cursor.json", validation_alias="EVAL_CURSOR_FILE")

    @field_validator(
        "pii_data_types", "banned_words", "banned_words_soft", "banned_words_warn",
        "blocked_query_terms", "supported_output_languages", "supported_input_languages",
        "ban_word_context_allowlist", "disabled_guardrails",
        mode="before",
    )
    @classmethod
    def parse_json_list(cls, v):
        # Parses list fields from JSON strings when set via environment variables.
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator(
        "banned_words_by_language", "banned_words_soft_by_language", "banned_words_warn_by_language",
        mode="before",
    )
    @classmethod
    def parse_json_dict(cls, v):
        # Parses dict fields from JSON strings when set via environment variables.
        if isinstance(v, str):
            return json.loads(v)
        return v

    def model_post_init(self, __context) -> None:
        # Logs warnings for missing critical config and CRITICAL for any active kill-switches.
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
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    # Cached singleton; call get_settings.cache_clear() between tests to reset.
    return Settings()
