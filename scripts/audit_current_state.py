"""Read-only current separated-role inventory; historical receipts stay pinned.

The old normal-format comparison driver has retired. This command uses the
current role catalogue and records lexical source limits without retained DBs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_phase2_dependencies import main

if __name__ == "__main__":
    main()
