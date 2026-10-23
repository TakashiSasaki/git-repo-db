import os,json,subprocess,sys,shutil,time,hashlib
from pathlib import Path
root=Path('/workspace/adr0033-review');out=Path('/tmp/adr0033-rereview');base=out/'installed';outside=base/'outside';records=[]
sys.path.insert(0,str(root))
from scripts import verify_i5_offline as evidence
shutil.copyfile(root/'scripts/ci_journal.py',outside/'ci_journal.py')
(outside/'origin_probe.py').write_text('''import hashlib,json,sys,sqlite3,zipfile\nfrom pathlib import Path\nimport repo_catalog\np=Path(repo_catalog.__file__).resolve().parent\nassert p.is_relative_to(Path(sys.prefix).resolve()) and 'site-packages' in p.parts,p\nassert not any(Path(x).resolve().is_relative_to(Path('/workspace/adr0033-review')) for x in sys.path if x),sys.path\nwith zipfile.ZipFile(sys.argv[1]) as z:\n expected={n.removeprefix('repo_catalog/'):hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('repo_catalog/')}\nactual={str(x.relative_to(p)):hashlib.sha256(x.read_bytes()).hexdigest() for x in p.rglob('*') if x.is_file() and x.suffix in {'.py','.sql','.json','.graphql'}}\nassert expected==actual\ndb=sqlite3.connect(':memory:')\nPath(sys.argv[2]).write_text(json.dumps({'origin':str(p),'executable':sys.executable,'sys_path':sys.path,'product_hashes':actual,'sqlite':db.execute('select sqlite_version(),sqlite_source_id()').fetchone()},indent=2)+'\\n')\n''')
def run(name,args,env):
 start=time.time()
 with (out/(name+'.log')).open('w') as f:r=subprocess.run(list(map(str,args)),cwd=outside,env=env,stdout=f,stderr=subprocess.STDOUT)
 record={'name':name,'argv':list(map(str,args)),'cwd':str(outside),'started_epoch':start,'wall_seconds':time.time()-start,'exit_code':r.returncode};records.append(record);(out/'installed-journal-processes.json').write_text(json.dumps(records,indent=2)+'\n');return r.returncode
summary={}
for tag in ('direct','sdist'):
 py=base/(tag+'-venv/bin/python');venv=py.parent.parent
 env={**os.environ,'PATH':str(py.parent)+os.pathsep+os.environ['PATH'],'PYTHONPATH':str(outside/'network_guard'),'GIT_ALLOW_PROTOCOL':'file'}
 for key in ('GH_TOKEN','GITHUB_TOKEN','PYTHONHOME'):env.pop(key,None)
 artifact=next(((base/'source/dist') if tag=='direct' else next((base/'from-sdist').iterdir())/'dist').glob('*.whl'))
 assert run(tag+'-origin',[py,outside/'origin_probe.py',artifact,out/(tag+'-origin.json')],env)==0
 args=[py,'-m','pytest','test_installed_i4.py','test_installed_i5.py','-c','/dev/null','--rootdir='+str(outside),'--confcutdir='+str(outside),'-o','junit_family=xunit1','-q']
 assert run(tag+'-installed-collection',args+['--collect-only'],env)==0
 nodes=[line.strip() for line in (out/(tag+'-installed-collection.log')).read_text().splitlines() if line.startswith('test_installed_') and '::' in line]
 (out/(tag+'-installed.selected.txt')).write_text(''.join(n+'\n' for n in nodes));assert len(nodes)==246 and len(nodes)==len(set(nodes))
 xml=out/(tag+'-installed.xml');journal=out/(tag+'-installed.jsonl')
 exit_code=run(tag+'-installed-journal',args+['-p','ci_journal','--journal='+str(journal),'--junitxml='+str(xml)],env)
 summary[tag]={'exit_code':exit_code,'outcomes':evidence.outcomes(xml),'reconciliation':evidence.reconciliation(nodes,xml,journal)}
(out/'installed-journal-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
assert all(r['exit_code']==0 and r['reconciliation']['consistent_node_execution'] for r in summary.values())
