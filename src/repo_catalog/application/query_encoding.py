"""Finite metadata encoding, independent of acquisition orchestration."""

from repo_catalog.domain.shared_values import CoreFailure, encode


def _charge(work, unit, amount):
    work.require(unit, amount)
    work.charge(unit, amount)


def encode_metered(work, value, limit=64 * 1024 * 1024):
    """Reserve a finite conservative bound before encoding caller metadata."""
    pending = [value]
    upper = 0
    nodes = 0
    scheduled = 1
    _charge(work, "metadata_units", 1)
    while pending:
        item = pending.pop()
        nodes += 1
        if nodes > 1_000_000:
            raise CoreFailure("BUDGET", "encoding", "finite value count")
        if isinstance(item, str):
            upper += 2 + 12 * len(item)
        elif isinstance(item, (tuple, list)):
            upper += 2 + len(item)
            scheduled += len(item)
            if scheduled > 1_000_000:
                raise CoreFailure("BUDGET", "encoding", "finite value count")
            _charge(work, "metadata_units", len(item))
            pending.extend(item)
        elif isinstance(item, dict):
            upper += 2 + 2 * len(item)
            scheduled += 2 * len(item)
            if scheduled > 1_000_000:
                raise CoreFailure("BUDGET", "encoding", "finite value count")
            _charge(work, "metadata_units", 2 * len(item))
            for key, child in item.items():
                if not isinstance(key, str):
                    raise CoreFailure("REQUEST", "encoding", "text keys required")
                pending.extend((key, child))
        elif item is None or type(item) is bool:
            upper += 5
        elif type(item) is int and -(2**63) <= item < 2**63:
            upper += 21
        else:
            raise CoreFailure("REQUEST", "encoding", "bounded JSON values required")
        if upper > limit:
            raise CoreFailure("BUDGET", "encoding", "finite metadata encoding limit")
    work.require("input_bytes", upper)
    try:
        result = encode(value)
    except BaseException:
        abandon = getattr(work, "abandon", None)
        if abandon:
            abandon("input_bytes")
        else:
            work.charge("input_bytes", upper)
        raise
    work.charge("input_bytes", len(result))
    return result
