from __future__ import annotations

import hashlib
import json
import time
import uuid
from importlib.resources import files
from urllib.parse import urlencode, urljoin

import httpx

from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.domain.models import CatalogError, Waiting, now


class GitHubCollector:
    def __init__(self, store, token, transport=None):
        self.s, self.token = store, token
        self.http = transport or GitHubTransport(store.config["github"], token)
        self.owned = transport is None
        self.inventory_uncertainty = None

    def request_get(self, url, repo=None, **kwargs):
        seen = set()
        while True:
            if url in seen:
                raise CatalogError("PAGINATION_CYCLE", "API redirect cycle")
            seen.add(url)
            response = self.http.request("GET", url, **kwargs)
            if response.status_code not in (301, 302):
                return response
            target = urljoin(url, response.headers.get("location", ""))
            self.http.validate_url(target)
            if not repo:
                raise CatalogError("SCOPE_MISMATCH", "Unverified inventory redirect")
            from urllib.parse import urlsplit

            parts = urlsplit(target).path.strip("/").split("/")
            source = json.loads(
                self.s.one(
                    "SELECT settings FROM sources WHERE id=?", (repo["source_id"],)
                )[0]
            )
            if (
                len(parts) < 3
                or parts[0] != "repos"
                or parts[1].lower() != source["owner"].lower()
            ):
                raise CatalogError(
                    "SCOPE_MISMATCH", "Transfer target is outside declared owner"
                )
            name = "/".join(parts[1:3])
            identity = self.http.request("GET", self.http.base + "/repos/" + name)
            payload = identity.json()
            if str(payload.get("id")) != repo["provider_repo_id"]:
                raise CatalogError(
                    "SCOPE_MISMATCH", "Redirect changed repository identity"
                )
            with self.s.transaction():
                self.s.execute(
                    "UPDATE repositories SET name=? WHERE id=?", (name, repo["id"])
                )
                self.s.execute(
                    "INSERT OR IGNORE INTO repository_names VALUES(?,?,?)",
                    (repo["id"], name, now()),
                )
                self.s.publish()
            url = target

    def get_resource(self, url, repo):
        # Only single-resource representations use conditional GET; collection sweeps never do.
        scope = {
            "repo": repo["provider_repo_id"],
            "source": repo["source_id"],
            "principal": getattr(self, "principal", None),
            "version": self.s.config["github"]["rest_api_version"],
            "accept": "application/vnd.github+json",
            "url": url,
        }
        key = "etag:" + json.dumps(scope, sort_keys=True)
        cached = self.s.one("SELECT value FROM sync_checkpoints WHERE scope=?", (key,))
        value = json.loads(cached[0]) if cached else {}
        headers = {"If-None-Match": value["etag"]} if value.get("etag") else {}
        response = self.request_get(url, repo, headers=headers)
        if response.status_code == 304:
            saved = self.s.one(
                "SELECT body FROM api_responses WHERE id=?", (value.get("response_id"),)
            )
            if saved:
                return httpx.Response(
                    200,
                    content=saved[0],
                    headers=response.headers,
                    request=response.request,
                )
            response = self.request_get(url, repo)
            if response.status_code == 304:
                raise CatalogError("API_SCHEMA", "304 without a saved representation")
        if response.headers.get("etag"):
            raw = response.content
            sha = hashlib.sha256(raw).digest()
            with self.s.transaction():
                self.s.execute(
                    "INSERT OR IGNORE INTO api_responses(payload_sha256,body) VALUES(?,?)",
                    (sha, raw),
                )
                rid = self.s.one(
                    "SELECT id FROM api_responses WHERE payload_sha256=? AND body=?",
                    (sha, raw),
                )[0]
                self.s.execute(
                    "INSERT INTO sync_checkpoints VALUES(?,?,?) ON CONFLICT(scope) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (
                        key,
                        json.dumps(
                            {"etag": response.headers["etag"], "response_id": rid}
                        ),
                        now(),
                    ),
                )
        return response

    def inventory(self, source, job):
        cfg = json.loads(source["settings"])
        owner = cfg["owner"]
        base = self.http.base
        try:
            identity = self.http.request("GET", base + "/user").json()
            if cfg.get("include_repositories"):
                import re

                selected = []
                for repository in cfg["include_repositories"]:
                    name = repository.removeprefix(owner + "/")
                    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                        raise CatalogError(
                            "INVALID_ARGUMENT",
                            "Included repository must be a name within declared owner",
                        )
                    payload = self.http.request(
                        "GET", base + "/repos/" + owner + "/" + name
                    ).json()
                    if (
                        payload.get("full_name", "").lower()
                        != f"{owner}/{name}".lower()
                    ):
                        raise CatalogError(
                            "SCOPE_MISMATCH", "Selected repository identity changed"
                        )
                    provider = str(payload["id"])
                    selected.append(
                        {
                            "host": "github.com",
                            "provider_id": provider,
                            "name": payload["full_name"],
                            "url": cfg.get("clone_url_overrides", {}).get(
                                provider, payload["clone_url"]
                            ),
                            "metadata": payload,
                        }
                    )
                return selected
            if identity.get("login", "").lower() == owner.lower():
                url = (
                    base
                    + "/user/repos?"
                    + urlencode(
                        {
                            "affiliation": "owner",
                            "visibility": "all",
                            "per_page": self.s.config["github"]["rest_page_size"],
                        }
                    )
                )
            else:
                user = self.http.request("GET", base + "/users/" + owner).json()
                if user.get("type") == "Organization":
                    url = (
                        base
                        + "/orgs/"
                        + owner
                        + "/repos?"
                        + urlencode(
                            {
                                "per_page": self.s.config["github"]["rest_page_size"],
                                "type": "all",
                            }
                        )
                    )
                else:
                    raise CatalogError(
                        "SCOPE_UNSUPPORTED",
                        "Owner is not the authenticated user; private owner inventory is not established",
                    )
            result = []
            seen = set()
            while url:
                if url in seen:
                    raise CatalogError("PAGINATION_CYCLE", "Repeated inventory page")
                seen.add(url)
                response = self.http.request("GET", url)
                values = response.json()
                if not isinstance(values, list):
                    raise CatalogError("API_SCHEMA", "Expected repository list")
                for r in values:
                    if not r.get("id") or not r.get("full_name"):
                        raise CatalogError("API_SCHEMA", "Repository identity missing")
                    if r["full_name"].split("/")[0].lower() != owner.lower():
                        raise CatalogError(
                            "SCOPE_MISMATCH",
                            "Inventory returned repository outside owner scope",
                        )
                    provider = str(r["id"])
                    clone = cfg.get("clone_url_overrides", {}).get(
                        provider, r.get("clone_url")
                    )
                    if not clone:
                        raise CatalogError("API_SCHEMA", "Clone URL missing")
                    result.append(
                        {
                            "host": "github.com",
                            "provider_id": provider,
                            "name": r["full_name"],
                            "url": clone,
                            "metadata": r,
                        }
                    )
                url = self.http.next_url(response)
            by_id = {repo["provider_id"]: repo for repo in result}
            result = list(by_id.values())
            counts = (identity.get("public_repos"), identity.get("owned_private_repos"))
            if (
                identity.get("login", "").lower() != owner.lower()
                or not all(type(value) is int and value >= 0 for value in counts)
                or any(
                    type(repo["metadata"].get("private")) is not bool for repo in result
                )
            ):
                self.inventory_uncertainty = "INVENTORY_SCOPE_UNVERIFIED"
            elif counts != (
                sum(not repo["metadata"]["private"] for repo in result),
                sum(repo["metadata"]["private"] for repo in result),
            ):
                self.inventory_uncertainty = "INVENTORY_COUNT_MISMATCH"
            return result
        finally:
            if self.owned:
                self.http.close()

    def collection(
        self,
        repo,
        pr,
        kind,
        job,
        url,
        normalizer,
        *,
        cap=None,
        reported=None,
        replay=False,
    ):
        s = self.s
        previous = s.one(
            "SELECT * FROM collections WHERE job_id=? AND repo_id=? AND pr_id IS ? AND kind=? ORDER BY observed_at DESC LIMIT 1",
            (job, repo["id"], pr, kind),
        )
        if previous and previous["state"] == "complete":
            if replay:
                for page in s.all(
                    "SELECT p.ordinal,a.body FROM collection_pages p JOIN api_responses a ON a.id=p.response_id WHERE p.collection_id=? ORDER BY p.ordinal",
                    (previous["id"],),
                ):
                    with s.transaction():
                        self.fence(job)
                        for pos, value in enumerate(json.loads(page["body"])):
                            normalizer(
                                value, previous["id"], page["ordinal"] * 10000 + pos
                            )
                        s.publish()
            return previous["id"]
        if previous:
            cid = previous["id"]
            url = previous["cursor"] or url
            ordinal = s.one(
                "SELECT coalesce(max(ordinal),-1)+1 FROM collection_pages WHERE collection_id=?",
                (cid,),
            )[0]
        else:
            cid = str(uuid.uuid4())
            ordinal = 0
            with s.transaction():
                s.execute(
                    "INSERT INTO collections VALUES(?,?,?,?,?,?,?,?,?,NULL)",
                    (
                        cid,
                        pr,
                        repo["id"],
                        kind,
                        job,
                        "running",
                        json.dumps(
                            {
                                "repo_id": repo["id"],
                                "api_version": s.config["github"]["rest_api_version"],
                            }
                        ),
                        url,
                        now(),
                    ),
                )
        seen = set()
        count = s.one(
            "SELECT count(*) FROM collection_memberships WHERE collection_id=?", (cid,)
        )[0]
        try:
            while url:
                self.token.check()
                if url in seen:
                    raise CatalogError("PAGINATION_CYCLE", "Repeated collection page")
                seen.add(url)
                response = self.request_get(url, repo)
                values = response.json()
                if not isinstance(values, list):
                    raise CatalogError(
                        "API_SCHEMA", "Collection response must be a list"
                    )
                next_url = self.http.next_url(response)
                from repo_catalog.adapters.git.runner import hook

                hook("before_api_page_commit")
                with s.transaction():
                    self.fence(job)
                    payload = response.content
                    sha = hashlib.sha256(payload).digest()
                    s.execute(
                        "INSERT OR IGNORE INTO api_responses(payload_sha256,body) VALUES(?,?)",
                        (sha, payload),
                    )
                    response_id = s.one(
                        "SELECT id FROM api_responses WHERE payload_sha256=? AND body=?",
                        (sha, payload),
                    )[0]
                    s.execute(
                        "INSERT OR REPLACE INTO collection_pages VALUES(?,?,?,?,?,?)",
                        (
                            cid,
                            ordinal,
                            response_id,
                            json.dumps(
                                {
                                    "url": url,
                                    "api_version": s.config["github"][
                                        "rest_api_version"
                                    ],
                                    "parser_version": "v1",
                                }
                            ),
                            next_url,
                            now(),
                        ),
                    )
                    for position, value in enumerate(values):
                        resource = normalizer(value, cid, ordinal * 10000 + position)
                        if resource is not None:
                            count += 1
                            s.execute(
                                "INSERT OR IGNORE INTO collection_memberships VALUES(?,?,?)",
                                (cid, str(resource), ordinal * 10000 + position),
                            )
                    s.execute(
                        "UPDATE collections SET cursor=?,state='running' WHERE id=?",
                        (next_url, cid),
                    )
                    s.publish()
                hook("after_api_page_commit")
                ordinal += 1
                url = next_url
            if cap and (count >= cap or reported is not None and count < reported):
                raise CatalogError(
                    "API_CAP",
                    "Provider list may be truncated",
                    {"cap": cap, "collected": count, "reported": reported},
                )
            with s.transaction():
                self.fence(job)
                s.execute(
                    "UPDATE collections SET state='complete',cursor=NULL WHERE id=?",
                    (cid,),
                )
                s.publish()
                s.coverage(pr or repo["id"], kind, "complete")
            return cid
        except CatalogError as e:
            with s.transaction():
                s.execute(
                    "UPDATE collections SET state='partial',reason=? WHERE id=?",
                    (e.code, cid),
                )
                s.coverage(
                    pr or repo["id"], kind, "partial", json.dumps({"reason": e.code})
                )
                s.publish()
            raise

    def fence(self, job):
        if getattr(self.s, "expected_attempt", None) is not None:
            row = self.s.one("SELECT attempt,state FROM jobs WHERE id=?", (job,))
            if (
                not row
                or row["attempt"] != self.s.expected_attempt
                or row["state"] != "running"
            ):
                raise CatalogError(
                    "STALE_ATTEMPT", "Refusing obsolete API page publication"
                )

    def ensure_pr(self, repo, value, job):
        s = self.s
        if "number" not in value or not value.get("id"):
            raise CatalogError("API_SCHEMA", "PR identity missing")
        existing = s.one(
            "SELECT id FROM pull_requests WHERE repo_id=? AND number=?",
            (repo["id"], value["number"]),
        )
        ident = existing[0] if existing else f"{repo['id']}:{value['number']}"
        s.execute(
            "INSERT OR IGNORE INTO pull_requests(id,repo_id,number,node_id) VALUES(?,?,?,?)",
            (ident, repo["id"], value["number"], value.get("node_id")),
        )
        obs = s.execute(
            "INSERT INTO pr_observations(pr_id,job_id,observed_at,payload) VALUES(?,?,?,?)",
            (ident, job, now(), json.dumps(value)),
        ).lastrowid
        s.execute(
            "UPDATE pull_requests SET current_observation=? WHERE id=?", (obs, ident)
        )
        self.document(
            ident, "pr-title", str(value["id"]), value.get("title"), value, job
        )
        self.document(
            ident, "pr-body", str(value["id"]), value.get("body") or "", value, job
        )
        return ident

    def document(self, pr, kind, provider, body, value, collection, thread=None):
        s = self.s
        if not isinstance(body, str):
            raise CatalogError("API_SCHEMA", "Expected raw document text")
        node = (
            value.get("node_id") or value.get("id")
            if isinstance(value.get("id"), str)
            else value.get("node_id")
        )
        existing = s.one(
            "SELECT id FROM pr_documents WHERE pr_id=? AND kind=? AND provider_id=?",
            (pr, kind, str(provider)),
        )
        if not existing and node:
            existing = s.one(
                "SELECT id FROM pr_documents WHERE pr_id=? AND kind=? AND node_id=?",
                (pr, kind, node),
            )
        ident = existing[0] if existing else f"{pr}:{kind}:{provider}"
        user = value.get("user") or value.get("author") or {}
        metadata = {
            k: v
            for k, v in value.items()
            if k not in ("body", "title", "user", "author")
        }
        if thread:
            metadata["thread_id"] = thread
        s.execute(
            "INSERT INTO pr_documents(id,pr_id,kind,provider_id,node_id,author,url,metadata) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET node_id=coalesce(excluded.node_id,node_id),author=excluded.author,url=excluded.url,metadata=excluded.metadata",
            (
                ident,
                pr,
                kind,
                str(provider),
                node,
                user.get("login"),
                value.get("html_url") or value.get("url"),
                json.dumps(metadata),
            ),
        )
        sha = hashlib.sha256(body.encode()).digest()
        s.execute(
            "INSERT OR IGNORE INTO document_versions(document_id,body,body_sha256) VALUES(?,?,?)",
            (ident, body, sha),
        )
        version = s.one(
            "SELECT id FROM document_versions WHERE document_id=? AND body_sha256=? AND body=?",
            (ident, sha, body),
        )[0]
        s.execute(
            "UPDATE pr_documents SET current_version=?,deleted=0 WHERE id=?",
            (version, ident),
        )
        s.execute(
            "INSERT OR IGNORE INTO resource_observations(document_id,version_id,collection_run,observed_at,metadata) VALUES(?,?,?,?,?)",
            (ident, version, collection, now(), json.dumps(metadata)),
        )
        s.execute(
            "INSERT OR IGNORE INTO search_documents(kind,source_key,body,metadata) VALUES('pr',?,?,?)",
            (
                str(version),
                body,
                json.dumps({"document_id": ident, "version_id": version}),
            ),
        )
        if kind == "review":
            s.execute(
                "INSERT OR REPLACE INTO pr_reviews VALUES(?,?,?,?)",
                (ident, pr, ident, json.dumps(value)),
            )
        if kind == "review-comment":
            s.execute(
                "INSERT INTO review_comments VALUES(?,?,?) ON CONFLICT(document_id) DO UPDATE SET thread_id=coalesce(excluded.thread_id,thread_id),payload=excluded.payload",
                (ident, thread, json.dumps(value)),
            )
        return ident

    def sync(self, repo, job):
        s = self.s
        base = self.http.base
        name = repo["name"]
        root = f"{base}/repos/{name}"
        failures = []
        waiting = None
        with s.transaction():
            for component in ("pr", "pr-documents"):
                s.coverage(
                    repo["id"],
                    component,
                    "partial",
                    json.dumps({"reason": "collection_in_progress", "job_id": job}),
                )
            s.publish()

        def attempt(kind, operation):
            nonlocal waiting
            if waiting and waiting > self.http.clock() and kind != "pr-git":
                failures.append({"kind": kind, "reason": "RATE_LIMIT_WAIT"})
                return None
            try:
                return operation()
            except CatalogError as e:
                if e.code == "CANCELLED":
                    raise
                failures.append({"kind": kind, "reason": e.code})
                waiting = e.details.get("not_before", waiting)
                with s.transaction():
                    s.coverage(
                        repo["id"], kind, "partial", json.dumps({"reason": e.code})
                    )
                    s.publish()

        try:
            identity = self.http.request("GET", self.http.base + "/user").json()
            self.principal = str(identity.get("id") or identity.get("login"))
            size = s.config["github"]["rest_page_size"]
            attempt(
                "pr-list",
                lambda: self.collection(
                    repo,
                    None,
                    "pr-list",
                    job,
                    root
                    + f"/pulls?state=all&sort=created&direction=asc&per_page={size}",
                    lambda value, cid, pos: self.ensure_pr(repo, value, job),
                ),
            )
            for kind, endpoint, parent_field in [
                ("issue-comment", root + "/issues/comments", "issue_url"),
                ("review-comment", root + "/pulls/comments", "pull_request_url"),
            ]:
                attempt(
                    kind + "-incremental",
                    lambda kind=kind, endpoint=endpoint, parent_field=parent_field: (
                        self.incremental_comments(
                            repo, job, kind, endpoint, parent_field
                        )
                    ),
                )
            prs = s.all(
                "SELECT p.*,o.payload FROM pull_requests p JOIN pr_observations o ON o.id=p.current_observation WHERE p.repo_id=? ORDER BY p.number",
                (repo["id"],),
            )
            for pr in prs:
                self.token.check()
                completion_key = f"pr-complete:{job}:{pr['id']}"
                if s.one(
                    "SELECT 1 FROM sync_checkpoints WHERE scope=?", (completion_key,)
                ) or self.completed_pr(job, pr["id"]):
                    continue
                failures_before_pr = len(failures)
                number = pr["number"]
                url = root + f"/pulls/{number}"
                before = json.loads(pr["payload"])
                response = attempt("pr-detail", lambda: self.get_resource(url, repo))
                if response:
                    before = response.json()
                    with s.transaction():
                        self.ensure_pr(repo, before, job)
                        s.publish()
                endpoints = [
                    ("issue-comment", root + f"/issues/{number}/comments"),
                    ("review", url + "/reviews"),
                    ("review-comment", url + "/comments"),
                ]
                for kind, endpoint in endpoints:

                    def normalizer(value, cid, pos, kind=kind):
                        provider = value.get("id")
                        if provider is None:
                            raise CatalogError("API_SCHEMA", "Document ID missing")
                        return self.document(
                            pr["id"],
                            kind,
                            str(provider),
                            value.get("body") or "",
                            value,
                            cid,
                        )

                    attempt(
                        kind,
                        lambda kind=kind, endpoint=endpoint: self.collection(
                            repo,
                            pr["id"],
                            kind,
                            job,
                            endpoint + f"?per_page={size}",
                            normalizer,
                        ),
                    )

                def event(value, cid, pos):
                    s.execute(
                        "INSERT OR IGNORE INTO pr_events(pr_id,run_id,ordinal,provider_id,payload) VALUES(?,?,?,?,?)",
                        (
                            pr["id"],
                            cid,
                            pos,
                            str(value["id"]) if value.get("id") is not None else None,
                            json.dumps(value),
                        ),
                    )
                    return f"{cid}:{pos}"

                attempt(
                    "timeline",
                    lambda: self.collection(
                        repo,
                        pr["id"],
                        "timeline",
                        job,
                        root + f"/issues/{number}/timeline?per_page={size}",
                        event,
                    ),
                )
                merge = attempt("threads", lambda: self.threads(repo, pr, job)) or {}
                current = s.one(
                    "SELECT current_observation FROM pull_requests WHERE id=?",
                    (pr["id"],),
                )[0]
                with s.transaction():
                    code = s.execute(
                        "INSERT INTO pr_code_observations(pr_id,observation_id,head_oid,base_oid,state,details) VALUES(?,?,?,?,?,?)",
                        (
                            pr["id"],
                            current,
                            (before.get("head") or {}).get("sha"),
                            (before.get("base") or {}).get("sha"),
                            "pending",
                            "{}",
                        ),
                    ).lastrowid

                def commit(value, cid, pos):
                    if not value.get("sha"):
                        raise CatalogError("API_SCHEMA", "PR commit OID missing")
                    s.execute(
                        "INSERT OR REPLACE INTO pr_commits VALUES(?,?,?,?)",
                        (code, pos, value["sha"], json.dumps(value)),
                    )
                    return value["sha"]

                def file(value, cid, pos):
                    if "filename" not in value:
                        raise CatalogError("API_SCHEMA", "PR file path missing")
                    s.execute(
                        "INSERT OR REPLACE INTO pr_file_changes VALUES(?,?,?,?)",
                        (code, pos, value["filename"], json.dumps(value)),
                    )
                    return value["filename"]

                oldfail = len(failures)
                attempt(
                    "pr-commits",
                    lambda: self.collection(
                        repo,
                        pr["id"],
                        "pr-commits",
                        job,
                        url + f"/commits?per_page={size}",
                        commit,
                        cap=250,
                        reported=before.get("commits"),
                        replay=True,
                    ),
                )
                attempt(
                    "pr-files",
                    lambda: self.collection(
                        repo,
                        pr["id"],
                        "pr-files",
                        job,
                        url + f"/files?per_page={size}",
                        file,
                        cap=3000,
                        reported=before.get("changed_files"),
                        replay=True,
                    ),
                )
                after_response = attempt(
                    "pr-code", lambda: self.get_resource(url, repo)
                )
                after = after_response.json() if after_response else {}
                same = all(
                    (before.get(role) or {}).get("sha")
                    == (after.get(role) or {}).get("sha")
                    for role in ("head", "base")
                )
                state = "complete" if same and len(failures) == oldfail else "partial"
                with s.transaction():
                    s.execute(
                        "UPDATE pr_code_observations SET state=?,details=? WHERE id=?",
                        (
                            state,
                            json.dumps(
                                {
                                    "api_head_base_stable": same,
                                    "merge": merge,
                                    "provider_limits": {"commits": 250, "files": 3000},
                                }
                            ),
                            code,
                        ),
                    )
                    s.publish()
                if not same:
                    failures.append({"kind": "pr-code", "reason": "PR_CODE_RACE"})
                head = (before.get("head") or {}).get("sha")
                base_oid = (before.get("base") or {}).get("sha")
                role_oids = {"head": head, "base": base_oid, **merge}
                for review in s.all(
                    "SELECT payload FROM pr_reviews WHERE pr_id=?", (pr["id"],)
                ):
                    review_oid = json.loads(review["payload"]).get("commit_id")
                    if review_oid:
                        role_oids["review-target:" + review_oid] = review_oid
                for role, expected in role_oids.items():
                    if not expected:
                        continue
                    from repo_catalog.adapters.git.importer import GitImporter
                    from repo_catalog.domain.models import GitOid

                    algorithm = "sha256" if len(expected) == 64 else "sha1"
                    GitOid.parse(algorithm + ":" + expected)
                    roots = [
                        {
                            "ref": f"refs/pull/{number}/head"
                            if role == "head"
                            else expected,
                            "expected": expected,
                            "role": role,
                            "number": number,
                        }
                    ]
                    fetched = attempt(
                        "pr-git",
                        lambda: GitImporter(s, self.token).sync(
                            repo, job, pr_roots=roots, observation_id=current
                        ),
                    )
                    if fetched:
                        with s.transaction():
                            for rootrow in s.all(
                                "SELECT * FROM acquisition_roots WHERE run_id=?",
                                (fetched["run_id"],),
                            ):
                                s.execute(
                                    "INSERT OR IGNORE INTO pr_git_links VALUES(?,?,?,?,?)",
                                    (
                                        code,
                                        rootrow["role"],
                                        rootrow["object_format"],
                                        rootrow["oid"],
                                        rootrow["id"],
                                    ),
                                )
                            s.publish()
                if len(failures) == failures_before_pr:
                    with s.transaction():
                        self.fence(job)
                        s.execute(
                            "INSERT OR REPLACE INTO sync_checkpoints VALUES(?,?,?)",
                            (completion_key, json.dumps({"complete": True}), now()),
                        )
            document_failures = [
                failure
                for failure in failures
                if failure["kind"]
                not in {"pr-git", "pr-code", "pr-commits", "pr-files", "timeline"}
            ]
            with s.transaction():
                s.coverage(
                    repo["id"],
                    "pr-documents",
                    "partial" if document_failures else "complete",
                    json.dumps({"missing": document_failures}),
                )
                s.publish()
            if failures:
                with s.transaction():
                    s.coverage(
                        repo["id"], "pr", "partial", json.dumps({"missing": failures})
                    )
                    s.publish()
                raise Waiting(
                    "PR_PARTIAL",
                    "Some PR collections are incomplete",
                    {
                        "missing": failures,
                        **({"not_before": waiting} if waiting else {}),
                    },
                    True,
                )
            with s.transaction():
                s.coverage(repo["id"], "pr", "complete")
                s.publish()
            return {
                "repo_id": repo["id"],
                "state": "complete",
                "pull_requests": len(prs),
            }
        finally:
            if self.owned:
                self.http.close()

    def completed_pr(self, job, pr_id):
        """Recover completion from durable pages/links of older job attempts."""
        code = self.s.one(
            "SELECT c.* FROM pr_code_observations c JOIN pr_observations o ON o.id=c.observation_id WHERE o.job_id=? AND c.pr_id=? ORDER BY c.id DESC LIMIT 1",
            (job, pr_id),
        )
        if not code or code["state"] != "complete":
            return False
        kinds = {
            r[0]
            for r in self.s.all(
                "SELECT kind FROM collections WHERE job_id=? AND pr_id=? AND state='complete'",
                (job, pr_id),
            )
        }
        if (
            not {
                "issue-comment",
                "review",
                "review-comment",
                "timeline",
                "pr-commits",
                "pr-files",
                "threads",
            }
            <= kinds
        ):
            return False
        expected = {
            "head": code["head_oid"],
            "base": code["base_oid"],
            **json.loads(code["details"]).get("merge", {}),
        }
        for review in self.s.all(
            "SELECT payload FROM pr_reviews WHERE pr_id=?", (pr_id,)
        ):
            oid = json.loads(review[0]).get("commit_id")
            if oid:
                expected["review-target:" + oid] = oid
        links = {
            (r[0], r[1].hex())
            for r in self.s.all(
                "SELECT l.role,l.oid FROM pr_git_links l JOIN acquisition_roots a ON a.id=l.acquisition_id WHERE l.code_observation=? AND a.published=1",
                (code["id"],),
            )
        }
        return bool(code["head_oid"] and code["base_oid"]) and all(
            (role, oid) in links for role, oid in expected.items() if oid
        )

    def incremental_comments(self, repo, job, kind, endpoint, parent_field):
        s = self.s
        scope = f"watermark:{repo['id']}:{self.principal}:{kind}:{s.config['github']['rest_api_version']}"
        previous = s.one("SELECT value FROM sync_checkpoints WHERE scope=?", (scope,))
        started = now()
        parameters = {
            "per_page": s.config["github"]["rest_page_size"],
            "sort": "updated",
            "direction": "asc",
        }
        if previous:
            from datetime import datetime, timedelta

            parameters["since"] = (
                datetime.fromisoformat(json.loads(previous[0])["watermark"])
                - timedelta(minutes=5)
            ).isoformat()

        def normalize(value, cid, pos):
            from urllib.parse import urlsplit

            parent = value.get(parent_field)
            if not parent or value.get("id") is None:
                raise CatalogError("API_SCHEMA", "Comment parent/identity missing")
            self.http.validate_url(parent)
            try:
                number = int(urlsplit(parent).path.rsplit("/", 1)[-1])
            except ValueError:
                raise CatalogError("API_SCHEMA", "Comment parent number invalid")
            pr = s.one(
                "SELECT id FROM pull_requests WHERE repo_id=? AND number=?",
                (repo["id"], number),
            )
            if not pr:
                # Preserve the exact pending resource without importing unrelated Issue bodies.
                pending = f"pending-comment:{repo['id']}:{kind}:{value['id']}"
                s.execute(
                    "INSERT INTO sync_checkpoints VALUES(?,?,?) ON CONFLICT(scope) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (
                        pending,
                        json.dumps(
                            {
                                "repo_id": repo["id"],
                                "number": number,
                                "kind": kind,
                                "payload": value,
                                "collection": cid,
                            }
                        ),
                        now(),
                    ),
                )
                return str(value["id"])
            return self.document(
                pr["id"], kind, str(value["id"]), value.get("body") or "", value, cid
            )

        self.collection(
            repo,
            None,
            kind + "-incremental",
            job,
            endpoint + "?" + urlencode(parameters),
            normalize,
        )
        # Advance only a successful, bounded scan's start time, never max(updated_at).
        with s.transaction():
            self.fence(job)
            s.execute(
                "INSERT INTO sync_checkpoints VALUES(?,?,?) ON CONFLICT(scope) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (scope, json.dumps({"watermark": started}), now()),
            )
            for row in s.all(
                "SELECT scope,value FROM sync_checkpoints WHERE scope LIKE ?",
                (f"pending-comment:{repo['id']}:%",),
            ):
                pending = json.loads(row["value"])
                pr = s.one(
                    "SELECT id FROM pull_requests WHERE repo_id=? AND number=?",
                    (repo["id"], pending["number"]),
                )
                if pr:
                    value = pending["payload"]
                    self.document(
                        pr["id"],
                        pending["kind"],
                        str(value["id"]),
                        value.get("body") or "",
                        value,
                        pending["collection"],
                    )
                    s.execute(
                        "DELETE FROM sync_checkpoints WHERE scope=?", (row["scope"],)
                    )
                    s.publish()

    def threads(self, repo, pr, job):
        s = self.s
        owner, name = repo["name"].split("/", 1)
        query = (
            files("repo_catalog").joinpath("resources/pr_threads.graphql").read_text()
        )
        checkpoint = f"graphql-root:{job}:{pr['id']}"
        cached = s.one(
            "SELECT value FROM sync_checkpoints WHERE scope=?", (checkpoint,)
        )
        saved = json.loads(cached[0]) if cached else {}
        if saved.get("complete"):
            return saved.get("merge", {})
        cursor = saved.get("cursor")
        seen = set()
        merge = {}
        while True:
            variables = {
                "owner": owner,
                "name": name,
                "number": pr["number"],
                "cursor": cursor,
                "pageSize": s.config["github"]["graphql_page_size"],
            }
            response = self.http.request(
                "POST", self.http.graphql, json={"query": query, "variables": variables}
            )
            payload = response.json()
            data = payload.get("data") or {}
            p = (data.get("repository") or {}).get("pullRequest") or {}
            errors = payload.get("errors") or []
            if any(e.get("type") == "RATE_LIMITED" for e in errors):
                raise Waiting(
                    "RATE_LIMIT",
                    "GraphQL rate limited",
                    {"not_before": time.time() + 60},
                    True,
                )
            connection = p.get("reviewThreads") or {}
            nodes = connection.get("nodes") or []
            merge = {
                role: (p.get(field) or {}).get("oid")
                for role, field in [
                    ("merge-result", "mergeCommit"),
                    ("test-merge", "potentialMergeCommit"),
                ]
            }
            with s.transaction():
                self.fence(job)
                self.graphql_response(repo, pr, job, response, variables)
                for thread in nodes:
                    if not thread.get("id"):
                        raise CatalogError("API_SCHEMA", "Thread ID missing")
                    s.execute(
                        "INSERT INTO review_threads VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,observed_at=excluded.observed_at",
                        (
                            thread["id"],
                            pr["id"],
                            json.dumps(
                                {k: v for k, v in thread.items() if k != "comments"}
                            ),
                            now(),
                        ),
                    )
                    self.thread_comments(
                        pr,
                        thread["id"],
                        thread.get("comments") or {},
                        f"{job}:threads:{cursor}",
                    )
                s.publish()
            for thread in nodes:
                comments = thread.get("comments") or {}
                info = comments.get("pageInfo") or {}
                child_seen = set()
                child_key = f"graphql-child:{job}:{pr['id']}:{thread['id']}"
                child_checkpoint = s.one(
                    "SELECT value FROM sync_checkpoints WHERE scope=?", (child_key,)
                )
                if child_checkpoint:
                    child_saved = json.loads(child_checkpoint[0])
                    info = {
                        "hasNextPage": not child_saved["complete"],
                        "endCursor": child_saved.get("cursor"),
                    }
                while info.get("hasNextPage"):
                    child = info.get("endCursor")
                    if not child or child in child_seen:
                        raise CatalogError(
                            "PAGINATION_CYCLE", "Thread comments cursor cycle"
                        )
                    child_seen.add(child)
                    v = {
                        "thread": thread["id"],
                        "commentCursor": child,
                        "pageSize": s.config["github"]["graphql_page_size"],
                    }
                    child_query = (
                        files("repo_catalog")
                        .joinpath("resources/thread_comments.graphql")
                        .read_text()
                    )
                    child_response = self.http.request(
                        "POST",
                        self.http.graphql,
                        json={"query": child_query, "variables": v},
                    )
                    child_payload = child_response.json()
                    if child_payload.get("errors"):
                        raise CatalogError(
                            "GRAPHQL_PARTIAL", "Thread comment page has errors"
                        )
                    comments = (child_payload.get("data", {}).get("node") or {}).get(
                        "comments"
                    ) or {}
                    if "pageInfo" not in comments:
                        raise CatalogError("API_SCHEMA", "Missing nested pageInfo")
                    with s.transaction():
                        self.fence(job)
                        self.graphql_response(repo, pr, job, child_response, v)
                        self.thread_comments(
                            pr,
                            thread["id"],
                            comments,
                            f"{job}:thread:{thread['id']}:{child}",
                        )
                        next_info = comments["pageInfo"]
                        s.execute(
                            "INSERT INTO sync_checkpoints VALUES(?,?,?) ON CONFLICT(scope) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                            (
                                child_key,
                                json.dumps(
                                    {
                                        "cursor": next_info.get("endCursor"),
                                        "complete": not next_info.get("hasNextPage"),
                                    }
                                ),
                                now(),
                            ),
                        )
                        s.publish()
                    info = comments["pageInfo"]
            if errors:
                raise CatalogError(
                    "GRAPHQL_PARTIAL",
                    "GraphQL partial response; collection cursor not advanced",
                )
            if "pageInfo" not in connection:
                raise CatalogError("API_SCHEMA", "Missing thread pageInfo")
            info = connection["pageInfo"]
            with s.transaction():
                self.fence(job)
                s.execute(
                    "INSERT INTO sync_checkpoints VALUES(?,?,?) ON CONFLICT(scope) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (
                        checkpoint,
                        json.dumps(
                            {
                                "cursor": info.get("endCursor"),
                                "complete": not info.get("hasNextPage"),
                                "merge": merge,
                            }
                        ),
                        now(),
                    ),
                )
                s.publish()
            if not info.get("hasNextPage"):
                break
            cursor = info.get("endCursor")
            if not cursor or cursor in seen:
                raise CatalogError("PAGINATION_CYCLE", "Thread cursor cycle")
            seen.add(cursor)
        with s.transaction():
            s.coverage(pr["id"], "threads", "complete")
            s.execute(
                "UPDATE collections SET state='complete' WHERE id=?",
                (f"graphql:{job}:{pr['id']}",),
            )
            s.publish()
        return merge

    def graphql_response(self, repo, pr, job, response, variables):
        s = self.s
        cid = f"graphql:{job}:{pr['id']}"
        s.execute(
            "INSERT OR IGNORE INTO collections VALUES(?,?,?,?,?,?,?,?,?,NULL)",
            (
                cid,
                pr["id"],
                repo["id"],
                "threads",
                job,
                "running",
                json.dumps(
                    {
                        "principal": self.principal,
                        "api_version": s.config["github"]["rest_api_version"],
                    }
                ),
                None,
                now(),
            ),
        )
        sha = hashlib.sha256(response.content).digest()
        s.execute(
            "INSERT OR IGNORE INTO api_responses(payload_sha256,body) VALUES(?,?)",
            (sha, response.content),
        )
        rid = s.one(
            "SELECT id FROM api_responses WHERE payload_sha256=? AND body=?",
            (sha, response.content),
        )[0]
        request = json.dumps(
            {"url": self.http.graphql, "variables": variables, "parser_version": "v1"},
            sort_keys=True,
        )
        existing = s.one(
            "SELECT ordinal FROM collection_pages WHERE collection_id=? AND request=?",
            (cid, request),
        )
        ordinal = (
            existing[0]
            if existing
            else s.one(
                "SELECT coalesce(max(ordinal),-1)+1 FROM collection_pages WHERE collection_id=?",
                (cid,),
            )[0]
        )
        s.execute(
            "INSERT OR REPLACE INTO collection_pages VALUES(?,?,?,?,?,?)",
            (cid, ordinal, rid, request, None, now()),
        )

    def thread_comments(self, pr, thread, connection, collection):
        for value in connection.get("nodes") or []:
            provider = value.get("fullDatabaseId") or value.get("id")
            if provider is None:
                raise CatalogError("API_SCHEMA", "GraphQL comment identity missing")
            self.document(
                pr["id"],
                "review-comment",
                str(provider),
                value.get("body") or "",
                value,
                collection,
                thread,
            )
