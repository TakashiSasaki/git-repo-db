"""Canonical explicit request scope shared by durable accounting and acquisition."""


def request_scope(
    repository_uuidv4, catalog_instance_uuidv4, source_attribution, source_scope
):
    """Exact explicit Notes request intent, independent of per-attempt limits."""
    from repo_catalog.domain.shared_values import CoreFailure, encode, uuid4_value

    uuid4_value(repository_uuidv4)
    uuid4_value(catalog_instance_uuidv4)
    if not source_attribution or not source_scope:
        raise CoreFailure(
            "NOTES_SCOPE", "request", "actual source attribution/scope required"
        )
    return encode(
        [
            repository_uuidv4,
            catalog_instance_uuidv4,
            source_attribution,
            "p4-notes/1",
            source_scope,
        ]
    )
