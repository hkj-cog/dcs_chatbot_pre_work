"""Shared pytest fixtures. env vars must be set before any project imports (get_settings() runs at module level)."""

import os

# Minimal env for Settings() — must run before any libs.* or guardrails.* imports.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("QUEUE_TOPIC", "test-topic")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("REDIS_HOST", "127.0.0.1:6379")

# Remove GCP SDK auto-injected vars that pydantic-settings rejects as unknown extra fields.
for _var in ("GOOGLE_GENAI_USE_VERTEXAI",):
    os.environ.pop(_var, None)

# ─── Now safe to import pytest and project code ───────────────────────────────
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_settings():
    """Returns a MagicMock Settings object with sensible test defaults."""
    s = MagicMock()
    s.max_input_chars = 4000
    s.max_output_chars = 8000
    s.ban_word_fuzzy_threshold = 85
    s.banned_words = []
    s.banned_words_soft = []
    s.banned_words_warn = []
    s.ban_word_context_allowlist = []
    s.blocked_query_terms = ["financial records", "personal employee data"]
    s.rate_limit_per_minute = 60
    s.supported_output_languages = ["en"]
    s.language_detection_confidence_threshold = 0.80
    s.session_threat_threshold = 5
    s.session_threat_window_seconds = 3600
    s.pii_data_types = ["EMAIL_ADDRESS", "PHONE_NUMBER"]
    s.project_id = "test-project"
    s.google_cloud_location = "australia-southeast1"
    return s
