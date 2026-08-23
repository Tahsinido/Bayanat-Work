"""One-time verification codes for approved file downloads.

An admin approving a download does not hand over the file: it mints a code that
is shown to the admin once and passed to the requester out of band. The file is
only served when that code comes back. Two people are therefore involved in
every release of a file, and the code travels on a different channel from the
session that will use it.

The code is stored hashed, exactly like a password -- an admin browsing the
database, or a database backup, must not be enough to unlock a download.

Brute force is contained on three sides: the alphabet is large enough that
guessing is hopeless (32^8, ~1.1e12), attempts are capped per request, and the
code expires minutes after it is issued.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash

from enferno.utils.date_helper import DateHelper
from enferno.utils.logging_utils import get_logger

logger = get_logger()

# No 0/O/1/I/L: these codes get read aloud over a phone or radio, and a code
# that cannot be dictated unambiguously is a support ticket waiting to happen.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

DEFAULT_CODE_LENGTH = 8
DEFAULT_CODE_TTL_MINUTES = 15
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_REQUEST_EXPIRY_HOURS = 24


def _setting(key: str, default, cast):
    """Read a tunable from app settings, falling back to the default."""
    try:
        from enferno.settings import Config

        value = Config.get(key, None)
    except Exception:
        value = None
    if value is None or value == "":
        return default
    try:
        return cast(value)
    except (TypeError, ValueError):
        logger.warning(f"Invalid {key}={value!r}, falling back to {default}")
        return default


def approval_enabled() -> bool:
    """Whether downloads require an approved request and a verified code."""
    value = _setting("DOWNLOAD_APPROVAL_ENABLED", True, bool)
    return bool(value)


def code_length() -> int:
    return max(6, min(_setting("DOWNLOAD_CODE_LENGTH", DEFAULT_CODE_LENGTH, int), 32))


def code_ttl() -> timedelta:
    minutes = max(1, _setting("DOWNLOAD_CODE_TTL_MINUTES", DEFAULT_CODE_TTL_MINUTES, int))
    return timedelta(minutes=minutes)


def max_attempts() -> int:
    return max(1, _setting("DOWNLOAD_CODE_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS, int))


def request_expiry() -> timedelta:
    hours = max(1, _setting("DOWNLOAD_REQUEST_EXPIRY_HOURS", DEFAULT_REQUEST_EXPIRY_HOURS, int))
    return timedelta(hours=hours)


def generate_code() -> str:
    """A fresh code in `XXXX-XXXX` form.

    Grouped for readability when it is dictated; the separator is cosmetic and
    stripped before comparison, so a user may type it either way.
    """
    length = code_length()
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))
    return "-".join(raw[i : i + 4] for i in range(0, length, 4))


def normalize(code: Optional[str]) -> str:
    """Strip formatting so display grouping and case never cause a false reject."""
    if not code:
        return ""
    return "".join(ch for ch in str(code).upper() if ch in CODE_ALPHABET)


def hash_code(code: str) -> str:
    """Hash a code for storage. Never store the plaintext."""
    return generate_password_hash(normalize(code))


def check_code(code: str, code_hash: Optional[str]) -> bool:
    """Constant-time comparison of a submitted code against the stored hash."""
    if not code_hash:
        return False
    candidate = normalize(code)
    if not candidate:
        return False
    try:
        return check_password_hash(code_hash, candidate)
    except Exception as e:
        logger.error(f"Download code verification failed: {e}")
        return False


def code_expiry_from_now():
    """When a code issued right now stops working."""
    return DateHelper.utcnow() + code_ttl()


def request_expiry_from_now():
    """When an approval granted right now stops being usable."""
    return DateHelper.utcnow() + request_expiry()
