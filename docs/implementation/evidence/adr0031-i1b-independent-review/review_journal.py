"""Independent work-only collection/phase journal; capture serializer before tests."""
import pathlib,os,json
_dumps=json.dumps
_out=None
def pytest_sessionstart(session):
    global _out
    xml=session.config.option.xmlpath
    _out=pathlib.Path(str(xml)).parent/'journal.jsonl'
    _out.parent.mkdir(parents=True,exist_ok=True)
    _out.write_text('')
def emit(x):
    with _out.open('a') as f: f.write(_dumps(x,separators=(',',':'))+'\n')
def pytest_collection_finish(session):
    emit({'event':'collection','nodes':[i.nodeid for i in session.items]})
def pytest_runtest_logstart(nodeid,location): emit({'event':'start','nodeid':nodeid})
def pytest_runtest_logreport(report): emit({'event':'phase','nodeid':report.nodeid,'when':report.when,'outcome':report.outcome})
def pytest_runtest_logfinish(nodeid,location): emit({'event':'finish','nodeid':nodeid})
def pytest_sessionfinish(session,exitstatus): emit({'event':'sessionfinish','exit':int(exitstatus)})
