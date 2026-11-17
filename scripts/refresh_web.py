"""Inspect main, regenerate changed schema inputs, and retain a review report."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_product as prepare

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path("website/.build/verification/refresh")
SCHEMA = "website/schema/"
MODELS = {
    "website/content/design/model.json",
    "website/content/design/semantic-model.json",
}


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True).encode())


def file_record(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Linked file refused: " + str(path))
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError("Nonregular or aliased file refused: " + str(path))
    raw = path.read_bytes()
    if raw.startswith(b"SQLite format 3\0"):
        raise ValueError("Catalog collision refused: " + str(path))
    return {"sha256": digest(raw), "mode": stat.S_IMODE(metadata.st_mode)}


def tree_entries(snapshot):
    entries = {}
    for item in git(Path(snapshot["path"]), "ls-tree", "-rz", snapshot["commit"]).split(
        b"\0"
    ):
        if item:
            metadata, name = item.split(b"\t", 1)
            entries[name.decode()] = metadata.decode().split()
    return entries


def product_fingerprints(snapshot):
    root, commit = Path(snapshot["path"]), snapshot["commit"]
    entries = tree_entries(snapshot)
    parsed = ast.parse(git(root, "show", commit + ":scripts/schema_inventory.py"))
    declaration = next(
        n.value
        for n in parsed.body
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "PRODUCER_CONTROLS" for t in n.targets
        )
    )
    controls = set(ast.literal_eval(declaration.args[0]))
    program = {
        p: entry
        for p, entry in entries.items()
        if p.startswith(("src/", "packages/", "scripts/")) or p in controls
    }
    policy_path = "docs/web-source-policy.json"
    policy = json.loads(git(root, "show", commit + ":" + policy_path))
    canonical = {
        policy_path,
        policy["canonical_index"],
        *policy["public_adrs"],
        *policy["support"],
    }
    return {
        "program": fingerprint(program),
        "canonical": fingerprint({p: entries[p] for p in sorted(canonical)}),
    }


def renderer_fingerprint():
    paths = {
        *ROOT.glob("scripts/*.py"),
        *[
            p
            for p in (ROOT / "website/tools").rglob("*")
            if p.suffix in {".py", ".html", ".js", ".mjs"}
        ],
        ROOT / "website/pyproject.toml",
        ROOT / "website/uv.lock",
        ROOT / "product-source.json",
    }
    return fingerprint(
        {p.relative_to(ROOT).as_posix(): file_record(p) for p in sorted(paths)}
    )


def schema_files():
    base = ROOT / "website/schema"
    if base.is_symlink():
        raise ValueError("Linked schema directory refused")
    result = {}
    for p in sorted(base.rglob("*")):
        if p.is_symlink():
            raise ValueError("Linked schema member refused")
        if not p.is_dir():
            result[p.relative_to(ROOT).as_posix()] = file_record(p)
    return result


def preflight_schema(previous):
    current = schema_files()
    for entry in git(ROOT, "ls-files", "-v", "-z", "--", "website/schema").split(b"\0"):
        if entry and not entry.startswith(b"H "):
            raise ValueError(
                "Hidden index flag on schema source: " + entry[2:].decode()
            )
    cached = set(
        filter(
            None,
            git(
                ROOT,
                "diff",
                "--cached",
                "--name-only",
                "-z",
                "HEAD",
                "--",
                "website/schema",
            )
            .decode()
            .split("\0"),
        )
    )
    working = set(
        filter(
            None,
            git(ROOT, "diff", "--name-only", "-z", "--", "website/schema")
            .decode()
            .split("\0"),
        )
    )
    others = set(
        filter(
            None,
            git(
                ROOT,
                "ls-files",
                "--others",
                "-z",
                "--",
                "website/schema",
            )
            .decode()
            .split("\0"),
        )
    )
    known = (previous or {}).get("generated", {})
    for name in sorted(cached | working | others):
        if name not in current or current[name] != known.get(name):
            raise ValueError(
                "Uncommitted schema edit preserved; commit or stash it first: " + name
            )
        if (
            name in cached
            and digest(git(ROOT, "show", ":" + name)) != current[name]["sha256"]
        ):
            raise ValueError("Staged schema edit preserved: " + name)
        if (
            name in cached
            and git(ROOT, "ls-files", "--stage", "--", name).split()[0] != b"100644"
        ):
            raise ValueError("Staged schema mode change preserved: " + name)
    return current


def prepared_records(private):
    base = ROOT / "website/.build/inputs"
    names = ("inventory.json", "producer.json", "source-manifest.json")
    records = {
        name: file_record(private.private_path(ROOT, base / name)) for name in names
    }
    location = private.private_path(ROOT, base / "product-location.json")
    return records, json.loads(location.read_bytes())


def valid_prepared(previous, integrity, private):
    if not previous:
        return False
    try:
        records, snapshot = prepared_records(private)
        if records != previous.get("prepared_files"):
            return False
        expected = previous["prepared_source"]
        if any(
            snapshot.get(k) != expected.get(k)
            for k in ("path", "commit", "tree", "repository", "requested_ref")
        ):
            return False
        root = Path(snapshot["path"])
        try:
            integrity.verify_checkout(root, snapshot["commit"])
        except ValueError:
            return False
        if git(root, "rev-parse", "HEAD^{tree}").decode().strip() != snapshot["tree"]:
            return False
        base = ROOT / "website/.build/inputs"
        producer = json.loads((base / "producer.json").read_bytes())
        canonical = json.loads((base / "source-manifest.json").read_bytes())
        identity = {k: snapshot[k] for k in ("commit", "tree")}
        ir_hash = records["inventory.json"]["sha256"]
        for manifest in (producer, canonical):
            if (
                manifest.get("product_source") != identity
                or manifest.get("ir_sha256") != ir_hash
            ):
                return False
        for name, expected in producer.get("input_sha256", {}).items():
            if Path(name).is_absolute() or ".." in Path(name).parts or "\\" in name:
                return False
            if file_record(root / name)["sha256"] != expected:
                return False
        for name, expected in canonical.get("canonical_sources", {}).items():
            if not name.startswith("docs/") or ".." in Path(name).parts:
                return False
            if (
                file_record(root / name)["sha256"] != expected
                or digest(git(root, "show", snapshot["commit"] + ":" + name))
                != expected
            ):
                return False
        return bool(producer.get("input_sha256") and canonical.get("canonical_sources"))
    except (FileNotFoundError, KeyError, subprocess.CalledProcessError):
        return False


def changed_sources(previous, snapshot):
    if not previous:
        return None
    try:
        return sorted(
            filter(
                None,
                git(
                    Path(snapshot["path"]),
                    "diff",
                    "--no-renames",
                    "--name-only",
                    "-z",
                    previous["inspected_source"]["commit"],
                    snapshot["commit"],
                )
                .decode()
                .split("\0"),
            )
        )
    except subprocess.CalledProcessError:
        return None  # A missing historical/local baseline is unassessed, not current.


def review_items(previous, changed, acknowledge=()):
    pending = {x["path"]: x for x in (previous or {}).get("pending_review", [])}
    for name in acknowledge:
        if name not in pending:
            raise ValueError("Not a previously pending review path: " + name)
        del pending[name]
    pages = sorted(
        {
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "website/content").rglob("*.md")
        }
        | {p for p in MODELS if (ROOT / p).exists()}
    )
    if changed is None:
        reasons = {
            p: {"Initial or unavailable baseline: review applicability manually"}
            for p in pages
        }
    else:
        reasons = {}
        for source in changed:
            matches = {p for p in pages if source in (ROOT / p).read_text()}
            if source.startswith(
                ("src/", "packages/", "docs/adr/", "docs/architecture/")
            ):
                matches |= {
                    p
                    for p in pages
                    if "/architecture/" in p
                    or p in MODELS
                    or p == "website/content/index.md"
                }
            elif source.startswith("scripts/"):
                matches |= {
                    p
                    for p in pages
                    if "/schema/" in p or p.endswith("/development/index.md")
                }
            elif source.startswith(("tests/", ".github/")) or source in {
                "README.md",
                "AGENTS.md",
                "pyproject.toml",
                "uv.lock",
                "docs/local-python.md",
                "docs/testing.md",
            }:
                matches |= {p for p in pages if p.endswith("/development/index.md")}
            elif not matches:
                matches = set(
                    pages
                )  # Unknown dependencies remain explicitly conservative.
            for page in matches:
                reasons.setdefault(page, set()).add("Changed source: " + source)
    for name, new_reasons in reasons.items():
        old_reasons = set(pending.get(name, {}).get("reasons", []))
        pending[name] = {"path": name, "reasons": sorted(old_reasons | new_reasons)}
    return [pending[p] for p in sorted(pending)]


def generate(snapshot, destination, log):
    env = dict(os.environ)
    for key in ("PYTHONPATH", "RESOURCE_ATLAS_PRODUCT_ROOT", "UV_PROJECT_ENVIRONMENT"):
        env.pop(key, None)
    subprocess.run(
        [
            str(ROOT / "website/.venv/bin/python"),
            "website/tools/schema_viz.py",
            "--ir",
            "website/.build/inputs/inventory.json",
            "--format",
            "all",
            "--output-dir",
            str(destination),
        ],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        check=True,
    )


def apply_generated(destination, before, previous, private):
    staged = {}
    for p in sorted(destination.rglob("*")):
        if p.is_dir():
            continue
        name = p.relative_to(destination).as_posix()
        allowed = (
            name in {"README.md", "index.html"}
            or (name.startswith("dbml/") and p.suffix == ".dbml")
            or (name.startswith("mermaid/") and p.suffix == ".md")
        )
        if not allowed:
            raise ValueError("Unexpected generator output: " + name)
        file_record(p)
        staged[SCHEMA + name] = p.read_bytes()
    if not staged or not set(before).issubset(staged):
        raise ValueError("Incomplete generated artifact inventory")
    tracked = set(filter(None, git(ROOT, "ls-files", "-z").decode().split("\0")))
    if len(tracked | set(staged)) > 1000:
        raise ValueError("Refresh would exceed 1,000 tracked web files")
    if preflight_schema(previous) != before:
        raise ValueError("Schema files changed during generation; left untouched")
    changed = []
    # Validate every destination before the first tracked write.
    for name in staged:
        target = ROOT / name
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise ValueError("Linked schema destination refused")
        if target.exists():
            file_record(target)
    for name, raw in staged.items():
        existing = before.get(name, {})
        if (
            existing.get("sha256") == digest(raw)
            and not existing.get("mode", 0) & 0o111
        ):
            continue
        target = ROOT / name
        fd = private.directory_fd(target.parent)
        temporary = ".refresh-" + secrets.token_hex(12)
        try:
            out = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o644,
                dir_fd=fd,
            )
            with os.fdopen(out, "wb") as stream:
                stream.write(raw)
            if target.exists():
                if file_record(target) != before.get(name):
                    raise ValueError("Schema destination changed before replacement")
            elif name in before:
                raise ValueError("Schema destination disappeared before replacement")
            os.replace(temporary, target.name, src_dir_fd=fd, dst_dir_fd=fd)
            changed.append(name)
        finally:
            try:
                os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError:
                pass
            os.close(fd)
    return changed


def write_report(private, report):
    private.write_private_json(ROOT, ROOT / REPORT / "report.json", report)
    lines = [
        "# Website refresh report",
        "",
        "Status: " + report["status"],
        "",
        "This is local refresh bookkeeping, not semantic or release acceptance.",
        "",
        "Inspected source: "
        + report["inspected_source"]["commit"]
        + " ("
        + report["inspected_source"]["selection_mode"]
        + ")",
        "Prepared input source: "
        + report.get("prepared_source", {}).get("commit", "not prepared by this check"),
        "Attempt log: " + report.get("attempt_log", "none"),
        "",
        "## Machine actions",
        "",
        json.dumps(report.get("actions", {}), indent=2),
        "",
        "## Pending manual review",
        "",
    ]
    for item in report.get("pending_review", []):
        lines.append("- " + item["path"])
        lines.extend("  - " + reason for reason in item["reasons"])
    if not report.get("pending_review"):
        lines.append(
            "No pending items recorded; this is not a semantic verification result."
        )
    if report.get("error"):
        lines.extend(["", "Error: " + report["error"]])
    private.write_private(
        ROOT, ROOT / REPORT / "report.md", ("\n".join(lines) + "\n").encode()
    )


def refresh(snapshot, *, check=False, acknowledge=()):
    if check and acknowledge:
        raise ValueError("Check-only mode cannot acknowledge review items")
    integrity, private = prepare.product_helpers(snapshot)
    state_path = private.private_path(ROOT, ROOT / REPORT / "state.json")
    previous = json.loads(state_path.read_bytes()) if state_path.exists() else None
    if previous and previous.get("schema_version") != 1:
        raise ValueError("Unsupported refresh state")
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "inspected_source": snapshot,
        "actions": {},
    }
    try:
        before = preflight_schema(previous)
        inputs = product_fingerprints(snapshot)
        renderer = renderer_fingerprint()
        changed = changed_sources(previous, snapshot)
        pending = review_items(previous, changed, acknowledge)
        cache_valid = valid_prepared(previous, integrity, private)
        prepare_needed = not cache_valid or inputs != previous.get("product_inputs")
        generate_needed = (
            previous is None
            or renderer != previous.get("renderer")
            or before != previous.get("generated")
        )
        # Every rendering attempt gets the locked environment through the
        # existing verified preparation path, including lock/control changes.
        prepare_needed |= (
            generate_needed or not (ROOT / "website/.venv/bin/python").is_file()
        )
        report.update(
            pending_review=pending,
            source_changes=changed,
            baseline="unassessed" if changed is None else "recorded",
            actions={
                "prepare_needed": prepare_needed,
                "generation_needed": generate_needed or prepare_needed,
            },
        )
        if check:
            report["status"] = "check-only"
            write_report(private, report)
            return report
        log_path = ROOT / REPORT / ("attempt-" + secrets.token_hex(12) + ".log")
        report["attempt_log"] = log_path.relative_to(ROOT).as_posix()
        with private.private_log(ROOT, log_path) as log:
            if prepare_needed:
                prepare.prepare_inputs(snapshot, log=log)
            records, prepared = prepared_records(private)
            ir_hash = records["inventory.json"]["sha256"]
            generate_needed |= previous is None or ir_hash != previous.get("ir_sha256")
            changed_files = []
            if generate_needed:
                destination = (
                    ROOT
                    / "website/.build/output"
                    / ("refresh-" + secrets.token_hex(12))
                )
                generate(prepared, destination, log)
                if renderer_fingerprint() != renderer:
                    raise ValueError("Renderer controls changed during refresh")
                changed_files = apply_generated(destination, before, previous, private)
        integrity.verify_checkout(Path(prepared["path"]), prepared["commit"])
        if prepared_records(private) != (records, prepared):
            raise ValueError(
                "Prepared inputs changed during refresh; no baseline saved"
            )
        generated = schema_files()
        report.update(
            status="updated"
            if prepare_needed or generate_needed
            else "review-needed"
            if pending
            else "up-to-date",
            prepared_source=prepared,
            generated_files_changed=changed_files,
            actions={
                "prepared": prepare_needed,
                "generated": generate_needed,
                "reused_prepared_inputs": not prepare_needed,
            },
        )
        write_report(private, report)
        state = {
            "schema_version": 1,
            "inspected_source": snapshot,
            "prepared_source": prepared,
            "product_inputs": inputs,
            "renderer": renderer,
            "ir_sha256": ir_hash,
            "prepared_files": records,
            "generated": generated,
            "pending_review": pending,
        }
        private.write_private_json(ROOT, state_path, state)
        return report
    except Exception as error:
        report.update(status="failed", error=str(error))
        write_report(private, report)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--product-root",
        type=Path,
        help="Use an existing local checkout; do not claim remote freshness",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Write a plan/report without preparation, generation or baseline changes",
    )
    parser.add_argument(
        "--acknowledge",
        action="append",
        default=[],
        metavar="WEB_PATH",
        help="Clear a previously pending review item; new changes still add it again",
    )
    args = parser.parse_args()
    if args.check and args.acknowledge:
        parser.error("--check cannot acknowledge review items")
    try:
        snapshot = prepare.prepare_checkout(
            prepare.read_selection(), args.product_root, env=prepare.git_environment()
        )
        report = refresh(snapshot, check=args.check, acknowledge=args.acknowledge)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("Website refresh failed: " + str(error), file=sys.stderr)
        return 1
    print("Website refresh: " + report["status"])
    print(
        "Generated files changed: "
        + str(len(report.get("generated_files_changed", [])))
    )
    print("Pending manual review: " + str(len(report.get("pending_review", []))))
    print("Report: " + (REPORT / "report.md").as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
