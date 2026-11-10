import pytest
from unittest.mock import MagicMock

from app.models.settings import SmtpSetting
import app.services.settings as settings_service
from app.services.settings import update_smtp_settings_payload
from app.utils.mailer import _SmtpConfig, _build_message, _normalise_smtp_transport


def _config(**overrides):
    values = {
        "host": "smtp.example.com",
        "port": 587,
        "username": "mailer@example.com",
        "password": "secret",
        "from_name": "Tourvaa",
        "from_email": "notifications@example.com",
        "reply_to": "support@example.com",
        "use_ssl": False,
        "use_starttls": True,
        "timeout_seconds": 10,
    }
    values.update(overrides)
    return _SmtpConfig(**values)


def test_message_has_aligned_transactional_headers_and_both_body_formats():
    message, message_id = _build_message(
        _config(),
        "traveller@example.net",
        "Booking confirmed",
        "<html><body><p>Your booking is confirmed.</p></body></html>",
    )

    assert message["From"] == "Tourvaa <notifications@example.com>"
    assert message["Reply-To"] == "support@example.com"
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["Message-ID"] == message_id
    assert message_id.endswith("@example.com>")
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "Your booking is confirmed."
    assert message.get_body(preferencelist=("html",)).get_content_subtype() == "html"


def test_ssl_transport_disables_conflicting_starttls_setting():
    normalized = _normalise_smtp_transport(_config(use_ssl=True, use_starttls=True))

    assert normalized.use_ssl is True
    assert normalized.use_starttls is False


def test_saving_smtp_with_ssl_normalizes_conflicting_starttls(monkeypatch):
    setting = SmtpSetting(is_enabled=True, host="smtp.example.com", use_ssl=False, use_starttls=True)
    setting.id = 1
    db = MagicMock()
    monkeypatch.setattr(settings_service, "get_or_create_smtp_settings", lambda _db: setting)
    monkeypatch.setattr(settings_service, "log_audit", lambda *args, **kwargs: None)

    payload = update_smtp_settings_payload(db, {"use_ssl": True, "use_starttls": True})

    assert payload["use_ssl"] is True
    assert payload["use_starttls"] is False


@pytest.mark.parametrize(
    ("recipient", "subject"),
    [
        ("good@example.net\r\nBcc: bad@example.net", "Hello"),
        ("good@example.net", "Hello\r\nBcc: bad@example.net"),
        ("one@example.net, two@example.net", "Hello"),
    ],
)
def test_message_rejects_unsafe_address_or_subject_headers(recipient, subject):
    with pytest.raises(ValueError):
        _build_message(_config(), recipient, subject, "<p>Hello</p>")
