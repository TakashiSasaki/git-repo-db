import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path("/workspace/g3-review-docs-final")
OUT = Path("/tmp/g3-doc-post-review")
FREEZE = "6bc9525ab853344fba309b28aee343250f575738"
START = "3e6debe41f8e75f0a75be3a71cb1b12a0b70f0f5"
BASE = "24f593861327328fa00dab0b83f956cec330a0ac"
F2 = "9eeacb28f7e4a426114a9ce40e2324b4da302817"
R2 = "8ab57eb74068f5ba303b5985a335f0f76be4fdd2"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def sha(b):
    return hashlib.sha256(b).hexdigest()


def headings(path):
    result = set()
    counts = {}
    for line in path.read_text().splitlines():
        if m := re.match(r"^#{1,6} +(.*)", line):
            slug = "".join(
                c for c in m[1].strip().lower() if c.isalnum() or c in " _-"
            ).replace(" ", "-")
            n = counts.get(slug, 0)
            counts[slug] = n + 1
            result.add(slug + ("-" + str(n) if n else ""))
    return result


assert git("rev-parse", "HEAD").decode().strip() == FREEZE
assert git("status", "--porcelain") == b""
changed = git("diff", "--name-only", START, FREEZE).decode().splitlines()
stack = git("diff", "--name-only", BASE, FREEZE).decode().splitlines()
checks = {}
for base, name in ((START, "update"), (BASE, "stack")):
    p = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--check", base, FREEZE],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    checks[name + "_diff_check"] = "passed"
protected = (
    "src/",
    "tests/",
    ".github/",
    "pyproject.toml",
    "uv.lock",
    "AGENTS.md",
    "mkdocs.yml",
)
assert not any(any(f == p or f.startswith(p) for p in protected) for f in changed)
assert not any(
    f.startswith("docs/adr/")
    and f
    not in ("docs/adr/README.md", "docs/adr/0031-generalized-context-resources.md")
    for f in changed
)
checks["protected_paths_and_accepted_ADRs_unchanged"] = True
historical = [
    "cprime-independent-review.md",
    "cprime-independent-checks.json",
    "cprime-source-verification.json",
    "publication-checks.json",
]
for name in historical:
    path = "docs/implementation/evidence/context-resource-design/" + name
    assert git("rev-parse", START + ":" + path) == git(
        "rev-parse", FREEZE + ":" + path
    ), path
checks["old_review_receipts_unchanged"] = historical
mddocs = [ROOT / p for p in changed if p.endswith(".md")]
links = 0
anchors = 0
pins = set()
files = 0
for path in [ROOT / p for p in changed]:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        continue
    text = raw.decode("utf-8")
    assert text.strip() and not text.startswith("\ufeff"), path
    files += 1
    if path.suffix == ".json":
        assert isinstance(json.loads(text), dict), path
    if path.suffix != ".md":
        continue
    fenced = None
    for line in text.splitlines():
        m = re.match(r"^\s*(`{3,}|~{3,})", line)
        if m:
            if fenced is None:
                fenced = m[1][0]
            elif fenced == m[1][0]:
                fenced = None
    assert fenced is None, path
    hrefs = re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', text) + re.findall(
        r"^\[[^\]]+\]:\s*(\S+)", text, re.M
    )
    for href in hrefs:
        if href.startswith(("http:", "https:", "mailto:")):
            if m := re.match(
                r"https://github.com/TakashiSasaki/git-repo-db/blob/([0-9a-f]{40})/(.+?)(?:#.*)?$",
                href,
            ):
                pins.add((m[1], unquote(m[2])))
            continue
        dest, _, anchor = unquote(href).partition("#")
        target = (path.parent / dest).resolve() if dest else path
        assert target.exists(), (path, href)
        links += 1
        if anchor and target.suffix == ".md":
            assert anchor in headings(target), (path, href)
            anchors += 1
for commit, path in pins:
    git("cat-file", "-e", commit + ":" + path)
checks.update(
    {
        "strict_utf8_nonempty_files": files,
        "changed_markdown_files": len(mddocs),
        "local_link_occurrences": links,
        "anchor_occurrences": anchors,
        "pinned_git_blob_targets": len(pins),
    }
)
adr = (ROOT / "docs/adr/0031-generalized-context-resources.md").read_text()
index = (ROOT / "docs/adr/README.md").read_text()
assert adr.startswith("---\nstatus: proposed\ndate: null\nreplaces: []\n")
assert index.count("| [0031]") == 1
for choice in [
    "A3",
    "B3",
    "U3=C′",
    "U4=B",
    "U5=A",
    "U1=B",
    "U2=A",
    "U2-E2",
    "G3=A",
    "2026-10-21",
]:
    assert choice in adr, choice
checks["frontmatter_index_fixed_choices"] = "passed"
checks["main_112_message"] = (
    git("show", "efb55af84ccbf1183d47547d22bb6c57d8fbc8f9", "--no-patch", "--format=%B")
    .decode()
    .strip()
)
assert "#112" in checks["main_112_message"]
p = subprocess.run(
    ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", BASE, FREEZE]
)
assert p.returncode == 0
p = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", F2, FREEZE])
assert p.returncode == 1
checks["stack_ancestry_preserved_F2_external"] = True
manifest_path = "docs/implementation/evidence/context-resource-u3-cprime/semantic-gaps/input-freeze.json"
old_manifest = json.loads(git("show", F2 + ":" + manifest_path))
for path, digest in old_manifest["inputs_sha256"].items():
    assert sha(git("show", F2 + ":" + path)) == digest, path
    assert sha(git("show", R2 + ":" + path)) == digest, path
checks["F2_and_R2_18_inputs_match"] = len(old_manifest["inputs_sha256"])
new_manifest = json.loads(
    (
        ROOT
        / "docs/implementation/evidence/context-resource-design/g3-a/input-freeze.json"
    ).read_text()
)
for path, record in new_manifest["inputs"].items():
    raw = (ROOT / path).read_bytes()
    assert len(raw) == record["bytes"] and sha(raw) == record["sha256"], path
checks["new_frozen_executable_inputs_match"] = len(new_manifest["inputs"])
# Pure constructor composition: import source to generate text only; no SQL connection.
sys.path[:0] = [
    str(ROOT / "src"),
    str(ROOT / "docs/implementation/evidence/context-resource-design/g3-a/candidates"),
]
import cprime  # noqa: E402 -- select the reviewed frozen checkout first

sql = cprime.sql().encode()
assert sha(sql) == new_manifest["candidate_sql_sha256"]
checks["candidate_sql_sha256"] = sha(sql)
checks["frozen_document_sha256"] = {
    str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in mddocs
}
result = {
    "reviewer": "independent_docs (non-author)",
    "scope": "read-only final documentation/source/evidence-pin review; no SQLite execution",
    "reviewed_commit": FREEZE,
    "reviewed_tree": git("rev-parse", FREEZE + "^{tree}").decode().strip(),
    "update_base": START,
    "stack_base": BASE,
    "checks": checks,
    "changed_files": changed,
    "stack_files": stack,
    "findings": [],
    "verdict": "DOCUMENTATION READY; overall acceptance readiness depends on new runtime receipts and separate independent SQL review",
}
(OUT / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {k: v for k, v in checks.items() if k != "frozen_document_sha256"}, indent=2
    )
)
