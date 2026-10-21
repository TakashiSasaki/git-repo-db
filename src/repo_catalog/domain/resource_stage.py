"""I2 staging limits. Remove fences only with reviewed I3--I5 and routing."""

TRANSFER_NAMES = frozenset(
    {"transfer_event_report", "transfer_from_repository", "transfer_to_repository"}
)


class UnsupportedResourceStage(ValueError):
    code = "I2_TRANSFER_UNSUPPORTED"

    def __init__(self, operation="Transfer"):
        self.scope = operation
        super().__init__(f"{self.code}: {operation} requires reviewed I3-I5 support")


class UnsupportedIdentificationStage(ValueError):
    code = "I2_IDENTIFICATION_WIRE_UNSUPPORTED"

    def __init__(self):
        self.scope = "resource_identification"
        super().__init__(f"{self.code}: explicit identification wire requires I6")


def refuse_transfer(name):
    if name in TRANSFER_NAMES:
        raise UnsupportedResourceStage(name)


def preflight_transfer(value):
    """Visit decoded selected operations, not arbitrary strings in payloads.

    The real envelope/parser performs wire/digest validation first. Structural
    operation names alone have meaning; payload text containing Transfer does not.
    """
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for field in ("relation_kind", "operation", "unit_kind"):
                name = item.get(field)
                if isinstance(name, str):
                    refuse_transfer(name)
            if item.get("transfer_event") is True:
                raise UnsupportedResourceStage()
            pending.extend(
                item[key]
                for key in (
                    "units",
                    "operations",
                    "reports",
                    "endpoints",
                    "resource_relations",
                    "resource_repository_relations",
                )
                if key in item and isinstance(item[key], (dict, list, tuple))
            )
        elif isinstance(item, (list, tuple)):
            pending.extend(item)


def validate_stage_storage(db):
    """Minimal enduring I2 invariant, following trusted schema validation."""
    if (
        db.execute(
            "SELECT 1 FROM resource_relations WHERE relation_kind COLLATE BINARY='transfer_event_report' LIMIT 1"
        ).fetchone()
        or db.execute(
            "SELECT 1 FROM resource_repository_relations WHERE relation_kind COLLATE BINARY IN('transfer_from_repository','transfer_to_repository') LIMIT 1"
        ).fetchone()
    ):
        raise ValueError("reserved Transfer storage is impossible at I2")
