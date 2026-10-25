"""Deferred-COMMIT and missing-UDF controls outside the supported default profile."""
import json
import sqlite3
import sys
from pathlib import Path
from compose_proposal import compose, configure
from repo_catalog.domain.resource_identity import encode_identity as J

root=Path(__file__).resolve().parent
db=sqlite3.connect(':memory:',isolation_level=None)
configure(db);db.executescript(compose())
db.execute("INSERT INTO providers VALUES('aad25448-03eb-4f83-a578-ceec84375b5a','synthetic','{}')")
trace=[];db.set_trace_callback(trace.append)
db.execute('BEGIN');db.execute('PRAGMA defer_foreign_keys=ON')
db.execute("INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id) VALUES('5e7853d5-6002-4fb8-84ea-22a308614947','issue',?)",(J('7'),))
before=db.execute('SELECT * FROM resources').fetchall()
try:
    db.commit()
    raise AssertionError('deferred invalid FK committed')
except sqlite3.IntegrityError as error:
    commit={'message':str(error),'code':error.sqlite_errorcode,'name':error.sqlite_errorname,
            'in_transaction_after_failed_commit':db.in_transaction}
db.rollback()
after=db.execute('SELECT * FROM resources').fetchall()
assert before and not after
missing=sqlite3.connect(':memory:')
try:missing.executescript(compose());raise AssertionError('schema without UDF created')
except sqlite3.Error as error:
    missing_udf={'message':str(error),'code':error.sqlite_errorcode,'name':error.sqlite_errorname}
result={'scope':'explicit unsupported defer mode and absent-function controls; not normal write-path acceptance',
        'sqlite':sqlite3.sqlite_version,'source_id':db.execute('SELECT sqlite_source_id()').fetchone()[0],
        'before_commit':before,'commit_failure':commit,'after_rollback':after,
        'trace':trace,'missing_udf':missing_udf}
(root/sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
