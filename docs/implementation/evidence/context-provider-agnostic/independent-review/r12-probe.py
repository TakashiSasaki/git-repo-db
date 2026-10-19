"""Independent R1/R2 synthetic assertions against the actual Context facade.

Run with the repository's supported Python/SQLite environment. Prints a JSON
receipt and uses disposable databases only; it does not overwrite review evidence.
"""

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingDisposition,
    MappingOperationEvidence,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.production_context import CoreReference, ResourceRelation

S = "11111111-1111-4111-8111-111111111111"
T = "22222222-2222-4222-8222-222222222222"
R = "33333333-3333-4333-8333-333333333333"
Q = "44444444-4444-4444-8444-444444444444"
INSTANCE = "55555555-5555-4555-8555-555555555555"
prov = canonical(
    {"source": "independent synthetic reviewer", "evidence": "r12-original"}
)
results = []


def check(name, actual, expected):
    assert actual == expected, (name, actual, expected)
    results.append({"case": name, "actual": actual, "expected": expected, "pass": True})


assert sqlite3.sqlite_version_info >= (3, 51, 3)
with tempfile.TemporaryDirectory(prefix="r12-context-") as tmp:
    path = Path(tmp)
    initialize(path / "context.sqlite3", "context", R, INSTANCE)
    with Context.transaction(path) as c:
        c.provider(S, "github", "{}")
        c.provider(T, "gitlab", "{}")
        c.repository(R)
        c.repository(Q)
        repo = ResourceKey(S, "repository", "7")
        repo2 = ResourceKey(T, "repository", "7")
        issue = ResourceKey(S, "issue", "7")
        annotation = ResourceKey(S, "annotation", "analysis-1")
        for key in (repo, repo2, issue, annotation):
            c.resource(key)
        check("same-id-distinct-service-kind", len(c.resources()), 4)
        for name, key in [
            (
                "repository-document",
                ResourceKey.document(repo, "document", "wiki", "d1"),
            ),
            ("issue-thread", ResourceKey.document(issue, "thread", "discussion", "d1")),
            (
                "commit-review",
                ResourceKey.document(annotation, "review", "commit-review", "d1"),
            ),
            ("unknown-kind", ResourceKey(S, "discussion", "d1")),
        ]:
            try:
                c.resource(key)
            except sqlite3.IntegrityError:
                rejected = True
            else:
                rejected = False
            check(name + "-DDL-rejection", rejected, True)
        c.relation(
            ResourceRelation(annotation, "annotates", (repo, repo2), prov, "{}", 10)
        )
        check(
            "annotation-provider-targets",
            len(c.relations(annotation, "annotates")[0].members),
            2,
        )
        c.report_core_reference(
            CoreReference(annotation, "analyzed_commit", OID("sha1", "a" * 40), prov),
            clock=FieldClock("scanner", 1),
            observed_at_us=10,
        )
        deps = c.core_dependencies(annotation, lambda *_: False)
        check(
            "missing-core-report",
            [(d.available, d.required) for d in deps],
            [(False, False)],
        )
        m1 = ResourceRepositoryRelation(
            repo,
            "represents_repository",
            FieldClock("mapping", 1),
            canonical(R),
            prov,
            10,
        )
        m2 = ResourceRepositoryRelation(
            repo2,
            "represents_repository",
            FieldClock("mapping", 1),
            canonical(R),
            prov,
            10,
        )
        for m in (m1, m2):
            c.admit_repository_relation(m)
        check(
            "reverse-multi-provider",
            len(c.relations_for_repository(R, "represents_repository")),
            2,
        )
        check("forward-provider", len(c.relations_for_provider_repository(repo)), 1)
        m3 = ResourceRepositoryRelation(
            repo,
            "represents_repository",
            FieldClock("mapping", 2),
            canonical(Q),
            prov,
            11,
        )
        c.admit_repository_relation(m3)
        check(
            "conflicting-mapping",
            c.evaluate_provider_repository(repo).state,
            "conflict",
        )
        check("mapping-exact-replay", c.admit_repository_relation(m3), "duplicate")
        disp = MappingDisposition(
            m3.claim_key, "withdraw", FieldClock("mapping", 3), prov, 12
        )
        c.admit_mapping_disposition(disp)
        check(
            "unconfirmed-withdraw-retains-conflict",
            c.evaluate_provider_repository(repo).state,
            "conflict",
        )
        evidence = MappingOperationEvidence(
            confirmed_disposition_keys=frozenset({disp.disposition_key})
        )
        check(
            "qualified-withdraw-single",
            c.evaluate_provider_repository(repo, evidence=evidence).state,
            "single_candidate",
        )
        check(
            "no-core-file-required-for-mapping", (path / "core.sqlite3").exists(), False
        )

print(
    json.dumps(
        {
            "reviewer": "independent R1/R2",
            "python": sys.version,
            "sqlite": sqlite3.sqlite_version,
            "input": "synthetic; actual Context transaction and domain types; no Provider API calls",
            "results": results,
        },
        indent=2,
    )
)
