"""Independent strict decoder error and canonical-data preservation check."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

import repo_catalog
from repo_catalog.adapters.git.parsing import GitParsing
from repo_catalog.adapters.sqlite.schema import DDL_SHA256
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import CatalogError

root = Path(sys.argv[1])
assert Path(repo_catalog.__file__).is_relative_to(root), repo_catalog.__file__


def oid(fmt, kind, body):
    return hashlib.new(fmt, f'{kind} {len(body)}\0'.encode() + body).digest()


scenarios = []
with tempfile.TemporaryDirectory(prefix='scope4-strict-decode-') as directory:
    for fmt in ('sha1', 'sha256'):
        for bad_part in ('header', 'message'):
            state = Path(directory) / (fmt + '-' + bad_part)
            MaintenanceService(state).init('catalog-text-v1', 64 * 1024 * 1024, 0)
            header = b'author real\xff' if bad_part == 'header' else b'author real'
            message = b'actual message\xff' if bad_part == 'message' else b'actual message'
            body = b'tree ' + oid(fmt, 'tree', b'').hex().encode() + b'\n' + header + b'\n\n' + message
            with Store(state) as store:
                obj = GitParsing(store).install_object(fmt, oid(fmt, 'commit', body), 'commit', body)
                original = tuple(store.one('SELECT * FROM commits WHERE git_object_id=?', (obj,)))
                raw_original = tuple(store.one('SELECT * FROM stored_bytes'))
                revision = store.revision()
                strict = GitParsing(store, metadata_errors='strict')
                try:
                    strict.parse_object(store.one('SELECT * FROM git_objects WHERE git_object_id=?', (obj,)), body)
                except CatalogError as error:
                    code = error.code
                else:
                    raise AssertionError('strict non-UTF8 interpretation was accepted')
                assert code == 'PARSER_DECODE', code
                assert tuple(store.one('SELECT * FROM commits WHERE git_object_id=?', (obj,))) == original
                assert tuple(store.one('SELECT * FROM stored_bytes')) == raw_original
                assert store.revision() == revision
                assert store.one('SELECT count(*) FROM available_git_objects')[0] == 1
                assert not store.one('SELECT 1 FROM git_commit_facts WHERE decoder_key=?', (strict.decoder_key,))
                replaced = GitParsing(store, metadata_errors='replace')
                replaced.parse_object(store.one('SELECT * FROM git_objects WHERE git_object_id=?', (obj,)), body)
                assert store.one('SELECT 1 FROM valid_git_commit_facts WHERE decoder_key=?', (replaced.decoder_key,))
                assert not check_catalog(store, full=True)
                scenarios.append({'format': fmt, 'bad_part': bad_part, 'error_code': code, 'available_objects': 1, 'later_replace_accepted': True})
print(json.dumps({'commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(), 'tree': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD^{tree}'], text=True).strip(), 'module': repo_catalog.__file__, 'python': sys.version, 'sqlite': sqlite3.sqlite_version, 'ddl': DDL_SHA256.hex(), 'scenarios': scenarios}, indent=2))
