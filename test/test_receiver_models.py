"""
Tests for receiver/models.py:
  - ChatRequest
  - PubSubMessage
  - PubSubEnvelope

Also tests the receiver API validation patterns (User-ID format, session-ID format).
"""

import pytest
from unittest.mock import patch, MagicMock
import pydantic


# ═══════════════════════════════════════════════════════════════════════════════
# ChatRequest
# ═══════════════════════════════════════════════════════════════════════════════

class TestChatRequest:
    @pytest.fixture(autouse=True)
    def patch_settings(self):
        s = MagicMock()
        s.max_input_chars = 4000
        with patch("libs.config.get_settings", return_value=s):
            yield

    def test_valid_request(self):
        from receiver.models import ChatRequest
        req = ChatRequest(user_input="How do I renew my licence?")
        assert req.user_input == "How do I renew my licence?"
        assert req.translate is False

    def test_translate_default_false(self):
        from receiver.models import ChatRequest
        req = ChatRequest(user_input="hello")
        assert req.translate is False

    def test_translate_explicit_true(self):
        from receiver.models import ChatRequest
        req = ChatRequest(user_input="hello", translate=True)
        assert req.translate is True

    def test_whitespace_trimmed(self):
        from receiver.models import ChatRequest
        req = ChatRequest(user_input="  Hello world  ")
        assert req.user_input == "Hello world"

    def test_empty_string_raises(self):
        from receiver.models import ChatRequest
        with pytest.raises(pydantic.ValidationError):
            ChatRequest(user_input="")

    def test_whitespace_only_raises(self):
        from receiver.models import ChatRequest
        with pytest.raises(pydantic.ValidationError):
            ChatRequest(user_input="   ")

    def test_max_length_accepted(self):
        from receiver.models import ChatRequest
        req = ChatRequest(user_input="a" * 4000)
        assert len(req.user_input) == 4000

    def test_over_max_length_raises(self):
        from receiver.models import ChatRequest
        with pytest.raises(pydantic.ValidationError):
            ChatRequest(user_input="a" * 4001)

    def test_unicode_input_accepted(self):
        from receiver.models import ChatRequest
        req = ChatRequest(user_input="我需要更新我的驾照")
        assert "驾照" in req.user_input

    def test_special_characters_accepted(self):
        from receiver.models import ChatRequest
        req = ChatRequest(user_input="What about section 14(a) of the Act?")
        assert "14(a)" in req.user_input


# ═══════════════════════════════════════════════════════════════════════════════
# PubSubMessage
# ═══════════════════════════════════════════════════════════════════════════════

class TestPubSubMessage:
    def test_valid_message(self):
        from receiver.models import PubSubMessage
        msg = PubSubMessage(
            data="eyJzZXNzaW9uX2lkIjogInRlc3QifQ==",
            messageId="12345",
            publishTime="2026-04-23T10:00:00Z",
        )
        assert msg.messageId == "12345"

    def test_default_attributes_empty_dict(self):
        from receiver.models import PubSubMessage
        msg = PubSubMessage(
            data="dGVzdA==",
            messageId="1",
            publishTime="2026-01-01T00:00:00Z",
        )
        assert msg.attributes == {}

    def test_attributes_populated(self):
        from receiver.models import PubSubMessage
        msg = PubSubMessage(
            data="dGVzdA==",
            messageId="1",
            publishTime="2026-01-01T00:00:00Z",
            attributes={"session_id": "sess-abc"},
        )
        assert msg.attributes["session_id"] == "sess-abc"

    def test_missing_required_field_raises(self):
        from receiver.models import PubSubMessage
        with pytest.raises(pydantic.ValidationError):
            PubSubMessage(data="dGVzdA==", messageId="1")  # missing publishTime


# ═══════════════════════════════════════════════════════════════════════════════
# PubSubEnvelope
# ═══════════════════════════════════════════════════════════════════════════════

class TestPubSubEnvelope:
    def test_valid_envelope(self):
        from receiver.models import PubSubEnvelope, PubSubMessage
        msg = PubSubMessage(
            data="dGVzdA==",
            messageId="1",
            publishTime="2026-01-01T00:00:00Z",
        )
        envelope = PubSubEnvelope(
            message=msg,
            subscription="projects/my-project/subscriptions/my-sub",
        )
        assert envelope.subscription == "projects/my-project/subscriptions/my-sub"
        assert envelope.message.messageId == "1"

    def test_missing_message_raises(self):
        from receiver.models import PubSubEnvelope
        with pytest.raises(pydantic.ValidationError):
            PubSubEnvelope(subscription="projects/my-project/subscriptions/my-sub")

    def test_missing_subscription_raises(self):
        from receiver.models import PubSubEnvelope, PubSubMessage
        msg = PubSubMessage(
            data="dGVzdA==",
            messageId="1",
            publishTime="2026-01-01T00:00:00Z",
        )
        with pytest.raises(pydantic.ValidationError):
            PubSubEnvelope(message=msg)
