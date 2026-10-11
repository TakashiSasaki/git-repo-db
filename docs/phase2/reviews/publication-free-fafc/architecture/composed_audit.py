"""Exact source native/static review audit; no catalog outside memory."""
import importlib.util, json, sqlite3, sys, os
from pathlib import Path
import repo_catalog
from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.schema import schema_sql,DDL_SHA256
from repo_catalog.adapters.sqlite.json_contracts import guard_sql, inventory
ROOT=Path.cwd();OUT=Path(os.environ.get("ARCHITECTURE_AUDIT_OUTPUT",str(Path(__file__).parent)));OUT.mkdir(exist_ok=True)
assert Path(repo_catalog.__file__).resolve()==ROOT/'src/repo_catalog/__init__.py'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded);return loaded
struct=module('review_map','scripts/audit_publication_free.py')
audit=module('review_dependencies','scripts/audit_phase2_dependencies.py')
report=struct.report();checked=json.loads((ROOT/'docs/phase2/publication-free-schema-map.json').read_text());assert report==checked
(OUT/'regenerated-schema-map.json').write_text(json.dumps(report,indent=2))
db=sqlite3.connect(':memory:',isolation_level=None,cached_statements=0);register_git_object_sql_function(db);db.executescript(schema_sql())
native=audit.schema_inventory(db,schema_sql());(OUT/'native-schema-dependencies.json').write_text(json.dumps(native,indent=2))
assert all(v['status']=='compiled' for v in native['prepared_views'].values())
assert all(v['status']=='compiled' for v in native['prepared_mutations'].values())
assert native['checks']['foreign_key_check']==[]
assert native['checks']['integrity_check']==[('ok',)]
assert guard_sql()==(ROOT/'src/repo_catalog/resources/json_contracts.sql').read_text()
source=audit.source_inventory(ROOT,db,set(native['objects']));(OUT/'source-sql-call-inventory.json').write_text(json.dumps(source,indent=2))
registry=inventory(db);(OUT/'json-inventory.json').write_text(json.dumps(registry,indent=2))
summary={'python':sys.version,'sqlite':sqlite3.sqlite_version,'source':repo_catalog.__file__,'DDL':DDL_SHA256.hex(),'map_equal':True,'guard_equal':True,'counts':native['counts'],'checks':native['checks'],'views_prepared':len(native['prepared_views']),'mutations_prepared':len(native['prepared_mutations']),'json_inventory':registry}
(OUT/'audit-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));db.close()
