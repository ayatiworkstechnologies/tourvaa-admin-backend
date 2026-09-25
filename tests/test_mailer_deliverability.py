import pytest

from app.utils.mailer import _SmtpConfig, _build_message


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
