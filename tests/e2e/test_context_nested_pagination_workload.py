"""A bounded ordinary GraphQL workload follows every root and child continuation."""

import json

import httpx

from repo_catalog.adapters.github.production_intake import make_document_key
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from tests.e2e.test_context_response_boundary_retirement import request_document
from tests.e2e.test_separated_cli import document
from tests.e2e.test_separated_cli_pr_assessment import query
from tests.e2e.test_separated_cli_provider_regressions import (
    _comment,
    _connection,
    _http_response,
    _network_cli,
    _thread,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)

THREADS = 32
COMMENTS = 8
ROOT_WIDTH = 4
CHILD_WIDTH = 4


def thread_id(number):
    return f"stress-thread-{number:02d}"


def comment_id(thread, comment):
    return 1000 + thread * COMMENTS + comment


def comment_text(thread, comment):
    return f"thread {thread:02d} comment {comment}: é\x00\r\n"


def test_actual_many_page_graphql_workload_preserves_every_nested_member_and_whole_proof(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    threads = {
        number: make_document_key(
            case.keys["pull"], "review_thread", "thread", thread_id(number)
        )
        for number in range(THREADS)
    }
    comments = {
        (number, index): make_document_key(
            case.keys["pull"],
            "review_comment",
            "review_comment",
            str(comment_id(number, index)),
        )
        for number in range(THREADS)
        for index in range(COMMENTS)
    }
    case.authority = document(
        tmp_path,
        "nested-workload-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values())
                | frozenset(threads.values())
                | frozenset(comments.values()),
                sources={case.source},
                provider_registrations={case.service},
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    root_calls, child_calls, root_times, child_times = [], [], {}, {}
    received, clock = [], [0]

    def comment(number, index):
        return {
            **_comment(comment_id(number, index)),
            "body": comment_text(number, index),
        }

    def handle(http):
        clock[0] += 1000
        received.append((http.method, http.url.path))
        if http.method != "POST":
            if http.url.path.endswith("/pulls"):
                value = [{"id": 20, "number": 1}]
            elif http.url.path.endswith("/pulls/1"):
                value = {"id": 20, "number": 1}
            else:
                assert http.url.path == "/repos/owner/repo"
                value = {"id": 10, "full_name": "owner/repo"}
            return _http_response(http, value)
        assert http.url.path == "/graphql"
        variables = json.loads(http.content)["variables"]
        if "id" in variables:
            number = int(variables["id"].rsplit("-", 1)[1])
            assert variables == {
                "id": thread_id(number),
                "cursor": f"comments-{number}-4",
            }
            child_calls.append(number)
            child_times[number] = clock[0]
            value = {
                "node": {
                    "id": thread_id(number),
                    "comments": _connection(
                        [
                            comment(number, index)
                            for index in range(CHILD_WIDTH, COMMENTS)
                        ]
                    ),
                }
            }
        else:
            cursor = variables["cursor"]
            page = 0 if cursor is None else int(cursor.rsplit("-", 1)[1])
            assert variables == {
                "owner": "owner",
                "name": "repo",
                "number": 1,
                "cursor": None if page == 0 else f"roots-{page}",
            }
            assert 0 <= page < THREADS // ROOT_WIDTH
            root_calls.append(cursor)
            root_times[page] = clock[0]
            values = [
                _thread(
                    thread_id(number),
                    _connection(
                        [comment(number, index) for index in range(CHILD_WIDTH)],
                        next_cursor=f"comments-{number}-4",
                    ),
                )
                for number in range(page * ROOT_WIDTH, (page + 1) * ROOT_WIDTH)
            ]
            value = {
                "repository": {
                    "pullRequest": {
                        "id": "PR_ACTUAL_20",
                        "number": 1,
                        "reviewThreads": _connection(
                            values,
                            next_cursor=f"roots-{page + 1}"
                            if page + 1 < THREADS // ROOT_WIDTH
                            else None,
                        ),
                    }
                }
            }
        return _http_response(http, {"data": value})

    request = request_document(case)
    request.update(sections=["review_threads"], max_pages=43, response_bytes=8192)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: clock[0],
        )
    assert report["status"] == "complete" and report["failure_code"] is None
    assert report["http_attempts"] == len(received) == 43
    assert root_calls == [
        None,
        *(f"roots-{page}" for page in range(1, THREADS // ROOT_WIDTH)),
    ]
    assert child_calls == list(range(THREADS))
    with Context.snapshot(case.directory) as context:
        assert (
            context.db.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='thread'"
            ).fetchone()[0]
            == THREADS
        )
        assert (
            context.db.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='comment'"
            ).fetchone()[0]
            == THREADS * COMMENTS
        )
        rows = context.db.execute(
            "SELECT service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,"
            "provenance_json,observed_at_us,terminal_state,members_json FROM collection_terminals "
            "WHERE collection_kind IN('review_threads','review_thread_comments')"
        ).fetchall()
        root_rows = [row for row in rows if row[3] == "review_threads"]
        assert len(root_rows) == THREADS // ROOT_WIDTH
        assert sorted(len(json.loads(row[7])) for row in root_rows) == list(
            range(ROOT_WIDTH, THREADS + 1, ROOT_WIDTH)
        )
        (root_complete,) = [row for row in root_rows if row[6] == "complete"]
        assert json.loads(root_complete[7]) == [
            list(threads[number].coordinates()) for number in range(THREADS)
        ]
        for number, key in threads.items():
            child_rows = [row for row in rows if tuple(row[:3]) == key.coordinates()]
            assert len(child_rows) == 2
            (partial,) = [row for row in child_rows if row[6] == "partial"]
            (complete,) = [row for row in child_rows if row[6] == "complete"]
            assert json.loads(partial[7]) == [
                list(comments[number, index].coordinates())
                for index in range(CHILD_WIDTH)
            ]
            assert json.loads(complete[7]) == [
                list(comments[number, index].coordinates()) for index in range(COMMENTS)
            ]
            assert partial[5] == root_times[number // ROOT_WIDTH]
            assert complete[5] == child_times[number]
        complete_keys = {
            (*tuple(row[:5]), row[5], row[6], row[7])
            for row in rows
            if row[6] == "complete"
        }
        proofs = context.db.execute(
            "SELECT service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,"
            "provenance_json,terminal_observed_at_us,terminal_state,members_json FROM coverage_proofs "
            "WHERE collection_kind IN('review_threads','review_thread_comments') AND coverage_state='complete'"
        ).fetchall()
        assert len(proofs) == THREADS + 1
        assert {tuple(row) for row in proofs} == complete_keys
        body_rows = context.db.execute(
            "SELECT f.provider_resource_id,f.observed_at_us,f.provenance_json,t.text_value "
            "FROM field_candidates f JOIN text_bodies t ON json_extract(f.value_json,'$')=t.sha256 "
            "WHERE f.resource_kind='comment' AND f.field_name='text_body_sha256'"
        ).fetchall()
        assert len(body_rows) == THREADS * COMMENTS
        by_id = {row[0]: row for row in body_rows}
        for (number, index), key in comments.items():
            row = by_id[key.provider_resource_id]
            assert row[3] == comment_text(number, index)
            assert row[1] == (
                root_times[number // ROOT_WIDTH]
                if index < CHILD_WIDTH
                else child_times[number]
            )
            evidence = json.loads(row[2])["evidence"]
            assert evidence["source_registration_uuidv4"] == case.source
            assert evidence["request_identity"] == request["request_identity"]
            assert evidence["resource_path"].endswith(
                "/" + thread_id(number) + "/comments"
            )
        assert context.db.execute("PRAGMA foreign_key_check").fetchall() == []
    result = query(
        capsys,
        case,
        "pr-documents",
        "--kind",
        "review_threads",
        "--limit",
        1000,
        "--max-work",
        1000000,
        "--max-bytes",
        4194304,
        "--max-rows",
        50000,
        "--max-sql-steps",
        10000000,
        "--timeout-seconds",
        60,
    )
    assert (
        result["state"] == "complete"
        and result["coverage"]["complete_for_requested_scope"]
    )
    assert result["coverage"]["missing"] == [] and not result["has_more"]
    assert result["next_cursor"] is None
    assert result["total_count"] == len(result["items"]) == THREADS * (COMMENTS + 1)
    actual = {
        (
            item["service_instance_uuidv4"],
            item["resource_kind"],
            item["provider_resource_id"],
        )
        for item in result["items"]
    }
    assert actual == {
        key.coordinates() for key in (*threads.values(), *comments.values())
    }
    assert {
        text for item in result["items"] for text in item["resolved_texts"].values()
    } == {
        comment_text(number, index)
        for number in range(THREADS)
        for index in range(COMMENTS)
    }
    assert not (case.directory / "core.sqlite3").exists()
    assert not (case.directory / "transport-archive").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()
