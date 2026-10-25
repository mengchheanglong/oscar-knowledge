import ipaddress
from urllib.parse import urlsplit


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
