"""Challenge the candidate validator separately from its illustrative DDL.

Synthetic catalogs only. Declared unimplemented responsibilities are reported as
limits, not as successful integrity checks or defects in production Schema 18.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def load(directory):
    path = directory / "candidate_probe.py"
    spec = importlib.util.spec_from_file_location("candidate_review_target", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reject(module, operation):
    try:
        operation()
    except module.InvalidProof:
        return True
    return False


def current_receipt(module, db):
    p = module
    p.put(
        db,
        "review_threads",
        thread_id="thread-1",
        change_request_id="pr-1",
        repository_uuid=p.ident(11),
        provider_thread_id="provider-thread-1",
    )
    p.put(
        db,
        "review_resources",
        change_request_id="pr-1",
        kind="review-comment",
        provider_document_id="61",
        repository_uuid=p.ident(11),
        field_evidence_json="{}",
    )
    cid = p.collection(db, 80, kind="thread-comments", thread="thread-1")
    digest = p.manifest({"witnessed_body": "old exact text"})
    p.put(
        db,
        "review_receipt_members",
        collection_uuid=cid,
        ordinal=0,
        position=0,
        repository_uuid=p.ident(11),
        change_request_id="pr-1",
        kind="review-comment",
        provider_document_id="61",
        captured_thread_id="thread-1",
        observed_state_digest=digest,
    )
    rows = [
        [0, "review_receipt_members", ["pr-1", "review-comment", "61"], digest.hex()]
    ]
    db.execute(
        "UPDATE repository_collection_fragments SET member_count=1,member_digest=? WHERE collection_uuid=?",
        (p.manifest(rows), cid),
    )
    db.execute(
        "UPDATE repository_collection_seals SET member_count=1,member_digest=? WHERE collection_uuid=?",
        (p.manifest([[0, *row] for row in rows]), cid),
    )
    return cid


def probe(p):
    constraints, limits = {}, {}
    with p.connect() as db:
        p.base(db)
        uid, digest = p.pr(db, 17)
        cid = p.collection(db, 81, members=[(uid, digest)])
        constraints["valid_modeled_pr_member"] = p.validate_collection(db, cid) == 100
        db.execute(
            "UPDATE change_request_observations SET head_oid=? WHERE observation_uuid=?",
            (bytes([99]) * 20, uid),
        )
        constraints["tampered_retained_head_rejected"] = reject(
            p, lambda: p.validate_collection(db, cid)
        )

    with p.connect() as db:
        p.base(db)
        uid, digest = p.pr(db, 18)
        cid = p.collection(db, 82, members=[(uid, digest)])
        db.execute(
            "UPDATE pr_observation_fields SET module='different.module',version='999' WHERE observation_uuid=?",
            (uid,),
        )
        constraints["field_module_origin_mismatch_rejected"] = reject(
            p, lambda: p.validate_collection(db, cid)
        )

    with p.connect() as db:
        p.base(db)
        uid, _ = p.pr(db, 19)
        p.put(
            db,
            "repository_publication_seals",
            publication_uuid=p.ident(41),
            repository_uuid=p.ident(11),
            member_count=0,
            member_digest=p.manifest([]),
            sealed_at_us=200,
        )
        limits["publication_seal_exact_membership_not_enforced"] = (
            db.execute("SELECT observation_uuid FROM pr_maximal_candidates").fetchone()[
                0
            ]
            == uid
        )

    with p.connect() as db:
        p.base(db)
        cid = current_receipt(p, db)
        constraints["current_receipt_before_mutation"] = (
            p.validate_collection(db, cid) == 100
        )
        raw = b"new exact text after receipt time"
        digest = p.sha(raw)
        p.put(db, "domain_bytes", sha256=digest, body=raw, byte_length=len(raw))
        p.put(db, "text_bodies", sha256=digest)
        db.execute(
            "UPDATE review_resources SET body_sha256=? WHERE provider_document_id='61'",
            (digest,),
        )
        constraints["old_current_receipt_does_not_require_edit_history"] = (
            p.validate_collection(db, cid) == 100
        )
        p.put(
            db,
            "review_threads",
            thread_id="thread-2",
            change_request_id="pr-1",
            repository_uuid=p.ident(11),
            provider_thread_id="provider-thread-2",
        )
        db.execute(
            "UPDATE review_receipt_members SET captured_thread_id='thread-2' WHERE collection_uuid=?",
            (cid,),
        )
        constraints["wrong_captured_thread_rejected"] = reject(
            p, lambda: p.validate_collection(db, cid)
        )

    assert all(constraints.values()), constraints
    return {"validated_constraints": constraints, "declared_limits_reproduced": limits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prototype-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    p = load(args.prototype_dir)
    report = {
        "kind": "independent-candidate-validator-attacks-v1",
        "files_sha256": {
            name: hashlib.sha256((args.prototype_dir / name).read_bytes()).hexdigest()
            for name in ("candidate.sql", "candidate_probe.py")
        },
        "actual_results": probe(p),
        "limits": [
            "Candidate is Proposed/Pending Owner Decision, not production.",
            "Declared limits require chosen-model admission rules before production use.",
            "Value digest checks do not validate parser authenticity or new Exchange trust.",
        ],
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
