"""Independent actual composed-DDL inventory; does not import the author's audit."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import repo_catalog
from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.json_contracts import guard_sql
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, schema_sql

root = Path(sys.argv[1])
assert Path(repo_catalog.__file__).is_relative_to(root), repo_catalog.__file__
db = sqlite3.connect(':memory:')
db.execute('PRAGMA foreign_keys=ON')
db.execute('PRAGMA recursive_triggers=ON')
register_git_object_sql_function(db)
db.executescript(schema_sql())
objects = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
tables, views, triggers, indexes = {}, {}, {}, {}
for kind, name, owner, sql in objects:
    fingerprint = hashlib.sha256(sql.encode()).hexdigest()
    if kind == 'table':
        columns = db.execute('PRAGMA table_xinfo("' + name + '")').fetchall()
        tables[name] = {
            'columns': [row[1] for row in columns],
            'generated_columns': [row[1] for row in columns if row[6] in (2, 3)],
            'primary_key': [row[1] for row in sorted(columns, key=lambda row: row[5]) if row[5]],
            'foreign_keys': [list(row) for row in db.execute('PRAGMA foreign_key_list("' + name + '")')],
            'sql_sha256': fingerprint,
        }
    elif kind == 'view':
        db.execute('SELECT * FROM "' + name + '" LIMIT 0').fetchall()
        views[name] = fingerprint
    elif kind == 'trigger':
        triggers[name] = {'owner': owner, 'sql_sha256': fingerprint}
    elif kind == 'index':
        indexes[name] = {'owner': owner, 'sql_sha256': fingerprint}
inventory = {'ddl_sha256': DDL_SHA256.hex(), 'tables': tables, 'views': views, 'triggers': triggers, 'indexes': indexes}
expected = json.loads((root / 'docs/phase2/publication-free-schema-map.json').read_text())['current']
assert inventory == expected, 'Actual composed DDL differs from checked-in structural map'
assert (root / 'src/repo_catalog/resources/json_contracts.sql').read_text() == guard_sql()
assert db.execute('PRAGMA foreign_key_check').fetchall() == []
assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
print(json.dumps({
    'commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
    'tree': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
    'module': repo_catalog.__file__, 'python': sys.version, 'sqlite': sqlite3.sqlite_version,
    'ddl': DDL_SHA256.hex(), 'actual_map_matches': True,
    'counts': {'tables': len(tables), 'columns': sum(len(table['columns']) for table in tables.values()),
               'generated_columns': sum(len(table['generated_columns']) for table in tables.values()),
               'foreign_keys': sum(len(table['foreign_keys']) for table in tables.values()),
               'views': len(views), 'triggers': len(triggers), 'indexes': len(indexes)},
    'checks': ['all actual views compile', 'foreign_key_check empty', 'integrity_check ok', 'generated guard SQL exact'],
    'limitation': 'Structural inventory and preparation do not certify semantic correctness',
}, indent=2))
