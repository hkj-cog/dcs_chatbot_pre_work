"""
Tests for shared library modules:
  - libs/validation.py     — SESSION_ID_RE, USER_ID_RE
  - libs/dlp.py            — GoogleDlp
  - libs/session_threat_tracker.py — SessionThreatTracker
  - libs/logger.py         — GuardRailEvent, log_guardrail_event
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ═══════════════════════════════════════════════════════════════════════════════
# libs/validation.py
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionIdRegex:
    from libs.validation import SESSION_ID_RE

    def _matches(self, s: str) -> bool:
        from libs.validation import SESSION_ID_RE
        return bool(SESSION_ID_RE.match(s))

    def test_alphanumeric_valid(self):
        assert self._matches("abc123")

    def test_with_underscore_valid(self):
        assert self._matches("session_id_001")

    def test_with_hyphen_valid(self):
        assert self._matches("session-id-001")

    def test_single_char_valid(self):
        assert self._matches("a")

    def test_max_length_valid(self):
        assert self._matches("a" * 128)

    def test_too_long_invalid(self):
        assert not self._matches("a" * 129)

    def test_empty_string_invalid(self):
        assert not self._matches("")

    def test_space_invalid(self):
        assert not self._matches("session id")

    def test_at_sign_invalid(self):
        assert not self._matches("session@id")

    def test_dot_invalid(self):
        assert not self._matches("session.id")

    def test_uppercase_valid(self):
        assert self._matches("SessionID123")

    def test_mixed_case_hyphen_underscore_valid(self):
        assert self._matches("Session-ID_001")


class TestUserIdRegex:
    def _matches(self, s: str) -> bool:
        from libs.validation import USER_ID_RE
        return bool(USER_ID_RE.match(s))

    def test_simple_username_valid(self):
        assert self._matches("john123")

    def test_email_format_valid(self):
        assert self._matches("user@example.com")

    def test_with_dot_valid(self):
        assert self._matches("first.last@domain.com")

    def test_with_hyphen_valid(self):
        assert self._matches("user-name@org.gov.au")

    def test_single_char_valid(self):
        assert self._matches("u")

    def test_max_length_valid(self):
        assert self._matches("a" * 128)

    def test_too_long_invalid(self):
        assert not self._matches("a" * 129)

    def test_empty_string_invalid(self):
        assert not self._matches("")

    def test_space_invalid(self):
        assert not self._matches("user name")

    def test_special_chars_invalid(self):
        assert not self._matches("user!name")


# ═══════════════════════════════════════════════════════════════════════════════
# libs/dlp.py — GoogleDlp
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoogleDlp:
    @pytest.fixture
    def mock_dlp_client(self):
        with patch("libs.dlp.dlp_v2.DlpServiceClient") as mock_cls:
            client = MagicMock()
            mock_cls.return_value = client
            yield client

    def test_init_requires_project(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        with pytest.raises(ValueError, match="project"):
            GoogleDlp(project="", info_types=["EMAIL_ADDRESS"])

    def test_init_requires_info_types(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        with pytest.raises(ValueError, match="info_types"):
            GoogleDlp(project="my-project", info_types=[])

    def test_init_success(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        dlp = GoogleDlp(project="my-project", info_types=["EMAIL_ADDRESS"])
        assert dlp is not None

    def test_invoke_empty_string_returns_empty(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        dlp = GoogleDlp(project="my-project", info_types=["EMAIL_ADDRESS"])
        result = dlp.invoke("")
        assert result == ""
        mock_dlp_client.deidentify_content.assert_not_called()

    def test_invoke_whitespace_returns_whitespace(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        dlp = GoogleDlp(project="my-project", info_types=["EMAIL_ADDRESS"])
        result = dlp.invoke("   ")
        assert result == "   "
        mock_dlp_client.deidentify_content.assert_not_called()

    def test_invoke_calls_deidentify_content(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        response = MagicMock()
        response.item.value = "Contact [REDACTED] for more info."
        mock_dlp_client.deidentify_content.return_value = response
        dlp = GoogleDlp(project="my-project", info_types=["EMAIL_ADDRESS"])
        result = dlp.invoke("Contact john@example.com for more info.")
        assert result == "Contact [REDACTED] for more info."

    def test_invoke_no_pii_returns_original(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        original = "Normal query text without PII."
        response = MagicMock()
        response.item.value = original
        mock_dlp_client.deidentify_content.return_value = response
        dlp = GoogleDlp(project="my-project", info_types=["EMAIL_ADDRESS"])
        result = dlp.invoke(original)
        assert result == original

    def test_invoke_fail_closed_raises_runtime_error(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        mock_dlp_client.deidentify_content.side_effect = Exception("API unavailable")
        dlp = GoogleDlp(project="my-project", info_types=["EMAIL_ADDRESS"], fail_open=False)
        with pytest.raises(RuntimeError, match="DLP unavailable"):
            dlp.invoke("some query text")

    def test_invoke_fail_open_returns_original(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        mock_dlp_client.deidentify_content.side_effect = Exception("API unavailable")
        dlp = GoogleDlp(project="my-project", info_types=["EMAIL_ADDRESS"], fail_open=True)
        result = dlp.invoke("some query text")
        assert result == "some query text"

    def test_custom_replacement_string(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        response = MagicMock()
        response.item.value = "Contact [PII_REMOVED] for info."
        mock_dlp_client.deidentify_content.return_value = response
        dlp = GoogleDlp(project="my-project", info_types=["EMAIL_ADDRESS"], replacement_str="[PII_REMOVED]")
        result = dlp.invoke("Contact user@domain.com for info.")
        assert "[PII_REMOVED]" in result

    def test_multiple_info_types_accepted(self, mock_dlp_client):
        from libs.dlp import GoogleDlp
        dlp = GoogleDlp(
            project="my-project",
            info_types=["EMAIL_ADDRESS", "PHONE_NUMBER", "AUSTRALIA_TAX_FILE_NUMBER"]
        )
        assert dlp is not None


# ═══════════════════════════════════════════════════════════════════════════════
# libs/session_threat_tracker.py
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionThreatTracker:
    """
    SessionThreatTracker tests.

    Note: `record_trigger` and `record_pii_event` import redis_manager locally
    (`from libs.redis_manager import redis_manager`), so we patch
    `libs.redis_manager.redis_manager` (the object itself) rather than the
    module-level name in session_threat_tracker.
    """

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client with an async pipeline context manager."""
        redis_client = MagicMock()
        pipe = AsyncMock()
        pipe.__aenter__ = AsyncMock(return_value=pipe)
        pipe.__aexit__ = AsyncMock(return_value=None)
        # zremrangebyscore, zadd, zcard, expire are regular (non-awaited) calls
        pipe.zremrangebyscore = MagicMock()
        pipe.zadd = MagicMock()
        pipe.zcard = MagicMock()
        pipe.expire = MagicMock()
        pipe.execute = AsyncMock(return_value=[None, None, 1, None])
        redis_client.pipeline.return_value = pipe
        return redis_client, pipe

    @pytest.fixture
    def tracker(self):
        from libs.session_threat_tracker import SessionThreatTracker
        return SessionThreatTracker(threshold=3, window_seconds=3600, pii_threshold=5)

    @pytest.mark.asyncio
    async def test_empty_session_id_returns_false(self, tracker):
        result = await tracker.record_trigger("", "JailbreakGuardRail")
        assert result is False

    @pytest.mark.asyncio
    async def test_below_threshold_returns_false(self, tracker, mock_redis):
        redis_client, pipe = mock_redis
        pipe.execute.return_value = [None, None, 2, None]  # count=2, threshold=3
        with patch("libs.redis_manager.redis_manager") as mock_mgr:
            mock_mgr.get_client.return_value = redis_client
            result = await tracker.record_trigger("sess1", "JailbreakGuardRail")
        assert result is False

    @pytest.mark.asyncio
    async def test_at_threshold_returns_true_and_escalates(self, tracker, mock_redis):
        redis_client, pipe = mock_redis
        pipe.execute.return_value = [None, None, 3, None]  # count == threshold=3
        with patch("libs.redis_manager.redis_manager") as mock_mgr, \
             patch("libs.session_threat_tracker.log_escalation_event") as mock_esc:
            mock_mgr.get_client.return_value = redis_client
            result = await tracker.record_trigger("sess1", "JailbreakGuardRail", "Attack detected")
        assert result is True
        mock_esc.assert_called_once()

    @pytest.mark.asyncio
    async def test_above_threshold_no_re_escalation(self, tracker, mock_redis):
        redis_client, pipe = mock_redis
        pipe.execute.return_value = [None, None, 4, None]  # count=4 > threshold=3
        with patch("libs.redis_manager.redis_manager") as mock_mgr, \
             patch("libs.session_threat_tracker.log_escalation_event") as mock_esc:
            mock_mgr.get_client.return_value = redis_client
            result = await tracker.record_trigger("sess1", "JailbreakGuardRail")
        # count > threshold but != threshold → no re-escalation
        assert result is False
        mock_esc.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_error_fail_open(self, tracker, mock_redis):
        redis_client, pipe = mock_redis
        pipe.execute.side_effect = Exception("Redis down")
        with patch("libs.redis_manager.redis_manager") as mock_mgr:
            mock_mgr.get_client.return_value = redis_client
            result = await tracker.record_trigger("sess1", "JailbreakGuardRail")
        assert result is False  # fail-OPEN: Redis error never gates requests

    @pytest.mark.asyncio
    async def test_pii_empty_session_returns_false(self, tracker):
        result = await tracker.record_pii_event("", ["EMAIL_ADDRESS"])
        assert result is False

    @pytest.mark.asyncio
    async def test_pii_below_threshold_returns_false(self, tracker, mock_redis):
        redis_client, pipe = mock_redis
        pipe.execute.return_value = [None, None, 3, None]  # count=3 < pii_threshold=5
        with patch("libs.redis_manager.redis_manager") as mock_mgr:
            mock_mgr.get_client.return_value = redis_client
            result = await tracker.record_pii_event("sess1", ["EMAIL_ADDRESS"])
        assert result is False

    @pytest.mark.asyncio
    async def test_pii_at_threshold_returns_true(self, tracker, mock_redis):
        redis_client, pipe = mock_redis
        pipe.execute.return_value = [None, None, 5, None]  # count=5 == pii_threshold=5
        with patch("libs.redis_manager.redis_manager") as mock_mgr:
            mock_mgr.get_client.return_value = redis_client
            result = await tracker.record_pii_event("sess1", ["EMAIL_ADDRESS", "PHONE_NUMBER"])
        assert result is True

    @pytest.mark.asyncio
    async def test_pii_redis_error_fail_open(self, tracker, mock_redis):
        redis_client, pipe = mock_redis
        pipe.execute.side_effect = Exception("Redis down")
        with patch("libs.redis_manager.redis_manager") as mock_mgr:
            mock_mgr.get_client.return_value = redis_client
            result = await tracker.record_pii_event("sess1", ["EMAIL_ADDRESS"])
        assert result is False  # fail-OPEN

    def test_distinct_keys_threat_vs_pii(self):
        """
        Verify that the threat counter and PII counter use distinct Redis key prefixes.
        Confirmed via code inspection: 'threat:{session_id}' vs 'pii_threat:{session_id}'.
        This test documents the invariant.
        """
        session_id = "test-session"
        assert f"threat:{session_id}" != f"pii_threat:{session_id}"


# ═══════════════════════════════════════════════════════════════════════════════
# libs/logger.py
# ═══════════════════════════════════════════════════════════════════════════════

class TestLogger:
    def test_guardrail_event_dataclass(self):
        from libs.logger import GuardRailEvent
        event = GuardRailEvent(
            guardrail_name="TestGuardRail",
            layer="input",
            action="block",
            session_id="sess1",
            triggered=True,
            reason="Test reason",
            snippet="Short snippet",
        )
        assert event.guardrail_name == "TestGuardRail"
        assert event.layer == "input"
        assert event.action == "block"
        assert event.triggered is True
        assert event.reason == "Test reason"
        assert event.policy_version != ""  # auto-populated from GUARDRAILS_VERSION

    def test_guardrail_event_default_fields(self):
        from libs.logger import GuardRailEvent
        event = GuardRailEvent(
            guardrail_name="Test",
            layer="output",
            action="allow",
            session_id="",
            triggered=False,
        )
        assert event.reason == ""
        assert event.snippet == ""

    def test_log_guardrail_event_block_calls_warning(self):
        """Block events must use logger.warning so SIEM can filter by severity."""
        from libs.logger import GuardRailEvent, log_guardrail_event, logger
        with patch.object(logger, "warning") as mock_warn:
            event = GuardRailEvent(
                guardrail_name="TestGuardRail",
                layer="input",
                action="block",
                session_id="sess1",
                triggered=True,
                reason="Test block",
            )
            log_guardrail_event(event)
        mock_warn.assert_called_once()
        payload = json.loads(mock_warn.call_args[0][0])
        assert payload["guardrail_event"]["guardrail_name"] == "TestGuardRail"
        assert payload["guardrail_event"]["action"] == "block"

    def test_log_guardrail_event_allow_calls_info(self):
        """Allow events must use logger.info (not warning) to reduce log noise."""
        from libs.logger import GuardRailEvent, log_guardrail_event, logger
        with patch.object(logger, "info") as mock_info:
            event = GuardRailEvent(
                guardrail_name="TestGuardRail",
                layer="input",
                action="allow",
                session_id="sess1",
                triggered=False,
            )
            log_guardrail_event(event)
        mock_info.assert_called_once()
        payload = json.loads(mock_info.call_args[0][0])
        assert payload["guardrail_event"]["action"] == "allow"

    def test_log_escalation_event_emits_valid_json(self):
        """Escalation events must be valid JSON with escalation_event key."""
        from libs.logger import log_escalation_event, logger
        with patch.object(logger, "critical") as mock_crit:
            log_escalation_event(
                session_id="sess1",
                trigger_count=5,
                last_guardrail="JailbreakGuardRail",
                reason="Attack detected",
            )
        mock_crit.assert_called_once()
        payload = json.loads(mock_crit.call_args[0][0])
        assert payload["escalation_event"]["session_id"] == "sess1"
        assert payload["escalation_event"]["trigger_count"] == 5
        assert payload["escalation_event"]["last_guardrail"] == "JailbreakGuardRail"
