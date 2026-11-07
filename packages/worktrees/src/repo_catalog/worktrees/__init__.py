"""Independent worktree topology API; no concrete sibling catalog imports."""

from .catalog import WorktreeCatalog
from .git import discover_topology
from .models import DiscoveryResult, WorktreeEntry, WorktreeError

__all__ = [
    "DiscoveryResult",
    "WorktreeCatalog",
    "WorktreeEntry",
    "WorktreeError",
    "discover_topology",
]
