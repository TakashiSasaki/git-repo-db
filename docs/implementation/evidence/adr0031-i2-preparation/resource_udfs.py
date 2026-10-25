"""Disposable I2 proposal. No product file imports this module.

Reuse the exact I1 codec; predicates never query a connection or external source.
"""
from repo_catalog.domain.resource_identity import encode_identity, parse_identity

SCOPED = {
    "review": {"pull_request"},
    "comment": {"pull_request", "issue", "review", "thread"},
    "thread": {"pull_request", "review"},
    "document": {"pull_request"},
}


def identity_text(raw):
    try:
        parse_identity(raw)
        return 1
    except (TypeError, ValueError):
        return 0


def validate_identification(kind, raw, namespace_kind, namespace_id, subtype, local):
    if type(kind) is not str or not kind:
        raise ValueError("nonempty exact kind TEXT required")
    parse_identity(raw)
    metadata = (namespace_kind, namespace_id, subtype, local)
    if kind == "document" and all(x is None for x in metadata[:3]):
        # Complete explicit global contract, including a global that looks scoped.
        parse_identity(local)
        if local != raw:
            raise ValueError("global native ID must repeat the complete identity")
    elif kind in SCOPED:
        if (type(namespace_kind) is not str or namespace_kind not in SCOPED[kind]
                or type(subtype) is not str or not subtype):
            raise ValueError("reserved scoped identification contract")
        parse_identity(namespace_id)
        native_local = parse_identity(local)
        if raw != encode_identity([namespace_kind, namespace_id, subtype, native_local]):
            raise ValueError("identifying coordinates do not reconstruct the key")
    elif any(x is not None for x in metadata):
        raise ValueError("unscoped kind cannot claim known scoped metadata")


def identification(*args):
    try:
        validate_identification(*args)
        return 1
    except (TypeError, ValueError):
        return 0


def register(db):
    db.create_function("p1_resource_identity_v1", 1, identity_text, deterministic=True)
    db.create_function("p1_resource_identification_v1", 6, identification, deterministic=True)
