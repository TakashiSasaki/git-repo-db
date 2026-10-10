"""Strict local API server: real HTTP, synthetic payloads, controllable failures."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class GitHubFixture:
    def __init__(self, git_fixture):
        self.git = git_fixture
        self.stage = "A"
        self.requests = []
        self.failures = {}
        self.errors = []
        self.graphql_partial = False
        self.etag = False
        self.thread_count = 1
        self.reply_count = 1
        self.cap_mode = False
        self.incremental = False
        self.gzip = False
        self.inventory_verified = True
        alpha = git_fixture.alpha
        alpha.commit("P", {**git_fixture.m, b"pr-only.txt": b"pr-marker"}, ("N",))
        alpha.ref("refs/pull/41/head", "P")
        for n in (42, 43):
            alpha.ref(f"refs/pull/{n}/head", "P")
        self.prs = {
            n: {
                "id": 10000 + n,
                "node_id": f"PR{n}",
                "number": n,
                "title": f"title-marker {n}",
                "body": "body-marker 認証",
                "state": "open" if n == 41 else "closed",
                "draft": n == 41,
                "merged": n == 43,
                "merged_at": "2026-01-01T00:00:00Z" if n == 43 else None,
                "user": {"login": "writer"},
                "html_url": f"https://github.com/fixture/alpha/pull/{n}",
                "head": {"sha": alpha.commits["P"], "ref": "feature", "repo": None},
                "base": {"sha": alpha.commits["N"], "ref": "main", "repo": {"id": 101}},
                "commits": 1,
                "changed_files": 1,
                "assignees": [],
            }
            for n in (41, 42, 43)
        }
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.respond("GET")

            def do_POST(self):
                self.respond("POST")

            def respond(self, method):
                route = urlsplit(self.path)
                params = parse_qs(route.query)
                owner.requests.append((method, route.path, params))
                if (
                    self.headers.get("Authorization") != "Bearer fixture-dummy"
                    or self.headers.get("X-GitHub-Api-Version") != "2026-03-10"
                ):
                    owner.errors.append("missing auth/API version")
                    self.send_json(401, {"message": "Bad credentials"})
                    return
                pending = owner.failures.get(route.path)
                if pending:
                    status = pending.pop(0)
                    self.send_json(
                        status,
                        {"message": "injected"},
                        {"Retry-After": "60"} if status == 429 else {},
                    )
                    return
                try:
                    body = (
                        json.loads(
                            self.rfile.read(
                                int(self.headers.get("Content-Length", "0"))
                            )
                        )
                        if method == "POST"
                        else None
                    )
                    payload, headers = owner.route(method, route.path, params, body)
                    if (
                        owner.etag
                        and method == "GET"
                        and route.path.rsplit("/", 1)[-1] in ("41", "42", "43")
                    ):
                        tag = '"' + owner.stage + '"'
                        headers["ETag"] = tag
                        if self.headers.get("If-None-Match") == tag:
                            self.send_json(304, None, headers)
                            return
                    self.send_json(200, payload, headers)
                except (KeyError, AssertionError, ValueError) as e:
                    owner.errors.append(f"{method} {route.path}: {type(e).__name__}")
                    self.send_json(422, {"message": "Unknown request"})

            def send_json(self, status, payload, headers=None):
                raw = b"" if status == 304 else json.dumps(payload).encode()
                extra = dict(headers or {})
                if owner.gzip and raw:
                    import gzip

                    raw = gzip.compress(raw)
                    extra["Content-Encoding"] = "gzip"
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for k, v in extra.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        # Shorten idle shutdown polling, not API retries/backoff or real HTTP.
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True
        )

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def comment(self, n, provider=501):
        return {
            "id": provider,
            "node_id": f"RC{provider}",
            "body": f"review-comment-marker {self.stage}",
            "user": {"login": "reviewer"},
            "html_url": f"https://github.com/fixture/alpha/pull/{n}#discussion_r{provider}",
            "commit_id": self.git.alpha.commits["P"],
            "original_commit_id": self.git.alpha.commits["N"],
            "path": "pr-only.txt",
            "line": 1,
            "original_line": 1,
            "side": "RIGHT",
            "diff_hunk": "@@ -0,0 +1 @@\n+pr-marker",
        }

    def route(self, method, path, params, body):
        if method == "POST":
            assert path == "/graphql" and "mutation" not in body["query"]
            v = body["variables"]
            n = v.get("number") or int(v["thread"].removeprefix("THREAD").split("-")[0])

            def comments(index, start=0):
                nodes = []
                count = self.reply_count if n == 41 else 1
                for reply in range(start, min(count, start + 100)):
                    c = self.comment(
                        n,
                        501 + n
                        if index == reply == 0
                        else n * 1000000 + index * 1000 + reply,
                    )
                    nodes.append(
                        {
                            "id": c["node_id"],
                            "fullDatabaseId": str(c["id"]),
                            "body": c["body"],
                            "author": {"login": "reviewer"},
                            "url": c["html_url"],
                            "path": c["path"],
                            "line": 1,
                            "originalLine": 1,
                            "diffHunk": c["diff_hunk"],
                            "commit": {"oid": c["commit_id"]},
                            "originalCommit": {"oid": c["original_commit_id"]},
                        }
                    )
                return {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": start + 100 < count,
                        "endCursor": str(start + 100) if start + 100 < count else None,
                    },
                }

            if "thread" in v:
                index = int(v["thread"].split("-")[1])
                start = int(v["commentCursor"])
                return {
                    "data": {
                        "node": {"id": v["thread"], "comments": comments(index, start)}
                    }
                }, {}
            start = int(v.get("cursor") or 0)
            count = self.thread_count if n == 41 else 1
            nodes = [
                {
                    "id": f"THREAD{n}-{i}",
                    "isResolved": True,
                    "isOutdated": True,
                    "comments": comments(i),
                }
                for i in range(start, min(count, start + 100))
            ]
            pr = {
                "mergeCommit": {"oid": self.git.alpha.commits["P"]}
                if v["number"] == 43
                else None,
                "potentialMergeCommit": None,
                "reviewThreads": {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": start + 100 < count,
                        "endCursor": str(start + 100) if start + 100 < count else None,
                    },
                },
            }
            payload = {"data": {"repository": {"pullRequest": pr}}}
            if self.graphql_partial:
                payload["errors"] = [
                    {
                        "message": "injected",
                        "path": ["repository", "pullRequest", "reviewThreads"],
                    }
                ]
            return payload, {}
        if path == "/user":
            return {
                "login": "fixture",
                **(
                    {"public_repos": 0, "owned_private_repos": 1}
                    if self.inventory_verified
                    else {}
                ),
            }, {}
        if path == "/repos/fixture/alpha":
            return {
                "id": 101,
                "full_name": "fixture/alpha",
                "clone_url": "https://github.com/fixture/alpha.git",
                "private": True,
                "archived": True,
                "fork": True,
            }, {}
        if path == "/user/repos":
            assert params.get("affiliation") == ["owner"] and params.get(
                "visibility"
            ) == ["all"]
            return [
                {
                    "id": 101,
                    "full_name": "fixture/alpha",
                    "clone_url": "https://github.com/fixture/alpha.git",
                    "private": True,
                    "archived": True,
                    "fork": True,
                }
            ], {}
        prefix = "/repos/fixture/alpha"
        assert path.startswith(prefix)
        suffix = path.removeprefix(prefix)
        if suffix == "/issues":
            assert params.get("state") == ["all"] and params.get("sort") == ["updated"]
            return [
                {
                    "id": 20000 + number,
                    "number": number,
                    "title": f"ordinary-issue-title {number}",
                    "body": f"ordinary-issue-body {self.stage}",
                    "state": state,
                    "user": {"login": "writer"},
                    "updated_at": "2026-01-01T00:00:00Z"
                    if self.stage == "A"
                    else "2026-02-01T00:00:00Z",
                }
                for number, state in ((1, "open"), (2, "closed"))
            ] + [
                {
                    **value,
                    "pull_request": {"url": self.url + prefix + f"/pulls/{number}"},
                }
                for number, value in self.prs.items()
            ], {}
        if suffix in ("/issues/1/comments", "/issues/2/comments"):
            number = int(suffix.split("/")[2])
            return [
                {
                    "id": 20100 + number,
                    "body": f"ordinary-issue-comment {self.stage} {number}",
                    "user": {"login": "commenter"},
                    "updated_at": "2026-01-01T00:00:00Z"
                    if self.stage == "A"
                    else "2026-02-01T00:00:00Z",
                }
            ], {}
        if suffix == "/pulls":
            assert params.get("state") == ["all"] and params.get("sort") == ["created"]
            if params.get("page") == ["2"]:
                return [self.prs[43]], {}
            return [self.prs[41], self.prs[42]], {
                "Link": f'<{self.url}{path}?state=all&sort=created&direction=asc&per_page=100&page=2>; rel="next"'
            }
        if suffix in ("/issues/comments", "/pulls/comments"):
            if not self.incremental:
                return [], {}
            if suffix == "/issues/comments":
                return [
                    {
                        "id": 241,
                        "node_id": "IC41",
                        "body": f"comment-marker {self.stage}",
                        "user": {"login": "commenter"},
                        "issue_url": self.url + "/repos/fixture/alpha/issues/41",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                ], {}
            value = self.comment(41, 542)
            value["pull_request_url"] = self.url + "/repos/fixture/alpha/pulls/41"
            return [value], {}
        parts = suffix.strip("/").split("/")
        n = int(parts[1])
        assert n in self.prs
        if len(parts) == 2:
            result = {**self.prs[n], "body": f"body-marker 認証 {self.stage}"}
            return result, {}
        collection = parts[2]
        if collection == "comments" and parts[0] == "issues":
            return [
                {
                    "id": 200 + n,
                    "node_id": f"IC{n}",
                    "body": f"comment-marker {self.stage}",
                    "user": {"login": "commenter"},
                    "html_url": f"https://github.com/fixture/alpha/issues/{n}#comment",
                }
            ], {}
        if collection == "reviews":
            return [
                {
                    "id": 300 + n,
                    "node_id": f"REV{n}",
                    "body": "review-marker",
                    "user": {"login": "reviewer"},
                    "state": "DISMISSED",
                    "commit_id": self.git.alpha.commits["P"],
                }
            ], {}
        if collection == "comments":
            return [self.comment(n, 501 + n)], {}
        if collection == "timeline":
            return [
                {"id": 400 + n, "event": "closed"},
                {"id": 500 + n, "event": "referenced"},
                {"id": 600 + n, "event": "referenced"},
            ], {}
        if collection == "commits":
            if self.cap_mode and n == 41:
                return [{"sha": f"{i:040x}"} for i in range(251)], {}
            return [{"sha": self.git.alpha.commits["P"]}], {}
        if collection == "files":
            if self.cap_mode and n == 41:
                return [
                    {"filename": f"file-{i}.txt", "status": "added"}
                    for i in range(3001)
                ], {}
            return [
                {
                    "filename": "pr-only.txt",
                    "status": "added",
                    "patch": "@@ -0,0 +1 @@\n+pr-marker",
                }
            ], {}
        raise KeyError(collection)
