"""Execute F1-reproduction.sql after installing the exact candidate and UDFs.

PYTHONPATH must contain the frozen repo's src and author-rerun directory.
LD_LIBRARY_PATH must select one of the newly built actual SQLite libraries.
"""
import json,pathlib,sqlite3
from compose_proposal import compose,configure
from repo_catalog.adapters.sqlite.p1_context import ContextStore
b=pathlib.Path(__file__).resolve().parent
db=sqlite3.connect(':memory:',isolation_level=None);configure(db);db.executescript(compose())
db.executescript((b/'F1-reproduction.sql').read_text())
result={'runtime':db.execute('SELECT sqlite_version(),sqlite_source_id()').fetchone(),
        'issue_count':db.execute("SELECT count(*) FROM resources WHERE resource_kind='issue'").fetchone()[0],
        'endpoint_count':db.execute('SELECT count(*) FROM resource_repository_relations').fetchone()[0],
        'transfer_report_count':db.execute("SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'").fetchone()[0],
        'typed_reports':[{'event':r.event_resource.coordinates(),'from_state':r.from_state} for r in ContextStore(db).transfer_event_reports()],
        'foreign_key_check':db.execute('PRAGMA foreign_key_check').fetchall(),
        'integrity_check':db.execute('PRAGMA integrity_check').fetchall()}
print(json.dumps(result,indent=2))
raise SystemExit(1 if result['transfer_report_count'] else 0)
