"""Canonical absolute time: signed 64-bit Unix epoch microseconds.

Only external boundaries parse dates or seconds. Persisted values and comparisons
use integers; elapsed durations and monotonic deadlines are separate concepts.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal, DecimalException

MIN_EPOCH_US = -(1 << 63)
MAX_EPOCH_US = (1 << 63) - 1
MICROSECONDS_PER_SECOND = 1_000_000
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def validate_epoch_us(value: int) -> int:
    """Reject coercion (including bool) before an integer reaches storage."""
    if type(value) is not int:
        raise TypeError("An epoch timestamp must be an integer number of microseconds")
    if not MIN_EPOCH_US <= value <= MAX_EPOCH_US:
        raise ValueError("An epoch timestamp must fit in a signed 64-bit integer")
    return value


def now_us() -> int:
    return validate_epoch_us(time.time_ns() // 1_000)


def datetime_to_us(value: datetime) -> int:
    if not isinstance(value, datetime):
        raise TypeError("A timezone-aware datetime is required")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An absolute time must include a timezone")
    delta = value - _EPOCH
    return validate_epoch_us(
        (delta.days * 86_400 + delta.seconds) * MICROSECONDS_PER_SECOND
        + delta.microseconds
    )


def parse_iso8601_us(value: str) -> int:
    """Parse an offset-aware external ISO 8601 time without float arithmetic.

    Nonzero sub-microsecond digits are rejected instead of silently merging
    distinct observations. Additional zero digits do not change the instant.
    """
    if not isinstance(value, str):
        raise TypeError("An ISO 8601 timestamp must be a string")
    for fraction in re.findall(r"[.,](\d+)", value):
        if any(digit != "0" for digit in fraction[6:]):
            raise ValueError("Timestamp precision exceeds microseconds")
    return datetime_to_us(datetime.fromisoformat(value))


def format_iso8601_us(value: int) -> str:
    """Format supported calendar instants as fixed-width UTC ISO 8601.

    Integer storage supports all int64 values. A textual calendar conversion is
    bounded by Python datetime's year range and raises ValueError outside it.
    """
    validate_epoch_us(value)
    try:
        instant = _EPOCH + timedelta(microseconds=value)
    except OverflowError as cause:
        raise ValueError("Timestamp is outside the supported calendar range") from cause
    return instant.isoformat(timespec="microseconds").replace("+00:00", "Z")


def unix_seconds_to_us(value: int | float | str | Decimal) -> int:
    """Convert an external Unix-seconds value, flooring sub-microsecond parts.

    Decimal conversion uses the source's decimal representation, not binary
    floating-point multiplication. Raw external evidence remains unchanged.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise TypeError("Unix seconds must be a numeric value or decimal string")
    try:
        seconds = Decimal(str(value))
    except DecimalException as cause:
        raise ValueError("Invalid Unix-seconds timestamp") from cause
    if not seconds.is_finite():
        raise ValueError("Unix seconds must be finite")
    # Shift the exact decimal exponent without consulting Decimal's ambient
    # precision. Multiplication under the default context can round a value just
    # below an integer microsecond up before floor is applied.
    sign, digits, exponent = seconds.as_tuple()
    if not any(digits):
        return 0
    exponent += 6
    integer_digits = len(digits) + exponent
    if integer_digits > 19:
        raise ValueError("An epoch timestamp must fit in a signed 64-bit integer")
    if exponent >= 0:
        magnitude = int("".join(map(str, digits))) * 10**exponent
        fractional = False
    else:
        split = max(0, integer_digits)
        magnitude = int("".join(map(str, digits[:split])) or "0")
        fractional = any(digits[split:])
    micros = -magnitude - int(fractional) if sign else magnitude
    return validate_epoch_us(micros)
