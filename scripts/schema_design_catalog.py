"""Generate public design catalogs from the committed empty-fixture inventory.

No database is opened. Entries are proposals, not executable conversion rules.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

# target, transformation, deduplication, reparse/verification policy
POLICIES = {
    "schema_migrations": (
        "conversion_sources.source_migrations",
        "Archive source ledger; create a different target format ledger",
        "none",
        "Verify source DDL and packaged checksums; never rewrite to claim conversion",
    ),
    "catalog_meta": (
        "conversion_sources.source_catalog / database_identity",
        "Archive old identity; issue new DB instance, format_id and publication sequence",
        "none",
        "Old cursors invalid; source SHA and actual DDL recorded",
    ),
    "sources": (
        "sources",
        "local-git -> manual_git; github -> github_inventory; retain ID and raw settings",
        "none",
        "Validate JSON object and credential references; unknown settings preserved",
    ),
    "inventory_runs": (
        "inventory_observations",
        "Retain ID/scope/time/state as legacy assertion; split execution link",
        "none",
        "No inventory API replay without saved payload; completeness remains scoped",
    ),
    "repositories": (
        "repositories / legacy_records",
        "Remove source_id, provider_host, provider_repo_id and url projections",
        "no URL/OID-based merging",
        "Resolve endpoints and bindings independently; conflicting projections diagnosed",
    ),
    "repository_names": (
        "repository_name_assertions",
        "Preserve distinct seen-name assertion, not a fabricated full event history",
        "existing repo/name key only",
        "Observed_at retained with legacy first-seen semantics",
    ),
    "jobs": (
        "jobs / job_attempts / legacy_records",
        "Preserve request and last known attempt; running -> admission-required interrupted task",
        "none",
        "Do not fabricate prior attempts or reactivate processes; retain old state",
    ),
    "cache_entries": (
        "cache_locators",
        "Preserve identity/generation/path as source locator; verified read-only reuse reference",
        "none",
        "Do not activate source cache for writable new runtime; no deletion",
    ),
    "cache_leases": (
        "legacy_runtime_records",
        "Archive dead process lease evidence; never activate it",
        "none",
        "Offline shutdown required; lease does not establish live ownership",
    ),
    "space_reservations": (
        "legacy_runtime_records",
        "Archive source reservation; recompute destination admission separately",
        "none",
        "No active reservation inherited",
    ),
    "collection_runs": (
        "git_acquisitions / acquisition_progress / ref_capture_manifests",
        "Split acquisition fact, mutable progress and capture manifest; retain run ID",
        "none",
        "Validate endpoint/repo and closure evidence; unknown historic URL remains NULL",
    ),
    "preservation_obligations": (
        "acquisition_progress / publication_claims",
        "Preserve each flag and its legacy assertion; recompute proven postconditions",
        "none",
        "Cache loss or invalid flags cannot upgrade acquisition to published/complete",
    ),
    "snapshots": (
        "snapshots",
        "Retain ID; run_id -> acquisition_id; generation derived from acquisition",
        "none",
        "Scoped FK, publication and current pointer validation",
    ),
    "ref_observations": (
        "ref_observations / root_origins",
        "Retain raw BLOB names/OIDs; link distinct ref origins to shared seed",
        "no observation merging",
        "Validate OID/format; reconcile captured manifest without remote refs",
    ),
    "acquisition_roots": (
        "acquisition_roots / root_origins",
        "Keep seed IDs; add format to seed uniqueness, recover distinct origins from manifest/refs",
        "same acquisition/format/OID/role seed only",
        "Ambiguous PR origin kept unknown; one-to-many origin mapping tracked",
    ),
    "git_objects": (
        "git_objects",
        "Retain integer IDs, format/OID/type/size and legacy verification assertion",
        "format + complete OID; conflict blocks",
        "Rehash only when raw bytes exist; structural proof and legacy assertion distinguished",
    ),
    "repository_object_sources": (
        "repository_object_sources",
        "Retain provenance triples; run_id -> acquisition_id",
        "existing triple only",
        "Scoped acquisition/repo FK and actual object availability evidence",
    ),
    "commits": (
        "commits",
        "Retain raw headers/message and ordered structure",
        "existing object identity only",
        "Reconstruct raw only with OID proof; enforce object types/format",
    ),
    "commit_parents": (
        "commit_parents",
        "Retain parent_ordinal and duplicates at different positions",
        "existing commit/ordinal only",
        "Validate nonnegative/dense parent order and parent commit type",
    ),
    "tree_entries": (
        "tree_entries",
        "Preserve raw names/modes/OIDs, including gitlink without local child object",
        "existing tree/raw name only",
        "Raw tree byte order/mode spelling may require residual Git object; never invent bytes",
    ),
    "tag_objects": (
        "tag_objects",
        "Preserve raw payload and target",
        "existing object identity only",
        "Rehash available raw payload; enforce tag/target format",
    ),
    "contents": (
        "contents",
        "Preserve integer IDs and byte length/raw text/profile state",
        "no hash-only coalescing",
        "Validate available UTF-8 bytes; unavailable binary remains unavailable",
    ),
    "content_digests": (
        "content_digests",
        "Retain representation, algorithms, digest, verification time/pipeline",
        "existing content/representation/algorithm only",
        "Shape validation; rehash when raw available; never change old verified_at",
    ),
    "blob_content_map": (
        "blob_content_map",
        "Retain verified content association and first verification acquisition",
        "existing object key only",
        "Blob type, byte length and digest disagreement blocks",
    ),
    "content_locations": (
        "content_locations",
        "Preserve durable/cache locator evidence without writable source-cache ownership",
        "existing key only",
        "Unavailable locator is not empty raw text; inspect locators without mutation",
    ),
    "root_manifests": (
        "root_manifests",
        "Preserve tree ID and old completion assertion; rebuild only as needed",
        "existing tree only",
        "Compare canonical path multisets/closure, not count alone",
    ),
    "root_manifest_entries": (
        "root_manifest_entries",
        "Preserve raw path/mode/format/OID/object links",
        "existing tree/path only",
        "Reconstruct from saved tree graph and prove path/OID tuples",
    ),
    "coverage_components": (
        "coverage_claims / coverage_scopes",
        "Resolve polymorphic owner into explicit typed scope; preserve old assertion/details",
        "no observation merging",
        "Ambiguous owner archived; recompute effective coverage without silent promotion",
    ),
    "pull_requests": (
        "change_requests",
        "Retain ID; add binding_id and pull_request kind; current_observation scoped",
        "binding/kind/native number only after proof",
        "Ambiguous binding is blocking; never assign by number alone",
    ),
    "pr_observations": (
        "change_request_observations / observation_origins",
        "Retain ID/payload/time/publication; job link becomes origin provenance",
        "none, even identical payload",
        "Validate parent and JSON; parsed_at separate from observed_at",
    ),
    "pr_documents": (
        "documents",
        "Retain ID/native aliases/metadata and scoped current version",
        "same CR/kind/proven native aliases only",
        "No login/thread-ID-only merging; unsupported identity archived",
    ),
    "document_versions": (
        "document_versions / text_bodies",
        "Retain version ID; extract exact UTF-8 body into shared body record",
        "exact body bytes plus SHA candidate; document versions retain IDs",
        "Hash mismatch diagnosed; every observation/version link verified",
    ),
    "resource_observations": (
        "document_observations / observation_origins",
        "Retain every row/time; collection_run resolved as polymorphic origin",
        "none, including A-B-A",
        "Resolve job/page/GraphQL origin if proven; unknown raw key retained",
    ),
    "pr_reviews": (
        "reviews",
        "Retain ID/document/payload; pr_id -> change_request_id",
        "existing local ID only",
        "Scoped document/CR FK; raw payload retained",
    ),
    "review_threads": (
        "review_threads / thread_observations",
        "Keep local ID; external ID from saved payload; retain current legacy snapshot",
        "not by external ID across bindings",
        "No missing historical thread states invented; parent-scoped FK",
    ),
    "review_comments": (
        "review_comments / resource_payloads",
        "Preserve document/thread/payload; derive CR scope from proven document owner",
        "existing document key only",
        "Thread and document must share CR; NULL thread remains NULL",
    ),
    "pr_events": (
        "change_request_events / observation_origins",
        "Keep ID/run ordinal/provider ID/raw event; classify old run string origin",
        "not by equal payload or missing provider ID",
        "Unidentified repeated events retained, not collapsed",
    ),
    "pr_code_observations": (
        "code_observations / reanalysis_runs",
        "Retain IDs/head/base/assertions; add pointers to stable commit/file listings",
        "none across separate observations",
        "Cross-attempt head/base/context disagreement remains partial; derived repair separate",
    ),
    "pr_git_links": (
        "code_acquisitions",
        "Retain code/role/format/OID/acquisition relation",
        "existing relation only",
        "Validate same CR/repo/observation and role; dangling semantic link diagnosed",
    ),
    "pr_commits": (
        "code_commits / legacy_listing_items",
        "Reconcile saved pages into stable listing, not newly allocated code observation",
        "same proven listing/page/position; old tuples mapped explicitly",
        "Parse all saved pages; orphan/ambiguous rows retained without inventing order",
    ),
    "pr_file_changes": (
        "code_file_changes / legacy_listing_items",
        "Reconcile all saved file pages and raw patches into stable listing",
        "same proven listing/page/position only",
        "Do not coalesce renames/same path across observations; preserve raw patch",
    ),
    "api_responses": (
        "payloads",
        "Preserve integer IDs and exact decoded response bytes, including unreferenced bodies",
        "SHA candidate + exact bytes, never SHA alone",
        "Validate hash/length; malformed/unknown payload retained; no wire-byte claim",
    ),
    "collections": (
        "fetch_collections / collection_progress",
        "Retain ID/scope and acquisition start assertion; separate job/progress",
        "none across scans",
        "Complete requires page/context proof; finish time not synthesized",
    ),
    "collection_pages": (
        "fetch_occurrences / legacy_page_records",
        "Preserve each saved ordinal/request/body/cursor/time; assign occurrence IDs",
        "no fetch-observation dedup by body",
        "Recover REST vs GraphQL cursor chains; overwritten prior attempts unrecoverable",
    ),
    "collection_memberships": (
        "collection_memberships / listing_items",
        "Retain saved memberships; rebuild page-position association from payload",
        "same collection/resource only, raw repeated occurrences retained separately",
        "Resource namespace/type must be resolved; encoded ordinal not assumed dense",
    ),
    "sync_checkpoints": (
        "completion_markers / validators / incremental_scans / unresolved_payloads / resume_cursors / legacy_checkpoints",
        "Parse each known key dialect into typed state; archive raw scope/value/time",
        "no cross-account/instance/scope reuse",
        "Safe watermark cannot advance on replay; unknown scope disables only affected fast path",
    ),
    "search_documents": (
        "search_documents / legacy_derived_records",
        "Rebuild from validated durable sources, retaining IDs where identity unchanged",
        "existing semantic source only",
        "Compare full text/raw offsets and source-key mapping; no API or fetch",
    ),
    "index_generations": (
        "legacy_derived_records / index_generations",
        "Archive old physical generation metadata; build new destination index generations",
        "none",
        "Never copy arbitrary source table_name DDL; FTS optional, scan remains correct",
    ),
    "index_membership": (
        "legacy_derived_records / index_membership",
        "Archive membership evidence; derive destination membership from final search documents",
        "per new index/document",
        "Verify exact input versions and membership set, not count only",
    ),
    "service_instances": (
        "service_instances",
        "Retain UUID/kind/base URLs and metadata",
        "no URL-based instance merging",
        "Instance identity independent of accounts, hostname, port or base-path normalization",
    ),
    "repository_bindings": (
        "repository_bindings",
        "Add binding UUID; map old composite key; preserve native identity/metadata/time",
        "instance + native ID, NULL not an identity",
        "Binding map resolves PR namespaces; conflicts are not merged implicitly",
    ),
    "repository_endpoints": (
        "repository_endpoints / repositories.preferred_endpoint_id",
        "Retain UUID/URL/transport/label/metadata; move preferred flag into scoped pointer",
        "existing repo/exact URL only",
        "Missing/conflicting preference diagnosed; no historic URL backfill",
    ),
    "source_repositories": (
        "source_repositories",
        "Preserve membership and maintenance timestamps with explicit legacy semantics",
        "existing source/repo key only",
        "Backfill timestamp is not provider discovery time",
    ),
}

RENAMES = {
    ("sources", "kind"): "sources.discovery_kind",
    ("repositories", "source_id"): "legacy_records.primary_source_id",
    ("repositories", "provider_host"): "legacy_records.provider_host",
    ("repositories", "provider_repo_id"): "legacy_records.provider_repo_id",
    ("repositories", "url"): "legacy_records.preferred_url_projection",
    ("repositories", "current_snapshot"): "repositories.current_snapshot_id",
    ("jobs", "attempt"): "jobs.latest_attempt / job_attempts.attempt",
    ("jobs", "checkpoint"): "legacy_checkpoints / typed resume state",
    ("collection_runs", "job_id"): "acquisition_progress.job_id",
    ("collection_runs", "cache_id"): "acquisition_progress.cache_id",
    ("collection_runs", "attempt"): "acquisition_progress.attempt",
    ("collection_runs", "state"): "acquisition_progress.state / publication_claims",
    ("collection_runs", "roots_manifest"): "ref_capture_manifests.raw_json",
    (
        "snapshots",
        "generation",
    ): "legacy_records.snapshot_generation / git_acquisitions.generation",
    ("document_versions", "body"): "text_bodies.body",
    ("document_versions", "body_sha256"): "text_bodies.sha256 / legacy asserted hash",
    ("pr_documents", "current_version"): "documents.current_version_id",
    ("pull_requests", "current_observation"): "change_requests.current_observation_id",
    (
        "resource_observations",
        "collection_run",
    ): "observation_origins.raw_legacy_key / typed origin",
    ("pr_events", "run_id"): "observation_origins.raw_legacy_key / typed origin",
    (
        "repository_endpoints",
        "is_preferred",
    ): "repositories.preferred_endpoint_id / legacy flag",
    ("collections", "cursor"): "collection_progress.resume_cursor",
    ("collections", "job_id"): "collection_progress.job_id / acquisition origin",
    ("collections", "state"): "collection_progress.state / completion assertion",
    (
        "collection_pages",
        "observed_at",
    ): "fetch_occurrences.fetched_at / original asserted time",
    (
        "collections",
        "observed_at",
    ): "fetch_collections.registered_at / scan-time evidence",
    ("repository_names", "observed_at"): "repository_name_assertions.first_seen_at",
    ("api_responses", "payload_sha256"): "payloads.sha256",
    ("jobs", "state"): "jobs.admission_state / legacy_records.typed_fields.state",
    (
        "coverage_components",
        "owner_id",
    ): "coverage_scopes.typed_owner / legacy_records.typed_fields.owner_id",
    (
        "coverage_components",
        "state",
    ): "coverage_claims.asserted_state / derived effective state",
    (
        "pr_code_observations",
        "state",
    ): "legacy_records.typed_fields.state / code_observations.state after validation",
    (
        "pr_commits",
        "code_observation",
    ): "code_commits.listing_id via collection/context evidence / legacy_listing_items.source_code_observation",
    (
        "pr_commits",
        "ordinal",
    ): "code_commits.page_ordinal,position / legacy_listing_items.source_ordinal",
    (
        "pr_commits",
        "oid",
    ): "code_commits.object_format,oid after hexadecimal proof / raw source OID text",
    (
        "pr_file_changes",
        "code_observation",
    ): "code_file_changes.listing_id via collection/context evidence / legacy_listing_items.source_code_observation",
    (
        "pr_file_changes",
        "ordinal",
    ): "code_file_changes.page_ordinal,position / legacy_listing_items.source_ordinal",
    (
        "sync_checkpoints",
        "scope",
    ): "legacy_checkpoints.scope / typed checkpoint scope after key-dialect parsing",
    (
        "sync_checkpoints",
        "value",
    ): "legacy_checkpoints.raw_value / typed state and unresolved payload",
    (
        "sync_checkpoints",
        "updated_at",
    ): "legacy_checkpoints.updated_at / state-maintenance time, not scan start",
}


def rows(inventory):
    actual = {table["name"] for table in inventory["tables"]}
    if actual != set(POLICIES):
        raise ValueError(
            f"Review required: table catalog mismatch {sorted(actual ^ set(POLICIES))}"
        )
    result = []
    for table in inventory["tables"]:
        name = table["name"]
        target, transform, dedup, verification = POLICIES[name]
        for column in table["columns"]:
            col = column["name"]
            base = target.split(" / ")[0]
            field = ".typed_fields." if base.startswith("legacy_") else "."
            destination = RENAMES.get((name, col), base + field + col)
            if (name, col) not in RENAMES:
                if col == "pr_id":
                    destination = base + ".change_request_id"
                elif col == "run_id" and name not in ("pr_events",):
                    destination = base + ".acquisition_id"
            result.append(
                {
                    "source_table": name,
                    "source_column": col,
                    "target": destination,
                    "column_rule": "Explicit projection/split"
                    if (name, col) in RENAMES
                    else "Preserve typed value and NULL; table-level transform/validation applies",
                    "table_rule": transform,
                    "dedup_rule": dedup,
                    "reparse_and_validation": verification,
                    "failure_policy": "Record diagnostic + typed legacy value; block unsafe semantic activation; never discard silently",
                }
            )
    return result


def source_access(root, tables):
    result = {
        table: {"read": set(), "write": set(), "other": set()} for table in tables
    }
    pattern = re.compile(
        r"\b(INSERT(?:\s+OR\s+\w+)?\s+INTO|UPDATE|DELETE\s+FROM|FROM|JOIN)\s+([a-z_]+)\b",
        re.I,
    )
    for path in (root / "src").rglob("*.py"):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for match in pattern.finditer(line):
                table = match[2].lower()
                if table in result:
                    mode = "read" if match[1].upper() in ("FROM", "JOIN") else "write"
                    result[table][mode].add(f"{path.relative_to(root)}:{number}")
    return {t: {k: sorted(v) for k, v in modes.items()} for t, modes in result.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("docs/schema-hardening/current-schema.json"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("docs/schema-hardening")
    )
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    mapped = rows(inventory)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "column-conversion.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(mapped[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(mapped)
    root = Path(__file__).resolve().parents[1]
    (args.output_dir / "source-access.json").write_text(
        json.dumps(
            {
                "limitations": "Lexical SQL table references, not a call graph; dynamic SQL, filesystem and tests require manual review in README.md",
                "tables": source_access(root, POLICIES),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    with (args.output_dir / "table-conversion.md").open("w") as stream:
        stream.write(
            "# v2テーブル変換対応案\n\n各列の対応はcolumn-conversion.csv。ここにある規則は設計案であり、変換実装ではありません。失敗時は原本・旧typed値・診断を保持し、必要な意味付けができるまで利用を止めます。\n\n| v2 table | target | transform | dedup | reparse / validation |\n|---|---|---|---|---|\n"
        )
        for name, policy in sorted(POLICIES.items()):
            stream.write("| " + " | ".join((name, *policy)) + " |\n")


if __name__ == "__main__":
    main()
