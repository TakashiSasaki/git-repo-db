import fcntl
import os
from pathlib import Path

from repo_catalog.domain.models import Waiting


class FileLock:
    def __init__(self, path, *, inheritable=False):
        self.path = Path(path)
        self.inheritable = inheritable
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close()
            raise Waiting(
                "WRITER_BUSY",
                "A process still owns this state/cache lock",
                retryable=True,
            )
        os.set_inheritable(self.file.fileno(), self.inheritable)
        return self

    def __exit__(self, *exc):
        # close, rather than LOCK_UN: inherited child FDs must keep the lock alive.
        self.file.close()

    @property
    def fd(self):
        return self.file.fileno()
