"""Bounded local CLI documents; explicit public DTO tags, never dynamic imports."""

from __future__ import annotations

import base64
import dataclasses
import enum
import importlib
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

MAX_BYTES = 32 * 1024 * 1024
DTO_MODULES = (
    "repo_catalog.domain.query_contracts",
    "repo_catalog.domain.shared_values",
    "repo_catalog.domain.p1_core",
    "repo_catalog.domain.ref_observation",
    "repo_catalog.domain.p1_context",
    "repo_catalog.domain.production_context",
    "repo_catalog.domain.provider_acquisition",
    "repo_catalog.domain.git_acquisition",
    "repo_catalog.domain.native_acquisition",
    "repo_catalog.domain.context_admission",
    "repo_catalog.domain.access_registry",
    "repo_catalog.domain.access_connections",
    "repo_catalog.domain.exchange",
    "repo_catalog.domain.p1_coordination",
    "repo_catalog.domain.recovery",
)


def read_document(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("INPUT_LIMIT")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("invalid JSON constant: " + value)

    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
    except RecursionError:
        raise ValueError("INPUT_LIMIT") from None
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > 48 or count > 200_000:
            raise ValueError("INPUT_LIMIT")
        if isinstance(item, dict):
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            pending.extend((v, depth + 1) for v in item)
    return value


@lru_cache(maxsize=1)
def _dto_registry():
    registry = {}
    for name in DTO_MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as error:
            if error.name == name:
                continue
            raise
        registry.update(
            {
                k: v
                for k, v in vars(module).items()
                if isinstance(v, type) and dataclasses.is_dataclass(v)
            }
        )
    return registry


@lru_cache(maxsize=256)
def _hints(cls):
    # Owner DTO annotations may import their optional peers only for type
    # checking. Resolve public forward references from the same finite registry
    # used for constructors, never from an input-selected module or eval scope.
    namespace = dict(vars(importlib.import_module(cls.__module__)))
    namespace.update(_dto_registry())
    try:
        return get_type_hints(cls, globalns=namespace, localns=namespace)
    except NameError:
        # Optional Context annotations must not require that capability for a
        # Core-only DTO invocation. Resolve each available owner annotation;
        # the typed constructor still rejects unavailable/invalid actual input.
        result = {}
        for member in dataclasses.fields(cls):
            probe = type(
                "PublicDTOAnnotation",
                (),
                {"__annotations__": {member.name: member.type}},
            )
            try:
                result.update(
                    get_type_hints(probe, globalns=namespace, localns=namespace)
                )
            except NameError:
                continue
        return result


def decode(value, expected=None):
    if isinstance(value, dict) and set(value) == {"$bytes"}:
        return base64.b64decode(value["$bytes"], validate=True)
    if isinstance(value, dict) and set(value) == {"$map"}:
        if type(value["$map"]) is not list or any(
            type(pair) is not list or len(pair) != 2 for pair in value["$map"]
        ):
            raise ValueError("typed map requires key/value pairs")
        pairs = [(decode(key), decode(item)) for key, item in value["$map"]]
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("duplicate typed map key")
        return result
    if isinstance(value, dict) and "$type" in value:
        if set(value) != {"$type", "fields"}:
            raise ValueError("typed DTO requires $type and fields")
        if type(value["$type"]) is not str or type(value["fields"]) is not dict:
            raise ValueError("typed DTO requires a type name and fields object")
        registry = _dto_registry()
        cls = registry.get(value["$type"])
        if cls is None:
            raise ValueError("unknown public DTO")
        public_fields = {
            member.name
            for member in dataclasses.fields(cls)
            if member.init and not member.name.startswith("_")
        }
        if set(value["fields"]) - public_fields:
            raise ValueError("only public DTO constructor fields may be supplied")
        hints = _hints(cls)
        return cls(**{k: decode(v, hints.get(k)) for k, v in value["fields"].items()})
    if isinstance(value, dict):
        return {k: decode(v) for k, v in value.items()}
    if isinstance(value, list):
        origin = get_origin(expected)
        args = get_args(expected)
        if origin not in (tuple, frozenset, list):
            for option in args:
                if get_origin(option) in (tuple, frozenset, list):
                    origin, args = get_origin(option), get_args(option)
                    break
        if origin is None and expected in (tuple, frozenset):
            origin = expected
        converted = [decode(v, args[0] if args else None) for v in value]
        return origin(converted) if origin in (tuple, frozenset) else converted
    return value


def encode(value):
    owner = type(value).__module__
    name = type(value).__name__
    if owner == "repo_catalog.domain.context_admission":
        if name == "AdmissionContext":
            raise ValueError("runtime admission authority is not a serializable result")
        if name == "AdmissionBudget":
            return {
                field: getattr(value, field)
                for field in (
                    "work_limit",
                    "bytes_limit",
                    "dependency_limit",
                    "depth_limit",
                    "used_work",
                    "used_bytes",
                    "used_dependencies",
                )
            }
    if dataclasses.is_dataclass(value):
        return {
            f.name: encode(getattr(value, f.name))
            for f in dataclasses.fields(value)
            if f.init and not f.name.startswith("_")
        }
    if isinstance(value, bytes):
        return {"$bytes": base64.b64encode(value).decode("ascii")}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            return {"$map": [[encode(k), encode(v)] for k, v in value.items()]}
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [encode(v) for v in value]
    return value


def emit(value):
    print(json.dumps(encode(value), sort_keys=True, ensure_ascii=True, allow_nan=False))


def failure(error):
    print(
        json.dumps(
            {
                "status": "error",
                "code": getattr(error, "code", "INVALID_ARGUMENT"),
                "error_type": type(error).__name__,
                "message": str(error),
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return 2


def authority(path, operation, selection=None):
    from repo_catalog.domain.context_admission import (
        AdmissionBudget,
        AdmissionSelection,
        DependencySet,
        create_local_admission_service,
    )

    document = read_document(path)
    grants = decode(document["grants"])
    if type(grants) is not DependencySet:
        raise ValueError("authority grants must be a tagged DependencySet")
    # Packet root selection and the locally supplied finite admission selection
    # have different responsibilities. Never replace explicit local target
    # authorization with an Exchange scope containing no resource roots.
    selected = decode(document["selection"]) if "selection" in document else selection
    if selected is None:
        raise ValueError("authority requires an explicit admission selection")
    if not isinstance(selected, AdmissionSelection):
        selected = AdmissionSelection.from_scope(selected)
    budget = decode(document["budget"]) if "budget" in document else AdmissionBudget()
    if operation == "exchange_export":
        from repo_catalog.application.identity_export import (
            create_identity_export_authority,
        )

        return create_identity_export_authority(
            grants=grants, selection=selected, budget=budget
        )
    return create_local_admission_service(
        operation, grants=grants, selection=selected, budget=budget
    )


def invocation(path):
    document = decode(read_document(path))
    if type(document) is not dict or set(document) - {"args", "kwargs"}:
        raise ValueError("invocation requires args and/or kwargs only")
    args, kwargs = document.get("args", []), document.get("kwargs", {})
    if type(args) not in (list, tuple) or type(kwargs) is not dict:
        raise ValueError("invocation args must be an array and kwargs an object")
    return tuple(args), kwargs
