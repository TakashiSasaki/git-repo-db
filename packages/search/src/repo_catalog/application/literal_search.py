"""Literal acceptance uses original bytes; display escaping never supplies a hit."""

import base64

RAW_SEGMENTS = "_literal_source_bytes"


def safe_text(value):
    return value.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def literal_summary(text, summary, query, work):
    if query not in text:
        return None
    segments = summary.get(RAW_SEGMENTS)
    public = {key: value for key, value in summary.items() if key != RAW_SEGMENTS}
    if segments is None:
        return public
    needle = query.encode("utf-8")
    for raw in segments:
        work.require("verification_bytes", len(raw))
        work.charge("verification_bytes", len(raw))
        start = raw.find(needle)
        if start >= 0:
            encoded_size = 4 * ((len(raw) + 2) // 3)
            work.require("input_bytes", encoded_size)
            encoded = base64.b64encode(raw).decode("ascii")
            work.charge("input_bytes", len(encoded))
            public["literal_match"] = {
                "byte_start": start,
                "byte_end": start + len(needle),
                "line": 1 + raw[:start].count(b"\n"),
                "source_bytes": {"$bytes": encoded},
            }
            return public
    return None
