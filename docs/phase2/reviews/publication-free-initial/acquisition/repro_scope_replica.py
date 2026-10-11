"""Print durable replica locations, using only disposable fixture state."""
import copy
import json
import tempfile
from pathlib import Path

import pytest
from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from tests.support.github_runtime import github_runtime
from test_independent_acquisition import prepare

with tempfile.TemporaryDirectory(prefix='independent-acquisition-') as disposable:
    patch=pytest.MonkeyPatch()
    fixture=github_runtime.__wrapped__(Path(disposable),patch)
    try:
        runtime=next(fixture)
        store,repo,git,api=runtime
        collector,parent,job,data=prepare(runtime)
        context=collector.facts.current_context(repo,parent['change_request_id'],api.url+'/pulls/1')
        context['acquisition_scope']['provider_response']={'body':'raw-provider-sentinel','headers':{'fixture-only':'dummy'}}
        candidate=current_parser.document({**data,'body':'new admitted domain body','updated_at':'2026-02-01T00:00:00Z'},context,200,'pr-body')
        candidate['parsed_at_us']=201
        adapter=CurrentApiState(store)
        admitted=adapter.admit('document_state',candidate,source='import')
        stored=store.one("SELECT acquisition_scope_json,field_evidence_json FROM document_state WHERE kind='pr-body'")
        assert all('raw-provider-sentinel' in value for value in stored)
        pending=copy.deepcopy(candidate)
        pending['change_request_id']='missing-parent'
        pending['acquisition_scope']['change_request_id']='missing-parent'
        deferred=adapter.admit('document_state',pending,source='import')
        stage=store.one("SELECT record_json FROM exchange_staging WHERE table_name='document_state'")[0]
        assert 'raw-provider-sentinel' in stage
        print(json.dumps({'admitted_status':admitted.status,'current_scope_replica':True,'current_field_replica':True,'pending_status':deferred.status,'pending_replica':True,'stored_api_bytes':store.one('SELECT count(*) FROM stored_bytes')[0]}))
    finally:
        fixture.close()
        patch.undo()
