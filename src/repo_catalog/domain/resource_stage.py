"""I2 staging limits. Both exact fences remain until reviewed retirement."""

from contextlib import contextmanager
from contextvars import ContextVar

# SQLite retains CREATE statements without their terminating semicolon. These
# domain guard definitions are checked against the packaged schema in T19.
TRANSFER_FENCE_DEFINITIONS = (
    (
        "trigger",
        "i2_transfer_report_stage_fence",
        "resource_relations",
        "CREATE TRIGGER i2_transfer_report_stage_fence BEFORE INSERT ON resource_relations\n"
        "WHEN NEW.relation_kind COLLATE BINARY='transfer_event_report'\n"
        "BEGIN SELECT RAISE(ABORT,'I2_TRANSFER_UNSUPPORTED'); END",
    ),
    (
        "trigger",
        "i2_transfer_stage_fence",
        "resource_repository_relations",
        "CREATE TRIGGER i2_transfer_stage_fence BEFORE INSERT ON resource_repository_relations\n"
        "WHEN NEW.relation_kind COLLATE BINARY IN('transfer_from_repository','transfer_to_repository')\n"
        "BEGIN SELECT RAISE(ABORT,'I2_TRANSFER_UNSUPPORTED'); END",
    ),
)


class UnsupportedTransferSchema(RuntimeError):
    code = "UNSUPPORTED_SCHEMA"

    def __init__(self, detail="both exact Transfer fences required"):
        self.scope = "context"
        super().__init__(f"{self.code}: {detail}")


_isolated_fixtures = ContextVar("isolated_transfer_fixtures", default=())


class _IsolatedTransferFixtureConnection:
    """Expiring connection identity; only the tests-only factory creates it."""

    def __init__(self, connection):
        self._connection = connection
        self._active = True

    def __getattr__(self, name):
        if not self._active:
            raise UnsupportedTransferSchema("isolated fixture capability expired")
        return getattr(self._connection, name)


def is_isolated_transfer_fixture(db) -> bool:
    """Recognize only the scoped wrapper, including trusted guarded connections."""
    seen = set()
    while id(db) not in seen:
        seen.add(id(db))
        if isinstance(db, _IsolatedTransferFixtureConnection):
            return db._active and any(
                db is fixture for fixture in _isolated_fixtures.get()
            )
        db = getattr(db, "_connection", None)
        if db is None:
            return False
    return False


@contextmanager
def _isolated_transfer_fixture(db):
    """Private test capability for a fresh in-memory DB, never a disk catalog.

    The tests-only factory verifies the complete packaged schema and connection
    profile before dropping exactly the two fences. Merely removing them from a
    raw connection never supplies this expiring capability.
    """
    databases = tuple(tuple(row) for row in db.execute("PRAGMA database_list"))
    if not databases or any(
        row[2] or row[1] not in ("main", "temp") for row in databases
    ):
        raise UnsupportedTransferSchema(
            "isolated fixture requires an in-memory database"
        )
    fixture = _IsolatedTransferFixtureConnection(db)
    token = _isolated_fixtures.set((*_isolated_fixtures.get(), fixture))
    try:
        yield fixture
    finally:
        fixture._active = False
        _isolated_fixtures.reset(token)


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


def has_transfer_fence(db) -> bool:
    """Return staged only for both exact definitions; all other states refuse.

    Both absent is supported solely on the explicit isolated fixture capability.
    No incomplete, altered or unreadable schema enables a Transfer operation.
    """
    try:
        rows = tuple(
            tuple(row)
            for row in db.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_schema "
                "WHERE name IN('i2_transfer_stage_fence','i2_transfer_report_stage_fence') "
                "ORDER BY name"
            )
        )
    except Exception as error:
        # Preserve lifecycle/recovery failures raised by guarded connections.
        # SQLite's stable primary CORRUPT (11) and NOTADB (26) codes must also
        # reach the adapter's existing authoritative-corruption handling.
        if getattr(error, "code", None) is not None or (
            (getattr(error, "sqlite_errorcode", 0) or 0) & 255 in (11, 26)
        ):
            raise
        raise UnsupportedTransferSchema(
            "Transfer fence definitions cannot be inspected"
        ) from error
    if rows == TRANSFER_FENCE_DEFINITIONS:
        return True
    if not rows and is_isolated_transfer_fixture(db):
        return False
    raise UnsupportedTransferSchema()


def validate_stage_storage(db):
    """Minimal enduring I2 invariant, following trusted schema validation."""
    if not has_transfer_fence(db):
        return
    if (
        db.execute(
            "SELECT 1 FROM resource_relations WHERE relation_kind COLLATE BINARY='transfer_event_report' LIMIT 1"
        ).fetchone()
        or db.execute(
            "SELECT 1 FROM resource_repository_relations WHERE relation_kind COLLATE BINARY IN('transfer_from_repository','transfer_to_repository') LIMIT 1"
        ).fetchone()
    ):
        raise ValueError("reserved Transfer storage is impossible at I2")
