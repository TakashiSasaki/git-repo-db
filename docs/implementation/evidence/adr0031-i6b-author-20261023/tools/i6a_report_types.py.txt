"""Evidence-only sidecar: preserve pytest report types and subtest context."""
import json,os,pathlib
_worker=False
_stream=None
def pytest_configure(config):
 global _worker,_stream
 _worker=hasattr(config,'workerinput')
 if not _worker:
  p=pathlib.Path(os.environ['I6A_REPORTS_SIDECAR']);p.parent.mkdir(parents=True,exist_ok=True);_stream=p.open('x')
def pytest_runtest_logreport(report):
 if _worker:return
 context=getattr(report,'context',None)
 row={'nodeid':report.nodeid,'phase':report.when,'outcome':report.outcome,'duration':round(report.duration,6),'report_type':type(report).__module__+'.'+type(report).__name__,'subtest_context':context._to_json() if context is not None else None}
 _stream.write(json.dumps(row,separators=(',',':'))+'\n');_stream.flush()
def pytest_unconfigure(config):
 if _stream:_stream.close()
