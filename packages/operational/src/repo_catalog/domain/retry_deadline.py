"""Scheduling deadlines are independent of observation/Provider timestamps."""


def validate_retry_deadline_us(value: int | None) -> int | None:
    """None is absent; zero is an expired, genuine scheduling deadline."""
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError("A retry deadline must be an integer number of microseconds")
    if not 0 <= value < 2**63:
        raise ValueError("A retry deadline must be a nonnegative signed int64")
    return value
