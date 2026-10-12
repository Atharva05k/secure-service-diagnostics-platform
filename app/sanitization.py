
import re
from typing import Any


REDACTED = "[REDACTED]"

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\w)"
)

BEARER_PATTERN = re.compile(
    r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)

CREDENTIAL_PATTERN = re.compile(
    r"(\b(?:password|passwd|pwd|api[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|token|secret)\b"
    r"[\"']?\s*[:=]\s*[\"']?)"
    r"([^\s,\"';}&]+)",
    re.IGNORECASE,
)

SENSITIVE_SUFFIXES = (
    "password",
    "passwd",
    "pwd",
    "apikey",
    "token",
    "secret",
    "authorization",
    "cookie",
    "sessionid",
    "email",
    "phone",
    "mobile",
    "mobilenumber",
    "phonenumber",
)


def is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())

    return any(
        normalized.endswith(suffix)
        for suffix in SENSITIVE_SUFFIXES
    )


def sanitize_text(value: str) -> str:
    value = EMAIL_PATTERN.sub(
        "[REDACTED_EMAIL]",
        value,
    )

    value = PHONE_PATTERN.sub(
        "[REDACTED_PHONE]",
        value,
    )

    value = BEARER_PATTERN.sub(
        lambda match: match.group(1) + REDACTED,
        value,
    )

    value = CREDENTIAL_PATTERN.sub(
        lambda match: match.group(1) + REDACTED,
        value,
    )

    return value


def sanitize_data(data: Any) -> Any:
    if isinstance(data, dict):
        sanitized = {}

        for key, value in data.items():
            if is_sensitive_key(key):
                sanitized[key] = REDACTED
            else:
                sanitized[key] = sanitize_data(value)

        return sanitized

    if isinstance(data, list):
        return [
            sanitize_data(item)
            for item in data
        ]

    if isinstance(data, str):
        return sanitize_text(data)

    return data
