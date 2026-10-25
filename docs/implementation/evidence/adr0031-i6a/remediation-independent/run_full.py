# Adapted frozen Author execution harness; tests independently reexecuted, no result copied.
import os,sys,json,pathlib,sqlite3
root=pathlib.Path(sys.argv[1]).resolve();out=pathlib.Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(root));from scripts import verify_i5_offline as e
os.environ['PATH']=str(pathlib.Path(sys.executable).parent)+os.pathsep+os.environ['PATH']
os.environ['TMPDIR']='/workspace/review-tmp'
os.environ['PYTHONPATH']='/workspace/review-tools'
e.write_json(out/'runtime.json',e.runtime_metadata(sqlite3.connect(':memory:')))
e.write_json(out/'binding-before.json',{'head':e.git('rev-parse','HEAD'),'tree':e.git('rev-parse','HEAD^{tree}'),'inputs':e.input_hashes(),'status':e.git('status','--porcelain','--untracked-files=no')})
e.require_product_runtime()
allnodes,_=e.collect(out,'all-collection',['tests']);nodes,r=e.collect(out,'ordinary-collection',['tests'],'not live and not benchmark')
if r['exit_code']:raise SystemExit('collection failed')
e.write_json(out/'unexecuted.json',sorted(set(allnodes)-set(nodes)))
execute=e.execute
def typed(out,name,args):
 os.environ['I6A_REPORTS_SIDECAR']=str(out/(name+'.report-types.jsonl'))
 return execute(out,name,['-p','i6a_report_types',*(['-p','i6a_assertion_lines'] if os.environ.get('I6A_ASSERTIONS_SOURCE') else []),*args,'--basetemp='+str(out/'basetemp')])
e.execute=typed
r=e.run_cohort(out,'ordinary',nodes,4)
e.write_json(out/'binding-after.json',{'head':e.git('rev-parse','HEAD'),'tree':e.git('rev-parse','HEAD^{tree}'),'inputs':e.input_hashes(),'status':e.git('status','--porcelain','--untracked-files=no')})
print(json.dumps({'counts':{k:r.get(k) for k in ['passed','failed','error','executed','exit_code']},'output':str(out)}))
