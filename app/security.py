import ipaddress
import base64
import hashlib
import hmac
import json
import time
import uuid
from urllib.parse import urlsplit


def private_subject(assertion: str | None, body: bytes, secret: str) -> str:
    """A separate backend signing key binds subject, audience, TTL and exact body.

    The service bearer token and client-supplied owner IDs never grant private scope.
    """
    try:
        if len(secret) < 32 or not assertion or len(assertion) > 2048:
            raise ValueError()
        payload, signature = assertion.split(".")
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        now = int(time.time())
        if (
            data["aud"] != "oscar-knowledge-private-v1"
            or not now - 5 <= data["iat"] <= now + 5
            or not now <= data["exp"] <= data["iat"] + 30
            or not hmac.compare_digest(data["body_sha256"], hashlib.sha256(body).hexdigest())
        ):
            raise ValueError()
        return str(uuid.UUID(data["sub"]))
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        raise PermissionError("PRIVATE_SCOPE_REQUIRED") from None


def public_source_url(value: str | None) -> str | None:
    """Only public HTTPS citation URLs, without credentials, queries or fragments."""
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return None
        host = parsed.hostname.lower()
        if "." not in host or host.endswith((".local", ".internal", ".localhost")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        if parsed.port not in (None, 443):
            return None
        return f"https://{host}{parsed.path}"
    except ValueError:
        return None
