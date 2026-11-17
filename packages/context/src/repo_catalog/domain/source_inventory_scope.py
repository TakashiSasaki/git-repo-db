"""Reserved Source inventory scope coordinates do not name a different owner."""

import json

from repo_catalog.domain.shared_values import encode, uuid4_value


class SourceInventoryScopeError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_source_inventory_scope(encoded, source, service=None):
    """Keep arbitrary captured scopes; qualify reserved keys when supplied.

    A DTO can check its Source coordinate before the owning service is available.
    Admission and stored authority validation additionally supply that service.
    Provenance is independent of these structural owner coordinates.
    """
    uuid4_value(source)
    if service is not None:
        uuid4_value(service)
    scope = json.loads(encoded)
    if encode(scope) != encoded:
        raise ValueError("canonical Source inventory scope required")
    if type(scope) is not dict:
        return
    for key, expected, code in (
        ("source_registration_uuidv4", source, "SOURCE_SCOPE"),
        ("service_instance_uuidv4", service, "SOURCE_SERVICE"),
    ):
        if key not in scope:
            continue
        try:
            uuid4_value(scope[key])
        except (TypeError, ValueError) as error:
            raise SourceInventoryScopeError(code) from error
        if expected is not None and scope[key] != expected:
            raise SourceInventoryScopeError(code)


def source_inventory_scope_sql(encoded, source, service):
    try:
        # SQL admission must have resolved the actual owning Source registration.
        uuid4_value(service)
        validate_source_inventory_scope(encoded, source, service)
        return 1
    except (ValueError, TypeError, RecursionError, OverflowError):
        return 0
