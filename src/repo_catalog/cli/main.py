from __future__ import annotations

import argparse
import math
import signal
import sqlite3
import sys

from repo_catalog import __version__
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.cli.presenters import envelope, exit_code, render
from repo_catalog.config import state_path
from repo_catalog.domain.models import CancellationToken, CatalogError


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CatalogError("INVALID_ARGUMENT", message)


def parser():
    p = Parser(prog="repo-catalog")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--state-dir")
    p.add_argument("--format", choices=("table", "json"), default="table")
    p.add_argument("--timeout-seconds", type=float, default=30)
    commands = p.add_subparsers(dest="command", required=True, parser_class=Parser)
    init = commands.add_parser("init")
    init.add_argument("--profile", required=True)
    init.add_argument("--cache-max-bytes", required=True, type=int)
    init.add_argument("--min-free-bytes", required=True, type=int)
    commands.add_parser("doctor")
    sources = commands.add_parser("sources").add_subparsers(
        dest="action", required=True, parser_class=Parser
    )
    source = sources.add_parser("add")
    source.add_argument("kind", choices=("github", "local-git", "git-url"))
    source.add_argument("--owner")
    source.add_argument("--name")
    source.add_argument("--url")
    source.add_argument("--repo")
    source.add_argument("--instance")
    source.add_argument("--provider-repo-id")
    source.add_argument("--token-env-var")
    source.add_argument(
        "--clone-url-override", action="append", default=[], metavar="REPO_ID=URL"
    )
    source.add_argument("--include-repo", action="append", default=[], metavar="NAME")
    discover = commands.add_parser("discover")
    discover.add_argument("--source")
    sync = commands.add_parser("sync")
    sync.add_argument("kind", choices=("git", "pr", "all"))
    repo_selector(sync)
    sync.add_argument("--source")
    sync.add_argument("--endpoint", dest="endpoint_id")
    instances = commands.add_parser("instances").add_subparsers(
        dest="action", required=True, parser_class=Parser
    )
    new_instance = instances.add_parser("add")
    new_instance.add_argument(
        "kind",
        choices=("github", "gitlab", "gitea", "forgejo", "gitolite", "git", "other"),
    )
    new_instance.add_argument("--name", required=True)
    new_instance.add_argument("--web-base-url")
    new_instance.add_argument("--api-base-url")
    page_options(instances.add_parser("list"))
    instance_show = instances.add_parser("show")
    instance_show.add_argument("--instance", required=True)
    page_options(instance_show)
    endpoints = commands.add_parser("endpoints").add_subparsers(
        dest="action", required=True, parser_class=Parser
    )
    endpoint_add = endpoints.add_parser("add")
    endpoint_add.add_argument("--repo", required=True)
    endpoint_add.add_argument("--url", required=True)
    endpoint_add.add_argument("--label")
    endpoint_add.add_argument("--preferred", action="store_true")
    endpoint_prefer = endpoints.add_parser("prefer")
    endpoint_prefer.add_argument("--repo", required=True)
    endpoint_prefer.add_argument("--endpoint", required=True)
    endpoint_list = endpoints.add_parser("list")
    endpoint_list.add_argument("--repo", required=True)
    page_options(endpoint_list)
    for category, actions in {
        "repos": ("list", "show", "bind"),
        "snapshots": ("list", "show"),
        "refs": ("list",),
        "tree": ("list",),
        "commits": ("list", "show", "compare"),
        "jobs": ("list", "show", "resume", "cancel"),
        "pr": ("list", "show", "documents", "thread", "timeline"),
    }.items():
        group = commands.add_parser(category).add_subparsers(
            dest="action", required=True, parser_class=Parser
        )
        for action in actions:
            child = group.add_parser(action)
            page_options(child)
            if category == "repos" and action == "bind":
                child.add_argument("--repo", required=True)
                child.add_argument("--instance", required=True)
                child.add_argument("--provider-repo-id")
                continue
            if category == "repos":
                child.add_argument("--source")
            if category == "jobs":
                if action != "list":
                    child.add_argument("job_id")
            elif category == "snapshots" and action == "show":
                child.add_argument("--snapshot", required=True)
            elif category == "pr" and action == "thread":
                child.add_argument("--thread-id", required=True)
            else:
                child.add_argument(
                    "--repo",
                    required=category not in ("repos", "pr") or action != "list",
                )
                child.add_argument("--snapshot")
            if category in ("tree", "commits") and action in ("list", "show"):
                select = child.add_mutually_exclusive_group(required=True)
                select.add_argument("--ref")
                select.add_argument("--commit")
                child.add_argument("--first-parent", action="store_true")
                child.add_argument("--path-prefix")
            if category == "commits" and action == "compare":
                child.add_argument("--left", required=True)
                child.add_argument("--right", required=True)
                child.add_argument(
                    "--set",
                    required=True,
                    choices=("left-only", "right-only", "common", "symmetric"),
                )
            if category == "refs":
                child.add_argument(
                    "--ref-kind",
                    dest="ref_kinds",
                    action="append",
                    choices=("head", "tag", "pr-head", "pr-related"),
                )
            if category == "pr":
                if action not in ("list", "thread"):
                    child.add_argument("--number", required=True, type=int)
                child.add_argument("--document")
                child.add_argument("--version", type=int)
    search = commands.add_parser("search").add_subparsers(
        dest="action", required=True, parser_class=Parser
    )
    for kind in ("path", "code", "commits", "hash", "pr"):
        child = search.add_parser(kind)
        repo_selector(child)
        page_options(child)
        child.add_argument("--source")
        if kind != "pr":
            child.add_argument(
                "--scope",
                choices=("current", "history", "recorded"),
                default="recorded" if kind == "hash" else "current",
            )
            child.add_argument("--snapshot")
            select = child.add_mutually_exclusive_group()
            select.add_argument("--ref", dest="refs", action="append")
            select.add_argument(
                "--ref-kind",
                dest="ref_kinds",
                action="append",
                choices=("head", "tag", "pr-head", "pr-related"),
            )
            select.add_argument("--pr", type=int)
        if kind in ("code", "commits", "pr"):
            child.add_argument("--literal", required=True)
        if kind in ("path", "pr"):
            path = child.add_mutually_exclusive_group()
            path.add_argument("--path")
            path.add_argument("--path-b64")
            child.add_argument(
                "--path-mode", choices=("exact", "prefix", "contains"), default="exact"
            )
        if kind == "path":
            child.add_argument("--content-id", type=int)
        if kind == "hash":
            child.add_argument(
                "--algorithm",
                required=True,
                choices=("raw-md5", "raw-sha1", "raw-sha256"),
            )
            child.add_argument("--digest", required=True)
            child.add_argument("--byte-length", type=int)
        if kind == "pr":
            child.add_argument(
                "--document-versions", choices=("latest", "observed"), default="latest"
            )
            child.add_argument(
                "--state", choices=("all", "open", "closed", "merged"), default="all"
            )
            for name in ("draft", "resolved", "outdated"):
                child.add_argument(
                    "--" + name, choices=("any", "true", "false"), default="any"
                )
            for name in (
                "author",
                "document-author",
                "reviewer",
                "document-kind",
                "commit",
            ):
                child.add_argument("--" + name)
    content = commands.add_parser("content").add_subparsers(
        dest="action", required=True, parser_class=Parser
    )
    for action in ("show", "hydrate"):
        child = content.add_parser(action)
        child.add_argument("--content-id", type=int, required=True)
        if action == "show":
            child.add_argument("--offset", type=int, default=0)
            child.add_argument("--length", type=int, default=65536)
        else:
            child.add_argument("--repo")
    for cmd in ("coverage", "status"):
        child = commands.add_parser(cmd)
        child.add_argument("--repo")
        child.add_argument("--kind")
        page_options(child)
    cache = commands.add_parser("cache").add_subparsers(
        dest="action", required=True, parser_class=Parser
    )
    page_options(cache.add_parser("status"))
    cache.add_parser("gc").add_argument("--apply", action="store_true")
    db = commands.add_parser("db").add_subparsers(
        dest="action", required=True, parser_class=Parser
    )
    db.add_parser("migrate")
    db.add_parser("check").add_argument("--full", action="store_true")
    db.add_parser("backup").add_argument("--output", required=True)
    db.add_parser("restore").add_argument("--input", required=True)
    index = commands.add_parser("index").add_subparsers(
        dest="action", required=True, parser_class=Parser
    )
    index.add_parser("rebuild").add_argument(
        "--kind", choices=("code", "pr", "commits", "all"), default="all"
    )
    return p


def page_options(p):
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--cursor")


def repo_selector(p):
    p.add_argument("--repo", dest="repos", action="append")


def dispatch(args, token):
    path = state_path(args.state_dir)
    maintenance = MaintenanceService(path)
    if args.command == "init":
        return maintenance.init(args.profile, args.cache_max_bytes, args.min_free_bytes)
    if args.command == "doctor":
        return maintenance.doctor()
    if args.command == "sources":
        overrides = {}
        for value in args.clone_url_override:
            key, sep, url = value.partition("=")
            if not sep or not key or not url or args.kind != "github":
                raise CatalogError(
                    "INVALID_ARGUMENT",
                    "Clone override must be REPO_ID=URL on a github source",
                )
            overrides[key] = url
        return maintenance.source_add(
            args.kind,
            owner=args.owner,
            name=args.name,
            url=args.url,
            clone_url_overrides=overrides,
            include_repositories=args.include_repo,
            repo=args.repo,
            instance=args.instance,
            provider_repo_id=args.provider_repo_id,
            token_env_var=args.token_env_var,
        )
    if args.command == "instances" and args.action == "add":
        return maintenance.instance_add(
            args.kind, args.name, args.web_base_url, args.api_base_url
        )
    if args.command == "endpoints" and args.action == "add":
        return maintenance.endpoint_add(args.repo, args.url, args.label, args.preferred)
    if args.command == "endpoints" and args.action == "prefer":
        return maintenance.endpoint_prefer(args.repo, args.endpoint)
    if args.command == "repos" and args.action == "bind":
        return maintenance.repository_bind(
            args.repo, args.instance, args.provider_repo_id
        )
    from repo_catalog.application.collection_service import CollectionService
    from repo_catalog.application.contracts import CollectionRequest

    collection = CollectionService(path, token)
    if args.command == "discover":
        return collection.discover(args.source)
    if args.command == "sync":
        return collection.sync(
            CollectionRequest(
                args.kind,
                tuple(args.repos or ()),
                args.source,
                endpoint_id=args.endpoint_id,
            )
        )
    if args.command == "jobs" and args.action == "resume":
        return collection.resume(args.job_id)
    if args.command == "jobs" and args.action == "cancel":
        from repo_catalog.adapters.filesystem.locks import FileLock
        from repo_catalog.adapters.sqlite.store import Store
        from repo_catalog.application.job_service import JobService
        from repo_catalog.domain.models import Result

        # Read running state first so a live writer reports JOB_RUNNING, not a false successful cancellation.
        with Store(path, readonly=True) as s:
            row = s.one("SELECT state FROM jobs WHERE id=?", (args.job_id,))
            if row and row[0] == "running":
                raise CatalogError(
                    "JOB_RUNNING", "Send SIGINT to the foreground runner"
                )
        with FileLock(path / "locks/writer.lock"), Store(path) as s:
            JobService(s).cancel(args.job_id)
            return Result(
                {"job_id": args.job_id, "state": "cancelled"}, catalog=s.revision()
            )
    if args.command == "db":
        return maintenance.database(args.action, args)
    if args.command == "cache" and args.action == "gc":
        return maintenance.gc(args.apply)
    if args.command == "index":
        return maintenance.rebuild(args.kind, token)
    if args.command == "content" and args.action == "hydrate":
        return maintenance.hydrate(args.content_id, args.repo, token)
    from repo_catalog.application.contracts import PageRequest, QueryRequest
    from repo_catalog.application.query_service import QueryService

    command = " ".join(filter(None, [args.command, getattr(args, "action", None)]))
    opts = {
        k: v
        for k, v in vars(args).items()
        if k
        not in (
            "command",
            "action",
            "state_dir",
            "format",
            "limit",
            "cursor",
            "timeout_seconds",
        )
        and v is not None
    }
    return QueryService(path, token).execute(
        QueryRequest(
            command,
            opts,
            PageRequest(getattr(args, "limit", 100), getattr(args, "cursor", None)),
            args.timeout_seconds,
        )
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    fmt = (
        "json"
        if "--format" in argv
        and argv[argv.index("--format") + 1 : argv.index("--format") + 2] == ["json"]
        else "table"
    )
    token = CancellationToken()
    old = signal.signal(signal.SIGINT, lambda *_: setattr(token, "cancelled", True))
    result = error = None
    command = ""
    request = {}
    try:
        args = parser().parse_args(argv)
        fmt = args.format
        request = {
            k: v
            for k, v in vars(args).items()
            if k not in ("format", "state_dir", "command", "action") and v is not None
        }
        command = " ".join(filter(None, [args.command, getattr(args, "action", None)]))
        if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
            raise CatalogError(
                "INVALID_ARGUMENT", "Timeout must be finite and positive"
            )
        result = dispatch(args, token)
    except CatalogError as e:
        error = e
    except (sqlite3.Error, OSError) as e:
        error = CatalogError(
            "DATABASE_ERROR" if isinstance(e, sqlite3.Error) else "IO_ERROR",
            f"{type(e).__name__}: {e}",
        )
    except Exception as e:
        error = CatalogError("INTERNAL_ERROR", f"Unexpected {type(e).__name__}")
    finally:
        signal.signal(signal.SIGINT, old)
    print(render(envelope(command, request, result, error), fmt))
    return exit_code(result, error)
