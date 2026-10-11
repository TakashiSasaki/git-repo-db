"""Final native metadata/decoder consistency checks; only own memory fixtures."""
import copy,hashlib,json,sqlite3,sys,uuid
from pathlib import Path
import repo_catalog
from fixtures import fixture
from repo_catalog.adapters.git.parsing import install_git_object
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.json_contracts import validate_catalog,validate_record
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.git_query_context import decoded_fact
from repo_catalog.domain.models import CatalogError


def modeled_tree_sql():
    db,ids=fixture();ids={k:v for k,v in ids.items() if k!='change_request_id'}
    metadata={'labels':[{'name':'one','id':1}],'milestone':{'title':'first','state':'open','creator':{'login':'synthetic'}}}
    value={**ids,'kind':'issue','provider_resource_id':'10','provider_issue_number':1,'body':'current','observed_at_us':100,'parsed_at_us':101,'provider_updated_at_us':10,'provider_clock_scope':'github-issue-updated-at','parser_module':'review.synthetic','parser_version':'1','acquisition_scope':{**ids,'endpoint':'issues/1'},'metadata':metadata}
    assert CurrentResources(db).admit(value,source='import').status=='accepted'
    variants=[]
    x=copy.deepcopy(metadata);x['milestone']['creator']['unmodeled']={};variants.append(x)
    x=copy.deepcopy(metadata);x['milestone']['creator']['login']={};variants.append(x)
    x=copy.deepcopy(metadata);x['labels'][0]['name']=['one'];variants.append(x)
    x=copy.deepcopy(metadata);x['labels'].append({'name':'second','unmodeled':{}});variants.append(x)
    x=copy.deepcopy(metadata);x['labels']=[[{'name':'one'}]];variants.append(x)
    x=copy.deepcopy(metadata);x['labels'][0]['id']=True;variants.append(x)
    for x in variants:
        row=dict(db.execute('SELECT * FROM issue_resources').fetchone());row['metadata']=json.dumps(x)
        try:validate_record(db,'issue_resources',row)
        except CatalogError:pass
        else:raise AssertionError('Python accepted malformed modeled tree')
        try:db.execute('UPDATE issue_resources SET metadata=?',(json.dumps(x),))
        except sqlite3.IntegrityError:pass
        else:raise AssertionError('SQL accepted malformed modeled tree')
    escaped=json.dumps(metadata).replace('"labels"','"l\\u0061bels"').replace('"creator"','"cre\\u0061tor"')
    db.execute('UPDATE issue_resources SET metadata=?',(escaped,));assert validate_catalog(db)['records_checked']>0
    duplicate=escaped[:-1]+',"labels":[]}'
    try:db.execute('UPDATE issue_resources SET metadata=?',(duplicate,))
    except sqlite3.IntegrityError:pass
    else:raise AssertionError('Decoded duplicate property accepted')
    db.close();return {'nested_shape_variants_rejected_Python_and_SQL':len(variants),'escaped_known_keys':'valid','decoded_duplicate_key':'rejected'}


class Reads:
    def __init__(self,db):self.connection=db
    def all(self,sql,args=()):return self.connection.execute(sql,args).fetchall()
    def execute(self,sql,args=()):return self.connection.execute(sql,args)


def decoded_candidates_computed_and_checked():
    results=[]
    for fmt in ('sha1','sha256'):
        db,ids=fixture();body=b'actual byte-derived text';oid=hashlib.new(fmt,f'blob {len(body)}\0'.encode()+body).digest()
        obj=install_git_object(db,fmt,oid,'blob',body)
        healthy=dict(db.execute('SELECT * FROM git_text_facts').fetchone());bad=copy.deepcopy(healthy);bad['git_fact_uuidv4']=str(uuid.uuid4());bad['parser_module']='review.synthetic.consistency'
        settings={k:bad[k] for k in ('parser_module','parser_version','text_encoding','metadata_encoding','metadata_errors','max_text_blob_bytes')}
        bad['decoder_key']=hashlib.sha256(json.dumps(settings,sort_keys=True,separators=(',',':')).encode()).hexdigest();bad['raw_text']='inconsistent retained projection'
        columns=tuple(bad);sql='INSERT INTO git_text_facts('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')'
        try:db.execute(sql,tuple(bad.values()))
        except sqlite3.IntegrityError as exc:assert 'decoder value' in str(exc)
        else:raise AssertionError('Native insert accepted inconsistent byte projection')
        # Simulate an old malformed retained row only in this disposable catalog.
        db.execute('DROP TRIGGER git_text_facts_bytes');db.execute(sql,tuple(bad.values()))
        assert db.execute('SELECT count(*) FROM git_text_facts').fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM valid_git_text_facts').fetchone()[0]==1
        result=decoded_fact(Reads(db),obj,'blob');assert not result['decoder_conflict'];assert result['fact']['raw_text']==body.decode();assert len(result['candidates'])==1
        issues=check_catalog(Reads(db),full=True)
        assert any(i.get('code')=='GIT_DECODER_FACT' and i.get('decoder_key')==bad['decoder_key'] for i in issues)
        results.append({'format':fmt,'native_insert':'rejected','simulated_old_malformed_row':'excluded_by_computed_view_and_reader','full_check':'specific_GIT_DECODER_FACT','healthy_candidate':'still_usable'});db.close()
    return results


def main():
    output={'source':repo_catalog.__file__,'python':sys.version,'sqlite':sqlite3.sqlite_version}
    for fn in (modeled_tree_sql,decoded_candidates_computed_and_checked):output[fn.__name__]=fn();print(fn.__name__,'passed',flush=True)
    Path(__file__).with_name('new-boundary-results.json').write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))
if __name__=='__main__':main()
