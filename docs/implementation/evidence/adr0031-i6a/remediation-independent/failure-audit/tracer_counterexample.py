"""Deterministic synthetic controls for the reviewer's trace event predicates."""
import ast
from io import StringIO
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
os.environ.setdefault('REVIEW_TRACE_SOURCE',str(HERE.parents[5]))
os.environ.setdefault('REVIEW_TRACE_OUTPUT','/tmp/unused-reviewer-trace-controls')
import reviewer_trace as tracer

code='''def branch(flag):
    assert True
    if flag:
        assert False

def failed():
    assert True
    assert False
    assert True

def denied():
    raise AdmissionRefused("denied")
'''
filename='<reviewer-trace-synthetic-control>'
assertlines={n.lineno for n in ast.walk(ast.parse(code)) if isinstance(n,ast.Assert)}
tracer._cache[filename]=('tests/synthetic_trace_control.py',assertlines)
class AdmissionRefused(Exception):pass
ns={'AdmissionRefused':AdmissionRefused}
exec(compile(code,filename,'exec'),ns)
tracer._stream=StringIO()

def run(name,*args):
    tracer._node=name;tracer._phase='call';tracer._seen=set()
    sys.settrace(tracer.trace)
    try:ns[name](*args)
    except (AssertionError,AdmissionRefused):pass
    finally:sys.settrace(None)

run('branch',False)
run('failed')
run('denied')
events=[json.loads(l) for l in tracer._stream.getvalue().splitlines()]
entered=lambda name:[r['line'] for r in events if r['nodeid']==name and r['event']=='assertion_line']
checks={'chosen_assert_entered':entered('branch')==[2],'unchosen_conditional_absent':4 not in entered('branch'),'failing_assert_entered':entered('failed')==[7,8],'post_failure_assert_absent':9 not in entered('failed'),'admission_exception_stack':any(r['event']=='admission_exception' and r['stack'][0]['line']==12 and r['message']=='denied' for r in events)}
assert all(checks.values()),(checks,events)
(HERE/'tracer-counterexample.json').write_text(json.dumps({'checks':checks,'events':events,'limit':'Synthetic tracing predicate controls; actual tests validate path recognition and pytest lifecycle separately.'},indent=2)+'\n')
print(json.dumps(checks))
