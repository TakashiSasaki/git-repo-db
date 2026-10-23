"""Reviewer diagnostic tracer: actual assert statement entry and admission raises.

No modification of product/test code. Covers the executing main Python thread,
not spawned processes/threads; pytest report capture remains separate.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import pytest

ROOT=Path(os.environ['REVIEW_TRACE_SOURCE']).resolve()
OUT=Path(os.environ['REVIEW_TRACE_OUTPUT']).resolve()
_stream=None
_node=None
_phase=None
_cache={}
_seen=set()


def emit(event,**kw):
    _stream.write(json.dumps(dict(event=event,nodeid=_node,phase=_phase,**kw))+'\n')
    _stream.flush()


def relevant(filename):
    if filename not in _cache:
        p=Path(filename)
        try:r=p.resolve().relative_to(ROOT).as_posix()
        except (ValueError,OSError):r=''
        if r.startswith(('tests/','src/repo_catalog/')) and p.suffix=='.py':
            asserts={x.lineno for x in ast.walk(ast.parse(p.read_text())) if isinstance(x,ast.Assert)} if r.startswith('tests/') else set()
            _cache[filename]=(r,asserts)
        else:_cache[filename]=None
    return _cache[filename]


def trace(frame,event,arg):
    r=relevant(frame.f_code.co_filename)
    if r is None:return None
    if event=='line' and frame.f_lineno in r[1]:
        k=(_phase,r[0],frame.f_lineno)
        if k not in _seen:
            _seen.add(k)
            emit('assertion_line',path=r[0],line=frame.f_lineno,function=frame.f_code.co_name)
    elif event=='exception':
        cls,exc,tb=arg
        if cls.__name__=='AdmissionRefused':
            stack=[]
            f=frame
            while f:
                rr=relevant(f.f_code.co_filename)
                if rr:stack.append(dict(path=rr[0],line=f.f_lineno,function=f.f_code.co_name))
                f=f.f_back
            emit('admission_exception',exception_type=cls.__module__+'.'+cls.__name__,message=str(exc),stack=stack)
    return trace


def product_origins(stage):
    import repo_catalog
    origin=Path(repo_catalog.__file__).resolve()
    assert origin.is_relative_to(ROOT/'src'),str(origin)
    modules={}
    for name,module in list(sys.modules.items()):
        if name=='repo_catalog' or name.startswith('repo_catalog.'):
            file=getattr(module,'__file__',None)
            if file:
                path=Path(file).resolve()
                assert path.is_relative_to(ROOT/'src'),(name,str(path))
                modules[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    emit('product_origins',stage=stage,modules=modules)


def pytest_configure(config):
    global _stream
    OUT.mkdir(parents=True,exist_ok=True)
    worker=getattr(config,'workerinput',{}).get('workerid','master')
    _stream=(OUT/(worker+'.jsonl')).open('x')
    emit('configure',worker=worker,source=str(ROOT),optimization=sys.flags.optimize)
    assert sys.flags.optimize==0
    product_origins('configure')


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item,nextitem):
    global _node,_seen
    assert sys.gettrace() is None
    _node=item.nodeid
    _seen=set()
    emit('start')
    sys.settrace(trace)
    try:yield
    finally:
        sys.settrace(None)
        emit('finish')
        _node=None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    global _phase
    _phase='setup'
    try:yield
    finally:_phase=None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    global _phase
    _phase='call'
    try:yield
    finally:_phase=None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    global _phase
    _phase='teardown'
    try:yield
    finally:_phase=None


def pytest_sessionfinish(session,exitstatus):
    product_origins('session_finish')
    emit('session_finish',exitstatus=int(exitstatus))


def pytest_unconfigure(config):
    if _stream:_stream.close()
