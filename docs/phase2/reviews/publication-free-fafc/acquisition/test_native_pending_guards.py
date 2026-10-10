"""Independent native-SQL attacks against frozen fafc typed pending guards."""
import copy
import json
import pathlib
import sqlite3
import subprocess

import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from tests.support.github_runtime import github_runtime
from test_independent_acquisition import prepare

SQLITE345 = pathlib.Path('/workspace/review-artifacts/schema-a1-b86/sqlite345/sqlite3')


@pytest.mark.parametrize('runtime',['sqlite353','sqlite345'])
@pytest.mark.parametrize('attack',[
    'foreign-capture-parent','foreign-field-parent','evidence-without-body',
    'overflow-observed','null-parsed','boolean-observed',
    'escaped-permissions-object','valid-signed-boundary',
])
def test_typed_pending_native_guard(github_runtime,tmp_path,runtime,attack):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    context=collector.facts.current_context(repo,parent['change_request_id'],api.url+'/pulls/1')
    candidate=current_parser.document(data,context,200,'pr-body')
    candidate.update(change_request_id='missing-real-parent',parsed_at_us=201)
    candidate['acquisition_scope']['change_request_id']='missing-real-parent'
    assert CurrentApiState(store).admit('document_state',candidate,source='import').status=='missing_dependency'
    saved=store.one("SELECT * FROM exchange_staging WHERE table_name='document_state'")
    record=json.loads(saved['record_json'])
    if attack=='foreign-capture-parent':record['acquisition_scope']['change_request_id']='foreign-parent'
    elif attack=='foreign-field-parent':record['field_evidence']['["body"]']['acquisition_scope']['change_request_id']='foreign-parent'
    elif attack=='evidence-without-body':del record['body']
    elif attack=='overflow-observed':record['observed_at_us']=2**63
    elif attack=='null-parsed':record['parsed_at_us']=None
    elif attack=='boolean-observed':record['observed_at_us']=True
    elif attack=='escaped-permissions-object':record['acquisition_scope']['request_context']={'permissions':[{'provider_response':'dummy-original'}]}
    else:
        record.update(observed_at_us=-(2**63),parsed_at_us=0)
        for origin in record['field_evidence'].values():origin.update(observed_at_us=-(2**63),parsed_at_us=0)
    payload=json.dumps(record,separators=(',',':'))
    if attack=='escaped-permissions-object':payload=payload.replace('"permissions"','"permi\\u0073sions"')
    expected_accept=attack=='valid-signed-boundary'
    sql="UPDATE exchange_staging SET record_json=? WHERE record_key=?"
    if runtime=='sqlite353':
        assert sqlite3.sqlite_version=='3.53.1'
        if expected_accept:
            store.execute(sql,(payload,saved['record_key']))
            assert json.loads(store.one('SELECT record_json FROM exchange_staging WHERE record_key=?',(saved['record_key'],))[0])['observed_at_us']==-(2**63)
        else:
            with pytest.raises(sqlite3.IntegrityError):store.execute(sql,(payload,saved['record_key']))
            assert store.one('SELECT record_json FROM exchange_staging WHERE record_key=?',(saved['record_key'],))[0]==saved['record_json']
    else:
        version=subprocess.run([str(SQLITE345),'--version'],check=True,text=True,capture_output=True).stdout
        assert version.startswith('3.45.1 ')
        catalog=tmp_path/'disposable-native345.sqlite3'
        destination=sqlite3.connect(catalog)
        store.connection.backup(destination)
        destination.close()
        quote=lambda value:"'"+value.replace("'","''")+"'"
        statement=sql.replace('?',quote(payload),1).replace('?',quote(saved['record_key']),1)
        run=subprocess.run([str(SQLITE345),str(catalog)],input='.bail on\nPRAGMA foreign_keys=ON;\nPRAGMA recursive_triggers=ON;\n'+statement+';\n',text=True,capture_output=True)
        if expected_accept:
            assert run.returncode==0,run.stderr
            read=subprocess.run([str(SQLITE345),str(catalog),"SELECT json_extract(record_json,'$.observed_at_us') FROM exchange_staging WHERE record_key="+quote(saved['record_key'])],check=True,text=True,capture_output=True)
            assert read.stdout.strip()==str(-(2**63))
        else:
            assert run.returncode!=0
            assert 'JSON contract violation: exchange_staging.record_json' in run.stderr,run.stderr
            read=subprocess.run([str(SQLITE345),str(catalog),'SELECT record_json FROM exchange_staging WHERE record_key='+quote(saved['record_key'])],check=True,text=True,capture_output=True)
            assert read.stdout.strip()==saved['record_json']
