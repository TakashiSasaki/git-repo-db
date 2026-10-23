"""Minimal independent confirmation of real admission queue growth at exhaustion.

No shared scanner helper, production replacement, Transfer unfencing or test
fixture. The observer records only actual C list.extend entry/return snapshots.
No timings or total-allocation measurement is claimed.
"""

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain import context_admission as ca
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.production_context import ResourceRelation
from repo_catalog.domain.resource_stage import has_transfer_fence

SERVICE = "89736f10-3371-4cf7-806b-c023921e3883"


class NoGrant:
    calls = 0

    def lease(self, *args):
        self.calls += 1
        raise AssertionError("no policy should be reached before input refusal")


def main():
    db = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(db)
    p1_schema.configure(db)
    db.executescript(p1_schema.compose("context"))
    db.execute("INSERT INTO store_identity VALUES('context',?,?)", (
        "57c943db-cfa5-407e-b1c0-04a223ad1782", "76fc946f-6337-4c1a-876e-e743197c5a07"))
    p1_schema.validate(db, "context")
    assert has_transfer_fence(db)
    owner = ResourceKey.from_native(SERVICE, "issue", "owner")
    members = tuple(ResourceKey.from_native(SERVICE, "issue", str(i)) for i in range(1000))
    relation = ResourceRelation(owner, "x-links", members,
        '{"evidence":"independent","source":"review"}', "{}", 1)
    policy = NoGrant()
    service = ca.ContextAdmissionService(policy, lambda credential: "review-session")
    budget = ca.AdmissionBudget(work_limit=10000)
    handle = service.context("local", "provider_intake", ca.AdmissionSelection(
        resource_keys=frozenset({owner,*members}), repository_uuidv4s=(),
        source_uuidv4s=(), object_oids=(), max_work=10000), budget)
    budget.charge(work=9992)
    seen = []
    def observe(frame, event, function):
        if frame.f_code is ca.ContextAdmissionService.charge_input.__code__ and event in ("c_call","c_return"):
            target = getattr(function,"__self__",None)
            if getattr(function,"__name__",None)=="extend" and type(target) is list:
                seen.append({"event":event,"source_line":frame.f_lineno,
                    "actual_queue_length":len(target),"used_work":budget.used_work,
                    "actual_member_references":sum(type(item) is tuple and len(item)==2 and isinstance(item[0],ResourceKey) and item[0] in members for item in target)})
    prior_profile = sys.getprofile()
    sql = []
    db.set_trace_callback(sql.append)
    try:
        with tempfile.TemporaryDirectory(prefix="pr155-independent-queue-") as directory:
            with Context.owned_transaction(db,Path(directory),authorization=service,admission=handle) as facade:
                sys.setprofile(observe)
                try:
                    facade.relation(relation,admission=handle)
                finally:
                    sys.setprofile(prior_profile)
    except ca.AdmissionRefused as error:
        outcome=error.code
    else:
        raise AssertionError("expected finite-work refusal")
    db.set_trace_callback(None)
    assert outcome=="INPUT_LIMIT"
    assert any(item["event"]=="c_return" and item["used_work"]==10000 and item["actual_queue_length"]==1002 and item["actual_member_references"]==1000 for item in seen)
    assert budget.used_work==10001 and policy.calls==0
    assert db.execute("SELECT count(*) FROM resource_relations").fetchone()[0]==0
    assert not db.in_transaction and has_transfer_fence(db)
    result={"outcome":outcome,"work_limit":10000,"prior_work":9992,
        "input_children":1000,"input_members_json_bytes":len(relation.members_json.encode()),
        "events":seen,"final_used_work":budget.used_work,"policy_calls":policy.calls,
        "rows_after":0,"transaction_open":False,"both_exact_fences_preserved":True,
        "sql":sql,"scanner_origin":ca.__file__,
        "scanner_sha256":hashlib.sha256(Path(ca.__file__).read_bytes()).hexdigest(),
        "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "executable":sys.executable,"sqlite_version":sqlite3.sqlite_version}
    db.close()
    Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("outcome","final_used_work","policy_calls","rows_after")}))


if __name__=="__main__":
    main()
