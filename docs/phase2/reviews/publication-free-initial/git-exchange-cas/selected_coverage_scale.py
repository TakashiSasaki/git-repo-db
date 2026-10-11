"""Independent same-scope unrelated coverage-history growth probe."""
import json
import pathlib
import sqlite3
import sys
import repo_catalog
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.coverage import admit_claim
from tests.integration.test_catalog3_exchange import catalog, fixture, complete_collection, uid

def measure(db, operation):
    ticks = 0
    statements = []
    def tick():
        nonlocal ticks
        ticks += 1
        return 0
    db.set_progress_handler(tick, 1)
    db.set_trace_callback(statements.append)
    try:
        unit = operation()
    finally:
        db.set_progress_handler(None, 0)
        db.set_trace_callback(None)
    return ticks, statements, unit

db = catalog()
owner = fixture(db)
complete_collection(db, owner['collection'])
scope = uid()
db.execute("INSERT INTO coverage_scopes VALUES(?,?,?,'pr-body')", (scope, owner['repository'], owner['cr']))
marker = db.execute('SELECT completion_marker_uuidv4 FROM completion_markers WHERE fetch_collection_id=?', (owner['collection'],)).fetchone()[0]
admit_claim(db, scope, 'complete', 1, json.dumps({'completion_marker_uuidv4s':[marker]}))
def export():
    return Graph(db, persist_identities=False).export(owner['repository'], fetch_collection_id=owner['collection'])
measurements=[]
baseline = None
for total in (0,1000,5000):
    previous = measurements[-1]['unrelated_claims'] if measurements else 0
    with db:
        for index in range(previous,total):
            assert admit_claim(db, scope, 'partial', index+2, '{}') is not None
    steps, statements, unit = measure(db,export)
    if baseline is None:
        baseline=unit['records']
    measurements.append({'unrelated_claims':total,'vm_steps':steps,'statements':len(statements),'records':len(unit['records']),'records_identical':baseline==unit['records']})
query='SELECT * FROM coverage_claims WHERE coverage_scope_id IS ?'
result={'python':sys.version,'sqlite':sqlite3.sqlite_version,'repo_catalog':repo_catalog.__file__,'measurements':measurements,'claim_lookup_plan':[list(r) for r in db.execute('EXPLAIN QUERY PLAN '+query,(scope,))]}
print(json.dumps(result,indent=2))
pathlib.Path('/workspace/review-artifacts/git-exchange-cas/selected_coverage_scale.json').write_text(json.dumps(result,indent=2)+'\n')
