"""Valid canonical wide tree compressed into one malformed intrinsic row."""
import hashlib
import json
import pathlib
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.git.parsing import verify_git_object_structure
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_exchange import catalog

results=[]
for fmt in ('sha1','sha256'):
    for width in (2,2048):
        db=catalog()
        child=hashlib.new(fmt,b'blob 7\0missing').digest()
        records=[b'100644 n%04d\0'%n+child for n in range(width)]
        body=b''.join(records)
        oid=hashlib.new(fmt,b'tree '+str(len(body)).encode()+b'\0'+body).digest()
        payload=intern_payload(db,body,representation='git-object-raw-v1')
        obj=db.execute("INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,'tree',?,1)",(fmt,oid,len(body))).lastrowid
        db.execute("INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",(obj,payload.sha256))
        db.execute('INSERT INTO tree_objects VALUES(?,1)',(obj,))
        # Exact bytes still agree: malformed name contains all intervening NULs,
        # OIDs and subsequent entries, leaving only the last OID as child target.
        spoof_name=body[len(b'100644 '):-len(child)-1]
        db.execute('INSERT INTO tree_entries VALUES(?,?,0,?,33188,?,?,NULL)',(obj,spoof_name,len(body),fmt,child))
        available=db.execute('SELECT count(*) FROM available_git_objects WHERE git_object_id=?',(obj,)).fetchone()[0]
        try:
            verify_git_object_structure(db,obj)
            validator='accepted'
        except CatalogError as error:
            validator=error.code+': '+str(error)
        result={'format':fmt,'canonical_entry_count':width,'stored_entry_count':1,'byte_size':len(body),'available_git_objects_count':available,'full_structure_validator':validator,'fk_check':db.execute('PRAGMA foreign_key_check').fetchall(),'integrity':db.execute('PRAGMA integrity_check').fetchone()[0]}
        results.append(result)
        db.close()
print(json.dumps(results,indent=2))
pathlib.Path('/workspace/review-artifacts/git-exchange-cas/intrinsic_tree_spoof.json').write_text(json.dumps(results,indent=2)+'\n')
