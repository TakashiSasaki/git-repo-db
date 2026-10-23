"""Select exactly the completed full invocation's actual UV cache failures."""
from collections import Counter
import gzip
import json
from pathlib import Path
import sys

import audit

OUT=Path(__file__).resolve().parent
full,receipt=audit.receipt(Path(sys.argv[1]).resolve())
expected,archived=audit.receipt(audit.E/'after-final')
assert set(full)==set(expected)
blocked={n:r for n,r in full.items() if r.get('uv_cache_error')}
differences=[{'nodeid':n,'actual':r,'archived':expected[n],'uv_cache_error':bool(r.get('uv_cache_error'))} for n,r in full.items() if r['outcome']!=expected[n]['outcome'] or r['phase']!=expected[n]['phase']]
summary={'raw_ordinary_receipt':receipt,'uv_cache_error_count':len(blocked),'uv_cache_error_nodes':sorted(blocked),'different_outcome_or_phase_count':len(differences),'non_cache_differences':[r for r in differences if not r['uv_cache_error']],'cache_error_previous_outcomes':dict(Counter(expected[n]['outcome'] for n in blocked)),'scope':'Select solely actual read-only UV cache failures from the completed raw ordinary invocation. No counts are rewritten and no test is treated as product-passing here.'}
(OUT/'full-cache-blocked-nodeids.json').write_text(json.dumps(sorted(blocked),indent=2)+'\n')
(OUT/'full-raw-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(OUT/'full-raw-differences.json.gz').write_bytes(gzip.compress(json.dumps(differences,indent=2).encode(),mtime=0))
print(json.dumps(summary,indent=2))
