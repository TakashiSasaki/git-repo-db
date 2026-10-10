"""Small SQLite units, including nested rollback and failed COMMIT cleanup."""

import uuid
from contextlib import contextmanager


@contextmanager
def atomic_unit(db):
    savepoint = "unit_" + uuid.uuid4().hex if db.in_transaction else None
    db.execute(f"SAVEPOINT {savepoint}" if savepoint else "BEGIN IMMEDIATE")
    try:
        yield
        db.execute(f"RELEASE {savepoint}" if savepoint else "COMMIT")
    except BaseException as error:
        try:
            if db.in_transaction:
                if savepoint:
                    db.execute(f"ROLLBACK TO {savepoint}")
                    db.execute(f"RELEASE {savepoint}")
                else:
                    db.execute("ROLLBACK")
        except BaseException as cleanup_error:
            error.add_note(
                "Transaction cleanup failed: " + type(cleanup_error).__name__
            )
            # Retire a connection whose rollback cannot be completed.
            try:
                db.close()
            except BaseException as close_error:
                error.add_note(
                    "Connection retirement failed: " + type(close_error).__name__
                )
        raise
