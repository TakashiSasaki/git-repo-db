"""FIV-1 sibling families: modeled decoding must match canonical object bytes."""
import hashlib,json,uuid
import pytest
from test_final_integrated import git_catalog,FixtureRepo,CatalogError,sqlite3
from repo_catalog.adapters.git.parsing import validate_git_fact
from repo_catalog.application.git_query_context import decoded_fact,decoded_name
from repo_catalog.application.catalog_validation import check_catalog

@pytest.mark.parametrize('attack',['text','commit-message','commit-metadata','name'])
def test_all_decoder_families_native_and_ordinary_readers_reject_false_value(tmp_path,attack):
    remote=FixtureRepo(tmp_path/'remote.git')
    remote.commit('A',{b'name-\xff.txt':b'genuine canonical text'});remote.ref('refs/heads/main','A')
    store,_=git_catalog(tmp_path/'state',remote)
    table={'text':'git_text_facts','commit-message':'git_commit_facts','commit-metadata':'git_commit_facts','name':'git_name_facts'}[attack]
    with store:
        row=dict(store.one('SELECT * FROM '+table+' LIMIT 1'))
        if 'git_fact_uuidv4' in row:row['git_fact_uuidv4']=str(uuid.uuid4())
        row.update(parser_module='scope4.native-'+attack,parser_version='unranked')
        settings={key:row[key] for key in ['parser_module','parser_version','text_encoding','metadata_encoding','metadata_errors','max_text_blob_bytes']}
        row['decoder_key']=hashlib.sha256(json.dumps(settings,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        field={'text':'raw_text','commit-message':'message_text','commit-metadata':'metadata','name':'decoded_name'}[attack]
        row[field]='{"author":"invented"}' if attack=='commit-metadata' else 'scope4-fabricated-decoder-value'
        try:store.execute('INSERT INTO '+table+'('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
        except (CatalogError,sqlite3.IntegrityError):return
        with pytest.raises(CatalogError):validate_git_fact(store.connection,table,row)
        if attack=='name':
            result=decoded_name(store,row['tree_git_object_id'],row['raw_name'],decoder_key=row['decoder_key'])
            returned=result['decoded_name']
        else:
            result=decoded_fact(store,row['git_object_id'],'blob' if attack=='text' else 'commit',decoder_key=row['decoder_key'])
            returned=result['fact']
        assert returned is None, f'{attack}: ordinary reader returned a canonical-byte contradiction'
        assert check_catalog(store,full=True), 'full catalog check silently accepts a false decoder candidate'
