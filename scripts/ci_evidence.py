"""Bounded, read-only Actions evidence retrieval. Artifacts are never build caches."""

import argparse
import hashlib
import io
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

LIMIT = 8 * 1024 * 1024
WORKFLOW = ".github/workflows/tests.yml"
GATE_STEP = "Validate plan and all required outcomes"


def verify_envelope(envelope, context):
    run, artifact, jobs = (envelope[k] for k in ("run", "artifact", "jobs"))
    manifest = envelope["manifest"]
    prior = manifest["context"]
    repository = context["repository"]
    if (
        run["repository"]["full_name"] != repository
        or run["head_repository"]["full_name"] != repository
    ):
        raise ValueError("Wrong repository/fork evidence")
    if (
        run["status"] != "completed"
        or run["conclusion"] != "success"
        or run["event"] != "pull_request"
        or run["path"] != WORKFLOW
    ):
        raise ValueError("Wrong/incomplete/failed workflow evidence")
    if not any(
        p["number"] == context["pr"]
        and p["head"]["sha"] == prior["feature_sha"]
        and p["base"]["sha"] == prior["base_sha"]
        for p in run["pull_requests"]
    ):
        raise ValueError("Wrong or missing PR evidence")
    if (
        str(run["id"]) == str(context.get("run_id"))
        or run["head_sha"] != prior["feature_sha"]
        or str(run["id"]) != str(prior["run_id"])
        or str(run["run_attempt"]) != str(prior["run_attempt"])
    ):
        raise ValueError("Wrong run/revision identity")
    if artifact["expired"] or datetime.fromisoformat(
        artifact["expires_at"].replace("Z", "+00:00")
    ) <= datetime.now(UTC):
        raise ValueError("Expired prior artifact")
    expected_name = f"ci-profile-{run['id']}-{run['run_attempt']}"
    association = artifact["workflow_run"]
    if (
        artifact["name"] != expected_name
        or association["id"] != run["id"]
        or association["head_sha"] != run["head_sha"]
        or association["repository_id"] != run["repository"]["id"]
        or association["head_repository_id"] != run["repository"]["id"]
    ):
        raise ValueError("Artifact/run/repository association differs")
    if artifact.get("digest") != "sha256:" + envelope["archive_sha256"]:
        raise ValueError("Artifact archive checksum differs/missing")
    if (
        envelope["manifest_sha256"]
        != hashlib.sha256(envelope["manifest_bytes"].encode()).hexdigest()
        or json.loads(envelope["manifest_bytes"]) != manifest
    ):
        raise ValueError("Manifest bytes/checksum differ")
    if jobs["total_count"] != len(jobs["jobs"]) or len(jobs["jobs"]) != 1:
        raise ValueError("Incomplete or unexpected jobs")
    job = jobs["jobs"][0]
    if (
        job["name"] != "offline"
        or job["status"] != "completed"
        or job["conclusion"] != "success"
        or job["head_sha"] != prior["feature_sha"]
    ):
        raise ValueError("Wrong/failed/skipped acceptance job")
    gates = [s for s in job["steps"] if s["name"] == GATE_STEP]
    if (
        len(gates) != 1
        or gates[0]["status"] != "completed"
        or gates[0]["conclusion"] != "success"
    ):
        raise ValueError("Missing or skipped final acceptance gate")


class Actions:
    """No third-party client, pagination ambiguity, unbounded polling, or write API."""

    def __init__(self, repository, token):
        if repository != "TakashiSasaki/git-repo-db":
            raise ValueError("Evidence repository is not approved")
        self.root = "https://api.github.com/repos/" + repository
        self.token = token
        self.requests = 0

    def get(self, suffix, *, binary=False):
        self.requests += 1
        if self.requests > 5:
            raise ValueError("Evidence lookup budget exceeded")
        request = urllib.request.Request(
            self.root + suffix,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        class Redirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                if urllib.parse.urlsplit(newurl).scheme != "https":
                    raise ValueError("Non-HTTPS evidence redirect")
                redirected = super().redirect_request(
                    req, fp, code, msg, headers, newurl
                )
                if (
                    urllib.parse.urlsplit(newurl).netloc
                    != urllib.parse.urlsplit(req.full_url).netloc
                ):
                    redirected.remove_header("Authorization")
                return redirected

        with urllib.request.build_opener(Redirect()).open(
            request, timeout=15
        ) as response:
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("Evidence response exceeds bounded size")
        return raw if binary else json.loads(raw)


def retrieve(context, client):
    """Inspect five recent runs, download at most one manifest; any ambiguity falls back."""
    if (
        context["event"] != "pull_request"
        or context.get("full")
        or context.get("head_repository") != context["repository"]
    ):
        return None
    query = urllib.parse.urlencode({"event": "pull_request", "per_page": 5})
    listing = client.get("/actions/workflows/tests.yml/runs?" + query)
    candidates = [
        r
        for r in listing["workflow_runs"]
        if str(r["id"]) != str(context.get("run_id"))
        and r["status"] == "completed"
        and r["conclusion"] == "success"
        and any(p["number"] == context["pr"] for p in r["pull_requests"])
        and r["head_repository"]["full_name"] == context["repository"]
    ]
    if not candidates:
        return None
    run = candidates[0]
    artifacts = client.get(f"/actions/runs/{run['id']}/artifacts?per_page=100")
    if artifacts["total_count"] != len(artifacts["artifacts"]):
        raise ValueError("Truncated artifact listing")
    name = f"ci-profile-{run['id']}-{run['run_attempt']}"
    chosen = [
        a for a in artifacts["artifacts"] if a["name"] == name and not a["expired"]
    ]
    if len(chosen) != 1:
        raise ValueError("Missing/ambiguous prior artifact")
    artifact = chosen[0]
    raw = client.get(f"/actions/artifacts/{artifact['id']}/zip", binary=True)
    checksum = hashlib.sha256(raw).hexdigest()
    if artifact.get("digest") != "sha256:" + checksum:
        raise ValueError("Prior artifact download checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = [
            i for i in archive.infolist() if i.filename == "validation-manifest.json"
        ]
        if (
            len(entries) != 1
            or entries[0].file_size > LIMIT
            or sum(i.file_size for i in archive.infolist()) > LIMIT
        ):
            raise ValueError("Missing/duplicate/oversized validation manifest")
        payload = archive.read(entries[0]).decode("utf-8")
    jobs = client.get(
        f"/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100"
    )
    envelope = {
        "run": run,
        "artifact": artifact,
        "jobs": jobs,
        "archive_sha256": checksum,
        "manifest_bytes": payload,
        "manifest_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "manifest": json.loads(payload),
    }
    verify_envelope(envelope, context)
    return envelope


def main():
    from scripts.ci_plan import ROOT, SHA, context_from_environment

    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/ci-profile")
    args = parser.parse_args()
    context = context_from_environment()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence.json").unlink(missing_ok=True)
    note = {
        "available": False,
        "requests": 0,
        "reason": "No token/eligible event; execute conservatively",
    }
    token = os.environ.get("CI_READ_TOKEN")
    if token:
        client = Actions(context["repository"], token)
        try:
            envelope = retrieve(context, client)
            if envelope:
                tested = envelope["manifest"]["context"]["tested_sha"]
                if not SHA.fullmatch(tested):
                    raise ValueError("Invalid prior tested revision")
                # A replaced synthetic merge need not be reachable from checkout.
                if subprocess.run(
                    ["git", "cat-file", "-e", tested + "^{commit}"], capture_output=True
                ).returncode:
                    subprocess.run(
                        ["git", "fetch", "--no-tags", "origin", tested],
                        check=True,
                        timeout=30,
                        capture_output=True,
                    )
                (output / "evidence.json").write_text(
                    json.dumps(envelope, indent=2) + "\n"
                )
                note = {
                    "available": True,
                    "run_id": envelope["run"]["id"],
                    "reason": "Downloaded checksum-verified manifest; planner verifies equivalence",
                }
        except Exception as error:
            # Never print HTTP URLs, headers, tokens, arbitrary artifact contents.
            note["reason"] = "Evidence unavailable/rejected: " + type(error).__name__
        note["requests"] = client.requests
    note["wall_seconds"] = time.perf_counter() - started
    (output / "evidence-lookup.json").write_text(json.dumps(note, indent=2) + "\n")
    print(json.dumps(note))


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
