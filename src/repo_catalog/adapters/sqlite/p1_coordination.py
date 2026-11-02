"""Isolated P1 reference adapters; the normal CLI does not import this module.

Support: cooperating processes on POSIX local filesystems with flock and SQLite
WAL locking. Unsupported platforms fail explicitly. Network filesystems and
hostile/privileged writers are outside this boundary. P7 must implement fresh
restore/activation and complete power-loss durability; this is not that engine.
"""

from __future__ import annotations

from repo_catalog.adapters.sqlite.context_transaction import (
    AdmissionTransaction as AdmissionTransaction,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    ReadSnapshot as ReadSnapshot,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    SnapshotReadLimits as SnapshotReadLimits,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    apply_snapshot_read_limits as apply_snapshot_read_limits,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    catalog_completion as catalog_completion,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    catalog_gate as catalog_gate,
)
from repo_catalog.adapters.sqlite.core_coordination import (
    persist_catalog_stop as persist_catalog_stop,
)
from repo_catalog.adapters.sqlite.operational_coordination import (
    NotesWorkBudget as NotesWorkBudget,
)
from repo_catalog.adapters.sqlite.operational_coordination import (
    WorkLedger as WorkLedger,
)
from repo_catalog.adapters.sqlite.paired_admission import (
    PairCoordinator as PairCoordinator,
)
from repo_catalog.adapters.sqlite.paired_admission import (
    _ContextAdmissionBinding as _ContextAdmissionBinding,
)
from repo_catalog.adapters.sqlite.paired_coordination import (
    PairedSnapshot as PairedSnapshot,
)
from repo_catalog.adapters.sqlite.paired_coordination import (
    validate_dependencies as validate_dependencies,
)
from repo_catalog.adapters.sqlite.paired_coordination import (
    validate_pair as validate_pair,
)
from repo_catalog.adapters.sqlite.search_projection import (
    SearchProjection as SearchProjection,
)
from repo_catalog.domain.p1_coordination import AdmissionFailure as AdmissionFailure
from repo_catalog.domain.p1_coordination import CoordinationError as CoordinationError
from repo_catalog.domain.p1_coordination import PairAdmission as PairAdmission
from repo_catalog.domain.p1_coordination import SnapshotToken as SnapshotToken
