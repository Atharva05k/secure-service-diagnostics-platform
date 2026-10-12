
from app.sanitization import (
    sanitize_data,
    sanitize_text,
)


def test_redacts_email_and_phone():
    message = (
        "Contact rahul@example.com "
        "or +91 98765 43210"
    )

    result = sanitize_text(message)

    assert "rahul@example.com" not in result
    assert "98765 43210" not in result
    assert "[REDACTED_EMAIL]" in result
    assert "[REDACTED_PHONE]" in result


def test_redacts_credentials_in_messages():
    message = (
        "Authorization: Bearer abc123xyz; "
        "api_key=secret123; "
        "password=hunter2"
    )

    result = sanitize_text(message)

    assert "abc123xyz" not in result
    assert "secret123" not in result
    assert "hunter2" not in result


def test_sanitizes_nested_json():
    event = {
        "message": "Error for rahul@example.com",
        "details": {
            "customer_email": "rahul@example.com",
            "api_key": "secret123",
            "error_code": "PAYMENT_TIMEOUT",
            "headers": {
                "Authorization": "Bearer abc123"
            },
            "attempts": [
                {"phone": "9876543210"},
                {"duration_ms": 5000},
            ],
        },
    }

    result = sanitize_data(event)

    assert result["details"]["customer_email"] == "[REDACTED]"
    assert result["details"]["api_key"] == "[REDACTED]"
    assert result["details"]["headers"]["Authorization"] == "[REDACTED]"
    assert result["details"]["attempts"][0]["phone"] == "[REDACTED]"

    assert result["details"]["error_code"] == "PAYMENT_TIMEOUT"
    assert result["details"]["attempts"][1]["duration_ms"] == 5000

    assert "rahul@example.com" not in result["message"]


def test_original_data_is_not_modified():
    original = {
        "password": "secret123",
        "duration_ms": 250,
    }

    result = sanitize_data(original)

    assert original["password"] == "secret123"
    assert result["password"] == "[REDACTED]"
    assert result["duration_ms"] == 250
