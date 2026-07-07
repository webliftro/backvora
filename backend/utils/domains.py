"""
Shared domain name normalization helpers.

Single source of truth for hostname cleanup and root-domain extraction —
import from here instead of redefining per router.
"""

from urllib.parse import urlparse


def normalize_domain(value: str) -> str:
    """Normalize a user/CSV-provided domain or URL to a bare lowercase hostname.

    "HTTPS://WWW.Example.com/path" -> "example.com"
    """
    name = (value or "").strip().lower()
    if name.startswith(("http://", "https://")):
        try:
            name = urlparse(name).netloc
        except ValueError:
            name = name.split("//", 1)[-1]
    name = name.split("/")[0].split("?")[0].split(":")[0]
    if name.startswith("www."):
        name = name[4:]
    return name


def extract_root_domain(domain: str) -> str:
    """Extract root domain from a subdomain. blog.domain.com → domain.com"""
    parts = domain.lower().strip().split(".")
    # Handle common TLDs: .co.uk, .com.br, etc.
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "edu", "gov", "ac"):
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return domain.lower().strip()
