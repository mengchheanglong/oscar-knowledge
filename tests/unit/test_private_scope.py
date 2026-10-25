import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest

from app.security import private_subject

SECRET = "independent-private-scope-test-key-123456789"


def sign(body=b"{}", **extra):
    now = int(time.time())
    data = {
        "aud": "oscar-knowledge-private-v1",
        "iat": now,
        "exp": now + 30,
        "sub": str(uuid.uuid4()),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        **extra,
    }
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
    return payload + "." + hmac.new(
        SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest(), data


def test_trusted_subject_and_body_binding():
    assertion, claims = sign()
    assert private_subject(assertion, b"{}", SECRET) == claims["sub"]
    for token, body, key in [
        (None, b"{}", SECRET),
        (assertion, b'{"owner_id":"someone"}', SECRET),
        (assertion, b"{}", "service-token-only"),
        (assertion + "x", b"{}", SECRET),
    ]:
        with pytest.raises(PermissionError):
            private_subject(token, body, key)


@pytest.mark.parametrize(
    "claims", [{"exp": 0}, {"iat": 0}, {"aud": "other"}, {"sub": "not-a-user"}]
)
def test_invalid_or_expired_claims(claims):
    assertion, _ = sign(**claims)
    with pytest.raises(PermissionError):
        private_subject(assertion, b"{}", SECRET)
