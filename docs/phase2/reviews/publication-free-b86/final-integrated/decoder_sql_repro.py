"""FIV-1: real normal acquisition -> false SQL decoder -> ordinary query."""
import hashlib,json,tempfile,uuid
from pathlib import Path
import repo_catalog
from repo_catalog.adapters.git.parsing import GitParsing,validate_git_fact
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.query_service import QueryService
from test_final_integrated import git_catalog, FixtureRepo, OWNER

assert '/publication-free-final-verifier/' in repo_catalog.__file__
with tempfile.TemporaryDirectory(prefix='scope4-decoder-') as temp:
    root=Path(temp);remote=FixtureRepo(root/'remote.git')
    remote.commit('A',{b'file.txt':b'genuine canonical content'});remote.ref('refs/heads/main','A')
    store,_=git_catalog(root/'state',remote)
    with store:
        parser=GitParsing(store);blob=store.one("SELECT * FROM git_text_facts LIMIT 1")
        row=dict(blob);row.update(git_fact_uuidv4=str(uuid.uuid4()),parser_module='scope4.false-local',parser_version='unranked',raw_text='scope-four-fabricated-text')
        settings={key:row[key] for key in parser.decoder}
        row['decoder_key']=hashlib.sha256(json.dumps(settings,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        insert_status='accepted'
        try:
            store.execute('INSERT INTO git_text_facts('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
        except Exception as error:
            insert_status=type(error).__name__+':'+str(error)
        validation='accepted'
        try:validate_git_fact(store.connection,'git_text_facts',row)
        except Exception as error:validation=type(error).__name__+':'+str(error)
        fullcheck=check_catalog(store,full=True)
    query=QueryService(root/'state').query('search code',{'repo':OWNER,'literal':'scope-four-fabricated-text','decoder_key':row['decoder_key']})
    print(json.dumps({'module':repo_catalog.__file__,'insert':insert_status,'byte_validator':validation,'full_catalog_check':fullcheck,'query_items':query.data['items']},indent=2))
