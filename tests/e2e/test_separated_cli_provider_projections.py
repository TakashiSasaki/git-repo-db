"""Real HTTP cross-endpoint projections preserve every original field producer."""

import json
from uuid import uuid4

import httpx
import pytest

from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.time import parse_iso8601_us
from tests.e2e.test_separated_cli import document
from tests.e2e.test_separated_cli_provider_regressions import (
    _connection,
    _http_response,
    _network_cli,
    _thread,
    values,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)

OLD = "2026-01-01T00:00:00Z"
NEW = "2026-02-01T00:00:00Z"
TARGET, ORIGINAL = "a" * 40, "b" * 40
OLD_HUNK, NEW_HUNK = "@@ -1 +1 @@\n-old", "@@ -1 +1 @@\n+new"


def full(endpoint, *, newer=False, body="old body", null_relationships=False):
    value = {
        "id": 10,
        "body": body,
        "updated_at": NEW if newer else OLD,
        "user": {"login": "new-author" if newer else "old-author"},
        "pull_request_review_id": None if null_relationships else 10,
        "in_reply_to_id": None if null_relationships else 11,
        "commit_id": TARGET,
        "original_commit_id": ORIGINAL,
        "path": "new.py" if newer else "old.py",
        "diff_hunk": NEW_HUNK if newer else OLD_HUNK,
        "position": 2 if newer else 1,
        "original_position": 1,
        "line": 20 if newer else 10,
        "original_line": 10,
        "side": "RIGHT",
    }
    if endpoint == "rest":
        return value
    renames = {
        "updated_at": "updatedAt",
        "user": "author",
        "diff_hunk": "diffHunk",
        "original_position": "originalPosition",
        "original_line": "originalLine",
    }
    result = {
        renames.get(key, key): item
        for key, item in value.items()
        if key
        not in {
            "id",
            "pull_request_review_id",
            "in_reply_to_id",
            "commit_id",
            "original_commit_id",
        }
    }
    result.update(
        id="opaque-comment-node",
        fullDatabaseId="10",
        pullRequestReview=None if null_relationships else {"fullDatabaseId": "10"},
        replyTo=None if null_relationships else {"fullDatabaseId": "11"},
        commit={"oid": TARGET},
        originalCommit={"oid": ORIGINAL},
    )
    return result


def partial(endpoint):
    if endpoint == "rest":
        return {
            "id": 10,
            "updated_at": NEW,
            "user": {"login": "new-author"},
            "diff_hunk": NEW_HUNK,
        }
    return {
        "id": "opaque-comment-node",
        "fullDatabaseId": "10",
        "updatedAt": NEW,
        "author": {"login": "new-author"},
        "diffHunk": NEW_HUNK,
    }


class Collector:
    def __init__(self, case, tmp_path, capsys, monkeypatch):
        self.case, self.tmp_path, self.capsys, self.monkeypatch = (
            case,
            tmp_path,
            capsys,
            monkeypatch,
        )
        self.stamp, self.calls = 1_000_000, []
        case.authority = document(
            tmp_path,
            "projection-authority.json",
            {
                "grants": DependencySet(
                    resources=frozenset(case.keys.values()),
                    sources=frozenset({case.source}),
                    provider_registrations=frozenset({case.service}),
                    object_oids=frozenset({OID("sha1", TARGET), OID("sha1", ORIGINAL)}),
                ),
                "selection": AdmissionSelection(all_selected=True),
            },
        )

    def collect(self, endpoint, value, *, intervening=None):
        def handle(request):
            self.stamp += 1_000_000
            self.calls.append((request.method, request.url.path))
            if request.method == "POST":
                parent = {
                    "id": "opaque-parent",
                    "fullDatabaseId": "11",
                    "body": "root",
                    "updatedAt": OLD,
                }
                result = {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "id": "PR_ACTUAL_20",
                                "number": 1,
                                "reviewThreads": _connection(
                                    [
                                        _thread(
                                            "thread-one", _connection([parent, value])
                                        )
                                    ]
                                ),
                            }
                        }
                    }
                }
            elif request.url.path.endswith("/comments"):
                result = [{"id": 11, "body": "root", "updated_at": OLD}, value]
            elif request.url.path.endswith("/pulls"):
                result = [{"id": 20, "number": 1}]
            elif request.url.path.endswith("/pulls/1"):
                result = {"id": 20, "number": 1}
            else:
                result = {"id": 10, "full_name": "owner/repo"}
            if intervening is not None and (
                request.method == "POST" or request.url.path.endswith("/comments")
            ):
                intervening()
            return _http_response(request, result)

        request = {
            "operation": "sync",
            "service_instance_uuidv4": self.case.service,
            "source_registration_uuidv4": self.case.source,
            "request_identity": [str(uuid4()), str(uuid4())],
            "new_request": True,
            "owner": "owner",
            "repository": "repo",
            "sections": ["review_comments" if endpoint == "rest" else "review_threads"],
            "response_bytes": 8192,
            "max_pages": 100,
            "rest_base_url": "https://api.example.test",
            "graphql_url": "https://api.example.test/graphql",
        }
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            report, _ = _network_cli(
                self.case,
                self.tmp_path,
                self.capsys,
                self.monkeypatch,
                client,
                request,
                clock_us=lambda: self.stamp,
            )
        assert report["status"] == "complete"
        return self.case.view(self.capsys, self.case.keys["comment"])


def assert_field(view, name, value, clock, endpoint=None):
    candidates = view["fields"][name]
    assert candidates and all(item["value"] == value for item in candidates)
    assert {item["clock"]["at_us"] for item in candidates} == {parse_iso8601_us(clock)}
    if endpoint is not None:
        suffix = (
            "/comments" if endpoint == "rest" else "/review_threads/thread-one/comments"
        )
        assert all(
            item["provenance"]["evidence"]["resource_path"].endswith(suffix)
            for item in candidates
        )
    assert all(item["observed_at_us"] > 0 for item in candidates)
    assert all("preferred_decoder" not in item for item in candidates)


@pytest.mark.parametrize("first", ["rest", "graphql"])
@pytest.mark.parametrize(
    "final_body",
    ["new exact\nbody\x00suffix", None, ""],
    ids=["exact", "null", "empty"],
)
@pytest.mark.parametrize("arrival", ["partial-first", "full-first"])
def test_real_http_cross_projection_preserves_field_producers_and_exact_body(
    provider_case, tmp_path, capsys, monkeypatch, first, final_body, arrival
):
    case = provider_case
    api = Collector(case, tmp_path, capsys, monkeypatch)
    other = "graphql" if first == "rest" else "rest"
    original = api.collect(first, full(first))
    original_body = original["fields"]["text_body_sha256"]
    if arrival == "partial-first":
        sparse = api.collect(other, partial(other))
        assert sparse["fields"]["text_body_sha256"] == original_body
        assert_field(sparse, "raw_path", "old.py", OLD, first)
        assert_field(sparse, "author", "new-author", NEW, other)
        assert_field(sparse, "diff_hunk", NEW_HUNK, NEW, other)
        assert_field(sparse, "review_id", "10", OLD, first)
        assert_field(sparse, "in_reply_to_id", "11", OLD, first)
        assert list(sparse["resolved_texts"].values()) == ["old body"]
    view = api.collect(
        first,
        full(first, newer=True, body=final_body, null_relationships=final_body is None),
    )
    if arrival == "full-first":
        view = api.collect(other, partial(other))
    # Explicit Provider null remains a known null text candidate; an omitted
    # body would retain the prior producer rather than create this candidate.
    assert set(view["resolved_texts"].values()) == {final_body}
    for name, value in {
        "raw_path": "new.py",
        "current_position": 2,
        "original_position": 1,
        "line": 20,
        "original_line": 10,
        "side": "RIGHT",
        "target_commit_object_oid": TARGET,
        "original_commit_object_oid": ORIGINAL,
        "review_id": None if final_body is None else "10",
        "in_reply_to_id": None if final_body is None else "11",
    }.items():
        assert_field(view, name, value, NEW, first)
    assert_field(view, "author", "new-author", NEW)
    assert_field(view, "diff_hunk", NEW_HUNK, NEW)
    assert set(values(view, "review_thread_id")) == {"thread-one"}
    # Relation originals survive scalar null; current foreign keys are never
    # inferred by mutating an older immutable report into a new source claim.
    assert any(
        relation["relation_kind"] == "in_reply_to"
        and relation["members"] == [list(case.keys["reply"].coordinates())]
        for relation in view["relations"]
    )
    assert not (case.directory / "core.sqlite3").exists()


@pytest.mark.parametrize("first", ["rest", "graphql"])
def test_real_http_older_full_fills_unknown_fields_without_reverting_newer_fields(
    provider_case, tmp_path, capsys, monkeypatch, first
):
    api = Collector(provider_case, tmp_path, capsys, monkeypatch)
    other = "graphql" if first == "rest" else "rest"
    api.collect(other, partial(other))
    view = api.collect(first, full(first, null_relationships=True))
    assert list(view["resolved_texts"].values()) == ["old body"]
    for name, value in {
        "raw_path": "old.py",
        "line": 10,
        "review_id": None,
        "in_reply_to_id": None,
        "target_commit_object_oid": TARGET,
        "original_commit_object_oid": ORIGINAL,
    }.items():
        assert_field(view, name, value, OLD, first)
    assert_field(view, "author", "new-author", NEW, other)
    assert_field(view, "diff_hunk", NEW_HUNK, NEW, other)


@pytest.mark.parametrize("first", ["rest", "graphql"])
def test_real_http_equal_clock_conflict_survives_concurrent_unrelated_publication(
    provider_case, tmp_path, capsys, monkeypatch, first
):
    from tests.e2e.test_separated_cli_provider_regressions import issue

    case = provider_case
    api = Collector(case, tmp_path, capsys, monkeypatch)
    other = "graphql" if first == "rest" else "rest"
    api.collect(other, partial(other))
    contradictory = full(first, newer=True, body="new body", null_relationships=True)
    contradictory["diff_hunk" if first == "rest" else "diffHunk"] = "contradictory"

    def publish_unrelated():
        case.admit(
            tmp_path,
            capsys,
            issues=(issue({"id": 100, "title": "unrelated writer", "updated_at": 50}),),
        )

    view = api.collect(first, contradictory, intervening=publish_unrelated)
    assert set(values(view, "diff_hunk")) == {NEW_HUNK, "contradictory"}
    assert_field(view, "author", "new-author", NEW)
    assert (
        len(
            {
                json.dumps(item["provenance"], sort_keys=True)
                for item in view["fields"]["diff_hunk"]
            }
        )
        == 2
    )
    assert set(values(case.view(capsys, case.keys["issue"]), "title")) == {
        "unrelated writer"
    }
    assert not (case.directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("endpoint", ["rest", "graphql"])
def test_live_http_names_actual_normalizer_without_rewriting_or_ranking_imported_producer(
    provider_case, tmp_path, capsys, monkeypatch, endpoint
):
    from repo_catalog.adapters.github.production_intake import (
        NORMALIZER_MODULE,
        NORMALIZER_VERSION,
    )
    from repo_catalog.domain.provider_acquisition import (
        ProviderReviewCommentIntake,
        make_provenance,
    )

    case = provider_case
    api = Collector(case, tmp_path, capsys, monkeypatch)
    live = api.collect(endpoint, full(endpoint))
    live_originals = live["fields"]["text_body_sha256"]
    assert live_originals and all(
        candidate["provenance"]["evidence"]["normalizer"]
        == {
            "module": NORMALIZER_MODULE,
            "version": NORMALIZER_VERSION,
        }
        for candidate in live_originals
    )
    assert all(
        candidate["provenance"]["evidence"]["read_origin"]["http_attempt_uuidv4"]
        for candidate in live_originals
    )
    original = make_provenance(
        "peer-reported-producer",
        {
            "normalizer": {"module": "independent.peer.decoder", "version": "999999"},
            "capture": "unchanged-peer-original",
        },
    )
    case.admit(
        tmp_path,
        capsys,
        review_comments=(
            ProviderReviewCommentIntake(
                "20",
                {"id": 10, "body": "peer body", "updated_at": OLD},
                2**60,
                original,
            ),
        ),
    )
    view = case.view(capsys, case.keys["comment"])
    assert set(view["resolved_texts"].values()) == {"old body", "peer body"}
    candidates = view["fields"]["text_body_sha256"]
    assert any(
        candidate["provenance"] == json.loads(original)
        and candidate["observed_at_us"] == 2**60
        for candidate in candidates
    )
    assert all(candidate in candidates for candidate in live_originals)
    assert {candidate["clock"]["at_us"] for candidate in candidates} == {
        parse_iso8601_us(OLD)
    }
