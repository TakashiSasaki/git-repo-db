"""Explicit current-decision publication set; no recursive ADR publishing."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
# Owner-authorized scope: current accepted index, including partially superseded
# records and its two preserved unnumbered decisions. New ADRs require selection.
PUBLIC_ADRS = (
    "docs/adr/0001-validation-lifecycle-architecture.md",
    "docs/adr/0002-three-store-boundary-architecture.md",
    "docs/adr/0004-metadata-only-git-core.md",
    "docs/adr/0005-common-oid-identity-with-attributed-metadata.md",
    "docs/adr/0006-field-claims-and-observation-scoped-relations.md",
    "docs/adr/0007-verification-aware-git-metadata-reads.md",
    "docs/adr/0008-domain-split-git-verification-ownership.md",
    "docs/adr/0009-bounded-byte-admission-and-physical-health.md",
    "docs/adr/0010-operation-scoped-cas-physical-integrity.md",
    "docs/adr/0011-adr-governance.md",
    "docs/adr/0012-append-only-multiple-cas-physical-instances.md",
    "docs/adr/0013-deterministic-cas-instance-eligibility.md",
    "docs/adr/0014-history-and-notes-catalog-without-file-archive.md",
    "docs/adr/0015-automatic-git-notes-ref-discovery.md",
    "docs/adr/0016-immutable-notes-ref-capture-observations.md",
    "docs/adr/0017-domain-keys-without-storage-surrogates.md",
    "docs/adr/0022-receiver-verified-notes-role-admission.md",
    "docs/adr/0023-configurable-finite-notes-resource-budgets.md",
    "docs/adr/0024-actual-notes-resource-work-accounting.md",
    "docs/adr/0025-cumulative-request-budgets-and-scoped-blockers.md",
    "docs/adr/0028-classified-times-and-sha256-exchange.md",
    "docs/adr/0029-independent-access-store.md",
    "docs/adr/0030-context-repository-relations-and-selective-exchange.md",
    "docs/adr/0031-generalized-context-resources.md",
    "docs/adr/0032-environment-sqlite-validation.md",
    "docs/adr/0033-minimal-product-sdist.md",
    "docs/transport-independent-core-adr.md",
    "docs/phase2/no-independent-publication-adr.md",
    "docs/adr/0034-repository-test-and-ci-efficiency.md",
    "docs/adr/0035-independent-documentation-workspace.md",
    "docs/adr/0036-ref-observations-and-shared-notes-mappings.md",
    "docs/adr/0037-operation-scoped-module-independence.md",
    "docs/adr/0038-scoped-recovery-and-optional-initialization.md",
)
SUPPORT = ("docs/adr/policy.md",)


def destinations() -> dict[str, str]:
    return {p: "adr/" + Path(p).name for p in (*PUBLIC_ADRS, *SUPPORT)}


def rewrite_links(text: str, source: str, revision: str) -> str:
    published = destinations()
    published["docs/adr/README.md"] = "adr/index.md"

    def replace(match):
        target = match.group(2)
        parsed = urlsplit(target)
        if (
            parsed.scheme
            or parsed.netloc
            or not parsed.path
            or parsed.path.startswith("/")
        ):
            return match.group(0)
        resolved = posixpath.normpath(
            posixpath.join(posixpath.dirname(source), parsed.path)
        )
        suffix = ("?" + parsed.query if parsed.query else "") + (
            "#" + parsed.fragment if parsed.fragment else ""
        )
        if resolved in published:
            url = posixpath.relpath(published[resolved], "adr") + suffix
        else:
            # External repository links do not copy additional documents/scripts.
            url = (
                f"https://github.com/TakashiSasaki/git-repo-db/blob/{revision}/{resolved}"
                + suffix
            )
        return match.group(1) + url + ")"

    return re.sub(r"(!?\[[^\]]*\]\()([^\s)]+)\)", replace, text)


def accepted_rows() -> dict[str, str]:
    body = (
        (ROOT / "docs/adr/README.md")
        .read_text()
        .split("## Accepted Records\n", 1)[1]
        .split("## Proposed Records", 1)[0]
    )
    result = {}
    for row in body.splitlines():
        match = re.match(r"\| \[[^\]]+\]\(([^)]+)\)", row)
        if match:
            path = posixpath.normpath("docs/adr/" + match.group(1))
            result[path] = row
    if set(result) != set(PUBLIC_ADRS):
        raise ValueError(
            "Accepted ADR index differs from explicit publication allowlist; review selection"
        )
    return result


def stage_adrs(staging: Path, revision: str) -> None:
    rows = accepted_rows()
    target = staging / "adr"
    target.mkdir(parents=True, exist_ok=True)
    intro = (
        (ROOT / "documentation/content/adr/index.md")
        .read_text()
        .replace(
            "/blob/main/docs/adr/README.md", f"/blob/{revision}/docs/adr/README.md"
        )
    )
    table = (
        "| ADR | Decision | Date | Current applicability |\n| --- | --- | --- | --- |\n"
        + "\n".join(rows.values())
        + "\n"
    )
    (target / "index.md").write_text(
        intro + "\n" + rewrite_links(table, "docs/adr/README.md", revision)
    )
    for source, dest in destinations().items():
        path = ROOT / source
        if path.is_symlink():
            raise ValueError("Symlink ADR source refused")
        raw = path.read_text()
        if source in rows:
            # Applicability is copied from the canonical index, outside ADR body.
            scope = rows[source].split("|")[-2].strip()
            banner = (
                "> **現在の適用範囲（正本索引）:** "
                + scope
                + "\n> 全文には過去の用語や未採択の実装提案も含まれます。後継 ADR と部分置換の範囲を併読してください。\n\n"
            )
            if raw.startswith("---\n"):
                end = raw.index("\n---", 4) + 5
                raw = raw[:end] + banner + raw[end:]
            else:
                raw = banner + raw
        (staging / dest).write_text(rewrite_links(raw, source, revision))
