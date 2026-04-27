from monitoring.redaction import Redactor


def test_redacts_email_phone_card_jwt_bearer():
    r = Redactor()
    text = (
        "Contact alice@example.com or +61 412 345 678. "
        "Card 4111 1111 1111 1111. "
        "Token: eyJabcdefghij.eyJabcdefghij.signaturepart "
        "Authorization: Bearer abc.def.ghi"
    )
    out = r.redact(text)
    assert "alice@example.com" not in out and "<email>" in out
    assert "<phone>" in out
    assert "<card>" in out
    assert "<jwt>" in out
    assert "Bearer <token>" in out


def test_disabled_redactor_is_passthrough():
    assert Redactor(enabled=False).redact("alice@example.com") == "alice@example.com"


def test_custom_rule():
    r = Redactor().add_rule(r"SECRET-\w+", "<custom>")
    assert r.redact("hello SECRET-XYZ world") == "hello <custom> world"


def test_empty_input_safe():
    r = Redactor()
    assert r.redact(None) == ""
    assert r.redact("") == ""