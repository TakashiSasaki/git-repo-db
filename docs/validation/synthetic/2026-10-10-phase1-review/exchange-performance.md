# Exchange performance evidence

The continuation used Python 3.12.14, SQLite 3.53.1, uv 0.12.19 and Git 2.52.0 on Linux x86_64. Both revisions used the same interpreter and synthetic setup. Setup was excluded from measurement. These are single measurements; SQL statements and Python allocation peak substantiate the scaling behavior. Process RSS, hardware power-loss behavior and live providers were not measured.

Initial PR #20 commit: `f9bff8b2dc17ddffd6b3f7662791022f25175c44`. Corrected Exchange SHA-256: `d142d7689272ba869fdb56c33539750efc665bc831c5623ced58a6ee7ddaa103`. The [raw comparison](exchange-performance-comparison.json) preserves the values.

| Unrelated objects | Initial PR #20 | Corrected |
| --- | --- | --- |
| 1,000 Git blobs | 0.6540s; 10,224 statements; 9.076 MiB Python peak | 0.0188s; 224 statements; 0.605 MiB |
| 5,000 Git blobs | 3.3088s; 50,224 statements; 44.854 MiB Python peak | 0.0095s; 224 statements; 0.221 MiB |
| 50,000 unrelated receipts | 0.3577s; 50,000 context rows; 24.167 MiB Python peak | 0.0006s; zero context rows; 0.016 MiB |

The corrected context derives Git roots from the selected repository or exact digest, walks indexed required receipt keys, and groups pending promotion by repository from one snapshot. Valid missing dependencies and proof checks remain. Regression tests use 4,096 real Git blobs in two unrelated repositories, 12,000 unrelated receipt rows, and 24 repositories with staged inputs. They bound SQL work and forbid global receipt materialization; no performance deadline was extended.

## Continuation harness

Run this code with the same virtual-environment Python and `PYTHONPATH` selecting each immutable revision. It uses only fresh in-memory catalogs:

```python
import hashlib, json, sqlite3, time, tracemalloc, uuid
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.adapters.sqlite.exchange import Graph


def uid():
    return str(uuid.uuid4())


def make_db(objects, admissions):
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    db.executescript(schema_sql())
    target, other = uid(), uid()
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'target','{}')",
        (target,),
    )
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'other','{}')",
        (other,),
    )
    acquisition = uid()
    db.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request) VALUES(?,?,'sha1','git','{}')",
        (acquisition, other),
    )
    db.execute("BEGIN")
    for i in range(objects):
        body = f"synthetic-object-{i:08d}".encode()
        oid = hashlib.sha1(f"blob {len(body)}\0".encode() + body).digest()
        digest = hashlib.sha256(body).digest()
        db.execute("INSERT INTO stored_bytes VALUES(?,?,?)", (digest, body, len(body)))
        db.execute("INSERT INTO payloads VALUES('git-object-raw-v1',?)", (digest,))
        obj = db.execute(
            "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',?,1) RETURNING git_object_id",
            (oid, len(body)),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO git_object_payloads VALUES(?,?,?)",
            (obj, "git-object-raw-v1", digest),
        )
        db.execute(
            "INSERT INTO repository_object_sources VALUES(?,?,?)",
            (other, obj, acquisition),
        )
    db.execute("COMMIT")
    if admissions:
        db.execute("BEGIN")
        fake = {"key": "unrelated:key", "table": "unrelated", "values": {}}
        encoded = json.dumps(fake, separators=(",", ":"), sort_keys=True)
        for i in range(admissions):
            db.execute(
                "INSERT INTO exchange_admissions VALUES(?,?,?,?,?)",
                (
                    f"unrelated:{i:08d}",
                    "unrelated",
                    "{}",
                    hashlib.sha256(str(i).encode()).digest(),
                    encoded,
                ),
            )
        db.execute("COMMIT")
    return db, target


def measure(db, fn):
    statements = []
    db.set_trace_callback(statements.append)
    tracemalloc.start()
    start = time.perf_counter()
    out = fn()
    elapsed = time.perf_counter() - start
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    db.set_trace_callback(None)
    return {
        "elapsed_s": round(elapsed, 4),
        "python_peak_mib": round(peak / 1024 / 1024, 3),
        "sql_statements": len(statements),
        "output_records": len(out.get("records", []))
        if isinstance(out, dict) and "records" in out
        else (len(out) if hasattr(out, "__len__") else None),
    }


for n in (1000, 5000):
    db, target = make_db(n, 0)
    g = Graph(db)
    print(
        json.dumps(
            {"objects": n, "export": measure(db, lambda: g.export(target))},
            sort_keys=True,
        )
    )
    db.close()
for n in (0, 50000):
    db, target = make_db(0, n)
    g = Graph(db, persist_identities=False)
    print(
        json.dumps(
            {
                "unrelated_admissions": n,
                "context": measure(db, lambda: g.original_intake_context((), target)),
            },
            sort_keys=True,
        )
    )
    db.close()
```

## Original harnesses

The original independent reviewer preserved these programs and the measurements in the [initial findings](reviewer-c-original-exchange-findings.md). They refer to the initial feature/main methods and are historical reproductions, not acceptance programs for the corrected signatures.

### reviewer-c-exchange-scale.py

```python
import hashlib
import json
import sqlite3
import sys
import time
import tracemalloc
import uuid

from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.schema import schema_sql

count = int(sys.argv[1])
db = sqlite3.connect(":memory:", isolation_level=None)
db.executescript(schema_sql())
repo = str(uuid.uuid4())
db.execute(
    "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?, 'empty', '{}')",
    (repo,),
)
rows = []
for i in range(count):
    body = f"object-{i:08d}-".encode() + hashlib.sha256(str(i).encode()).digest()
    oid = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).digest()
    sha = hashlib.sha256(body).digest()
    rows.append((oid, body, sha, len(body)))
db.execute("BEGIN")
for oid, body, sha, size in rows:
    obj_id = db.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',?,1) RETURNING git_object_id",
        (oid, size),
    ).fetchone()[0]
    db.execute(
        "INSERT INTO stored_bytes(sha256,body,byte_length) VALUES(?,?,?)",
        (sha, body, size),
    )
    db.execute(
        "INSERT INTO payloads(representation,sha256) VALUES('git-object-raw-v1',?)",
        (sha,),
    )
    db.execute(
        "INSERT INTO git_object_payloads(git_object_id,payload_representation,payload_sha256) VALUES(?,'git-object-raw-v1',?)",
        (obj_id, sha),
    )
db.execute("COMMIT")
statements = [0]
db.set_trace_callback(lambda sql: statements.__setitem__(0, statements[0] + 1))
tracemalloc.start()
start = time.perf_counter()
unit = Graph(db).export(repo)
elapsed = time.perf_counter() - start
_, peak = tracemalloc.get_traced_memory()
print(
    json.dumps(
        {
            "object_count": count,
            "elapsed_s": round(elapsed, 4),
            "sql_statements": statements[0],
            "python_peak_mib": round(peak / 1048576, 2),
            "export_record_count": len(unit["records"]),
        }
    )
)
```

### reviewer-c-exchange-promote-scale.py

```python
import hashlib
import json
import sqlite3
import sys
import time
import uuid

from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.schema import schema_sql

count = int(sys.argv[1])


def catalog():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(schema_sql())
    return db


src, dst = catalog(), catalog()
repo = str(uuid.uuid4())
src.execute(
    "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?, 'empty', '{}')",
    (repo,),
)
obj_rows, payload_rows, stored_rows, mapping_rows = [], [], [], []
for i in range(count):
    body = f"object-{i:08d}-".encode() + hashlib.sha256(str(i).encode()).digest()
    oid = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).digest()
    sha = hashlib.sha256(body).digest()
    obj_id = src.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',?,1) RETURNING git_object_id",
        (oid, len(body)),
    ).fetchone()[0]
    src.execute(
        "INSERT INTO stored_bytes(sha256,body,byte_length) VALUES(?,?,?)",
        (sha, body, len(body)),
    )
    src.execute(
        "INSERT INTO payloads(representation,sha256) VALUES('git-object-raw-v1',?)",
        (sha,),
    )
    src.execute(
        "INSERT INTO git_object_payloads(git_object_id,payload_representation,payload_sha256) VALUES(?,'git-object-raw-v1',?)",
        (obj_id, sha),
    )
    obj_rows.append(
        src.execute(
            "SELECT * FROM git_objects WHERE git_object_id=?", (obj_id,)
        ).fetchone()
    )
    payload_rows.append(
        src.execute("SELECT * FROM payloads WHERE sha256=?", (sha,)).fetchone()
    )
    stored_rows.append(
        src.execute("SELECT * FROM stored_bytes WHERE sha256=?", (sha,)).fetchone()
    )
    mapping_rows.append(
        src.execute(
            "SELECT * FROM git_object_payloads WHERE git_object_id=?", (obj_id,)
        ).fetchone()
    )
graph = Graph(src, persist_identities=False)
if hasattr(graph, "required_original_keys"):
    graph._original_export_keys = graph.required_original_keys(
        graph.local_original_context()
    )
records = [
    Graph(src).record(
        "repositories",
        Graph(src).lookup("repositories", ("repository_uuidv4",), (repo,)),
    )
]
# Reverse logical dependency order; receive must preserve durable missing-dependency staging.
for table, rows in [
    ("git_object_payloads", mapping_rows),
    ("payloads", payload_rows),
    ("git_objects", obj_rows),
    ("stored_bytes", stored_rows),
]:
    records.extend(
        graph.record(
            table,
            graph.lookup(
                table,
                graph.keys[table],
                tuple(row[i] for i in range(len(graph.keys[table]))),
            )
            if False
            else dict(zip(graph.columns[table], row)),
        )
        for row in rows
    )
unit = {
    "format": "repo-catalog/repository-exchange-v1",
    "repository_uuidv4": repo,
    "origin_catalog_uuidv4": str(uuid.uuid4()),
    "records": records,
}
context_calls = [0]
original_method = Graph.local_original_context


def counted_context(self, repository_uuidv4=None):
    context_calls[0] += 1
    return original_method(self, repository_uuidv4)


Graph.local_original_context = counted_context
count_statements = [0]
dst.set_trace_callback(
    lambda sql: count_statements.__setitem__(0, count_statements[0] + 1)
)
start = time.perf_counter()
result = Graph(dst).receive(unit)
elapsed = time.perf_counter() - start
print(
    json.dumps(
        {
            "object_count": count,
            "elapsed_s": round(elapsed, 4),
            "sql_statements": count_statements[0],
            "received": result["received_records"],
            "admitted": result["admitted_records"],
            "staged": result["staged_records"],
            "stored_bytes": dst.execute("select count(*) from stored_bytes").fetchone()[
                0
            ],
            "local_original_context_calls": context_calls[0],
        }
    )
)
```

### reviewer-c-exchange-admission-context-scale.py

```python
import hashlib
import json
import sqlite3
import sys
import time
import tracemalloc
import uuid
from repo_catalog.adapters.sqlite.exchange import Graph, canonical, record_digest
from repo_catalog.adapters.sqlite.schema import schema_sql

count = int(sys.argv[1])
db = sqlite3.connect(":memory:", isolation_level=None)
db.executescript(schema_sql())
selected = str(uuid.uuid4())
db.execute(
    "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?, 'selected', '{}')",
    (selected,),
)
other = [str(uuid.uuid4()) for _ in range(count)]
db.execute("BEGIN")
for i, repo in enumerate(other):
    row = {"repository_uuidv4": repo, "name": f"repo-{i}", "metadata": "{}"}
    record = {
        "key": "repositories:" + canonical({"repository_uuidv4": repo}),
        "table": "repositories",
        "values": row,
    }
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,?,?)",
        (repo, row["name"], row["metadata"]),
    )
    db.execute(
        "INSERT INTO exchange_admissions VALUES(?,?,?,?,?)",
        (
            record["key"],
            "repositories",
            canonical({"repository_uuidv4": repo}),
            record_digest(record),
            canonical(record),
        ),
    )
db.execute("COMMIT")
g = Graph(db, persist_identities=False)
statements = [0]
db.set_trace_callback(lambda sql: statements.__setitem__(0, statements[0] + 1))
tracemalloc.start()
t = time.perf_counter()
ctx = g.original_intake_context(repository_uuidv4=selected)
keys = g.required_original_keys(ctx)
elapsed = time.perf_counter() - t
_, peak = tracemalloc.get_traced_memory()
print(
    json.dumps(
        {
            "unrelated_admissions": count,
            "elapsed_s": round(elapsed, 4),
            "sql_statements": statements[0],
            "python_peak_mib": round(peak / 1048576, 2),
            "context_rows": len(ctx),
            "required_keys": len(keys),
        }
    )
)
```

