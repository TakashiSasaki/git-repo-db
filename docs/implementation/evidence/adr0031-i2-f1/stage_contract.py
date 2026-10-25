"""Executable design model ONLY; this is not a product API or Exchange parser.

Inputs are already normalized, version/digest/permission/selection-validated
Context operations. Product integration must add the same guards to all real
entry points; importing this model in a test does not implement those paths.
"""
from dataclasses import dataclass

TRANSFER_ROLES = frozenset(('transfer_from_repository', 'transfer_to_repository'))
TRANSFER_REPORT = 'transfer_event_report'


class StageUnsupported(ValueError):
    code = 'I2_TRANSFER_UNSUPPORTED'


class StageStoredViolation(ValueError):
    code = 'I2_STORED_TRANSFER_INVARIANT'


@dataclass(frozen=True)
class Operation:
    family: str  # relation, endpoint, or typed_transfer
    row: tuple = ()


def preflight(operation):
    if operation.family == 'typed_transfer':
        raise StageUnsupported('Transfer Admission requires the reviewed I3-I5 stack')
    if operation.family not in ('relation', 'endpoint'):
        raise ValueError('Unknown normalized operation family; no generic fallback')
    kind = operation.row[3]
    if (operation.family == 'relation' and kind == TRANSFER_REPORT) or (
            operation.family == 'endpoint' and kind in TRANSFER_ROLES):
        raise StageUnsupported('Transfer representation is unavailable during I2')


def validate_stage_storage(db):
    """After trusted schema/config checks, before ordinary domain reads/exports.

    Product integration must use existing invariant/recovery handling, not delete
    or hide rows. This model does not implement ADR 0026 recovery.
    """
    report = db.execute("SELECT 1 FROM resource_relations WHERE relation_kind='transfer_event_report' LIMIT 1").fetchone()
    endpoint = db.execute("SELECT 1 FROM resource_repository_relations WHERE relation_kind IN('transfer_from_repository','transfer_to_repository') LIMIT 1").fetchone()
    if report or endpoint:
        raise StageStoredViolation('Reserved Transfer rows cannot exist in the staged format')


class StagedContextPrototype:
    """Small testable routing contract; not a substitute for the product facade."""

    def __init__(self, db):
        self.db = db

    def admit(self, operation):
        preflight(operation)
        if operation.family == 'relation':
            return self.db.execute('INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)', operation.row)
        return self.db.execute('INSERT INTO resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)', operation.row)

    def import_selected(self, operations, *, duplicate=False):
        # Preflight the WHOLE selected transaction before any Resource/ledger or
        # relation effect and before a package/unit replay shortcut.
        operations = tuple(operations)
        for operation in operations:
            preflight(operation)
        validate_stage_storage(self.db)
        if duplicate:
            return 'duplicate'
        self.db.execute('SAVEPOINT c_f1_import')
        try:
            for operation in operations:
                self.admit(operation)
            self.db.execute('RELEASE c_f1_import')
        except BaseException:
            self.db.execute('ROLLBACK TO c_f1_import')
            self.db.execute('RELEASE c_f1_import')
            raise
        return 'admitted'

    def transfer_event_reports(self):
        # Refuse even on an empty store, rather than claiming supported emptiness.
        raise StageUnsupported('Transfer query is unavailable during I2')

    def relations(self, kind=None):
        if kind == TRANSFER_REPORT:
            raise StageUnsupported('Transfer report query is unavailable during I2')
        validate_stage_storage(self.db)
        return self.db.execute('SELECT * FROM resource_relations WHERE (? IS NULL OR relation_kind=?) ORDER BY 1,2,3,4,5,6,7', (kind, kind)).fetchall()

    def export_selected(self, operations):
        # Models routing after real bounded selection; not wire serialization.
        operations = tuple(operations)
        for operation in operations:
            preflight(operation)
        validate_stage_storage(self.db)
        return operations
