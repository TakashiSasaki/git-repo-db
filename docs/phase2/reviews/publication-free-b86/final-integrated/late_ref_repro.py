"""FIV-2 candidate: real Git origin waits for the exact captured ref."""
import copy,json,tempfile
from pathlib import Path
from test_final_integrated import git_catalog,FixtureRepo,export,receive,Store,init
with tempfile.TemporaryDirectory(prefix='scope4-late-ref-') as temp:
    root=Path(temp);remote=FixtureRepo(root/'remote.git')
    remote.commit('A',{b'a.txt':b'actual bytes'});remote.ref('refs/heads/main','A')
    sender,_=git_catalog(root/'sender',remote)
    with sender:unit=export(sender)
    ref=next(r for r in unit['records'] if r['table']=='ref_observations')
    early={**unit,'records':[r for r in unit['records'] if r!=ref]}
    with Store(init(root/'receiver')) as receiver:
        first=receive(receiver,early)
        early_staging=[dict(r) for r in receiver.all('SELECT table_name,reason,record_json FROM exchange_staging')]
        late=receive(receiver,{**unit,'records':[ref]})
        late_staging=[dict(r) for r in receiver.all('SELECT table_name,reason,record_json FROM exchange_staging')]
        replay=receive(receiver,unit)
        replay_staging=[dict(r) for r in receiver.all('SELECT table_name,reason,record_json FROM exchange_staging')]
        roots=receiver.one('SELECT count(*) FROM root_origins')[0]
        snapshots=receiver.one('SELECT count(*) FROM current_snapshots')[0]
    print(json.dumps({'first':first,'early_staging':early_staging,'late':late,'late_staging':late_staging,'replay':replay,'replay_staging':replay_staging,'root_origins':roots,'current_snapshots':snapshots},indent=2))
