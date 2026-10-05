import copy
import hashlib
import io
import json
import zipfile

import pytest

from scripts import ci_plan
from scripts.ci_evidence import retrieve, verify_envelope
from tests.support.ci_fixture import context, envelope, manifest, repository


@pytest.fixture
def evidence_case(tmp_path):
    root = tmp_path / "repo"
    base, head = repository(root)
    record = manifest(ci_plan.make_plan(context(root, base, head), root=root))
    return dict(record["context"], run_id="11"), envelope(record)


@pytest.mark.parametrize(
    "mutation",
    [
        "cancelled",
        "failed",
        "queued",
        "wrong-repository",
        "fork",
        "wrong-pr",
        "wrong-revision",
        "wrong-base",
        "wrong-path",
        "expired",
        "expired-time",
        "checksum",
        "manifest-checksum",
        "artifact-run",
        "artifact-fork",
        "incomplete-jobs",
        "skipped-job",
        "skipped-gate",
        "missing-gate",
        "same-run",
    ],
)
def test_remote_evidence_rejects_untrusted_incomplete_and_expired_metadata(
    evidence_case, mutation
):
    ctx, value = copy.deepcopy(evidence_case)
    run, artifact, jobs = value["run"], value["artifact"], value["jobs"]
    if mutation == "cancelled":
        run["conclusion"] = "cancelled"
    elif mutation == "failed":
        run["conclusion"] = "failure"
    elif mutation == "queued":
        run["status"] = "queued"
    elif mutation == "wrong-repository":
        run["repository"]["full_name"] = "wrong/repository"
    elif mutation == "fork":
        run["head_repository"]["full_name"] = "wrong/fork"
    elif mutation == "wrong-pr":
        run["pull_requests"][0]["number"] = 2
    elif mutation == "wrong-revision":
        run["head_sha"] = "f" * 40
    elif mutation == "wrong-base":
        run["pull_requests"][0]["base"]["sha"] = "f" * 40
    elif mutation == "wrong-path":
        run["path"] = ".github/workflows/other.yml"
    elif mutation == "expired":
        artifact["expired"] = True
    elif mutation == "expired-time":
        artifact["expires_at"] = "2000-01-01T00:00:00Z"
    elif mutation == "checksum":
        value["archive_sha256"] = "f" * 64
    elif mutation == "manifest-checksum":
        value["manifest_sha256"] = "f" * 64
    elif mutation == "artifact-run":
        artifact["workflow_run"]["id"] = 11
    elif mutation == "artifact-fork":
        artifact["workflow_run"]["head_repository_id"] = 99
    elif mutation == "incomplete-jobs":
        jobs["total_count"] = 2
    elif mutation == "skipped-job":
        jobs["jobs"][0]["conclusion"] = "skipped"
    elif mutation == "skipped-gate":
        jobs["jobs"][0]["steps"][0]["conclusion"] = "skipped"
    elif mutation == "missing-gate":
        jobs["jobs"][0]["steps"] = []
    else:
        ctx["run_id"] = "10"
    with pytest.raises(ValueError):
        verify_envelope(value, ctx)


class StoredActions:
    def __init__(self, ctx, envelope, *, corruption=None):
        self.calls = []
        self.ctx, self.envelope, self.corruption = ctx, envelope, corruption
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("validation-manifest.json", envelope["manifest_bytes"])
        self.raw = output.getvalue()
        envelope["artifact"]["digest"] = (
            "sha256:" + hashlib.sha256(self.raw).hexdigest()
        )

    def get(self, path, *, binary=False):
        self.calls.append(path)
        if "/workflows/" in path:
            return {"workflow_runs": [self.envelope["run"]]}
        if path.endswith("/zip"):
            return b"corrupt" if self.corruption == "checksum" else self.raw
        if "/jobs?" in path:
            return self.envelope["jobs"]
        return {
            "total_count": 2 if self.corruption == "truncated" else 1,
            "artifacts": []
            if self.corruption == "missing"
            else [self.envelope["artifact"]],
        }


def test_one_bounded_checksum_verified_artifact_lookup(evidence_case):
    ctx, value = evidence_case
    client = StoredActions(ctx, value)
    result = retrieve(ctx, client)
    assert result["manifest"] == value["manifest"]
    assert len(client.calls) == 4
    assert sum(p.endswith("/zip") for p in client.calls) == 1
    verify_envelope(result, ctx)


@pytest.mark.parametrize("corruption", ["checksum", "truncated", "missing"])
def test_missing_truncated_or_corrupt_download_cannot_supply_success(
    evidence_case, corruption
):
    ctx, value = evidence_case
    with pytest.raises(ValueError):
        retrieve(ctx, StoredActions(ctx, value, corruption=corruption))


def test_fork_and_manual_context_do_not_download_any_evidence(evidence_case):
    ctx, value = evidence_case
    client = StoredActions(ctx, value)
    assert retrieve(dict(ctx, head_repository="untrusted/fork"), client) is None
    assert retrieve(dict(ctx, event="workflow_dispatch"), client) is None
    assert not client.calls


def test_old_artifact_without_new_gate_manifest_falls_back(evidence_case):
    ctx, value = evidence_case
    client = StoredActions(ctx, value)
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("tests.json", json.dumps({"exit_code": 0}))
    client.raw = raw.getvalue()
    value["artifact"]["digest"] = "sha256:" + hashlib.sha256(client.raw).hexdigest()
    with pytest.raises(ValueError, match="manifest"):
        retrieve(ctx, client)
