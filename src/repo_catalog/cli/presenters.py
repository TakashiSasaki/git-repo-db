import base64
import dataclasses
import json

from repo_catalog.domain.models import Result, Waiting


def jsonable(value):
    if dataclasses.is_dataclass(value):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode()}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def envelope(command, request, result=None, error=None):
    r = result or Result()
    return {
        "schema_version": 1,
        "command": command,
        "status": (
            "partial"
            if isinstance(error, Waiting)
            else "cancelled"
            if error and error.code == "CANCELLED"
            else "error"
        )
        if error
        else r.status,
        "request": request,
        "catalog": r.catalog,
        "data": None if error else r.data,
        "coverage": None if error else r.coverage,
        "execution": {"completed": False, "timed_out": False, "backend": None}
        if error
        else r.execution,
        "warnings": r.warnings,
        "error": {
            "code": error.code,
            "message": str(error),
            "details": error.details,
            "retryable": error.retryable,
        }
        if error
        else None,
    }


def exit_code(result=None, error=None):
    if error:
        if isinstance(error, Waiting):
            return 3
        if error.code == "CANCELLED":
            return 130
        if error.code in ("INVALID_ARGUMENT", "CONFIG_ERROR", "PROFILE_UNSUPPORTED"):
            return 2
        if error.code in (
            "NOT_FOUND",
            "NOT_INITIALIZED",
            "RAW_CONTENT_UNAVAILABLE",
            "STALE_CURSOR",
            "JOB_RUNNING",
            "INDEX_UNAVAILABLE",
        ):
            return 4
        return 5
    return 3 if result.status == "partial" else 0


def render(payload, fmt):
    payload = jsonable(payload)
    output = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    if fmt == "json":
        return output

    def cell(value):
        # Escape terminal controls without changing the saved bytes or JSON DTO.
        text = json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            text = text[1:-1]
        return text if len(text) <= 80 else text[:77] + "..."

    lines = [f"{payload['command']}: {payload['status']}"]
    if payload["error"]:
        return "\n".join(
            lines + [json.dumps(payload["error"], ensure_ascii=True, indent=2)]
        )
    data = payload["data"] or {}
    if "items" not in data:
        return "\n".join(lines + [json.dumps(data, ensure_ascii=True, indent=2)])
    items = data["items"]
    columns = list(
        dict.fromkeys(
            key
            for item in items
            for key, value in item.items()
            if not isinstance(value, (dict, list))
        )
    )[:8]
    if items and columns:
        rows = [[cell(item.get(key)) for key in columns] for item in items]
        widths = [
            max(len(key), *(len(row[i]) for row in rows))
            for i, key in enumerate(columns)
        ]
        lines.append(
            " | ".join(key.ljust(width) for key, width in zip(columns, widths))
        )
        lines.append("-+-".join("-" * width for width in widths))
        lines.extend(
            " | ".join(value.ljust(width) for value, width in zip(row, widths))
            for row in rows
        )
    elif items:
        lines.extend(cell(item) for item in items)
    else:
        lines.append("0 items")
    lines.append(json.dumps(data["page"], ensure_ascii=True))
    if payload["coverage"] and not payload["coverage"]["complete_for_requested_scope"]:
        lines.append("coverage: " + json.dumps(payload["coverage"], ensure_ascii=True))
    return "\n".join(lines)
