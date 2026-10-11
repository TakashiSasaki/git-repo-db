"""Validate proposal artifacts and map every audited Schema 18 object conditionally.

Disposition means responsibility/dependency order, never executable DROP advice.
Static readers/writers are clearly labeled; workstream runtime traces establish
live consumers. All generated input is repository code/schema, not catalog data.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/phase2"

# Hand-reviewed groups point to actual caller/producer/consumer traces. Registry
# SQL preparation below adds exact static edges without asserting reachability.
GROUPS = {
    "identity-and-domain-content": {
        "tables": "database_identity repositories service_instances sources repository_bindings repository_endpoints source_repositories identity_relations identity_relation_cancellations documents change_requests review_threads text_bodies stored_bytes git_objects contents content_digests blob_content_map",
        "classification": "Retain as final domain content",
        "responsibility": "Independent identities, natural keys, exact text/Git/content and typed relationships; physical/logical representation may change",
        "replacement": "Preserve accepted identity/content contracts; migrate authored references and affected proof consumers before removing any legacy column",
        "decisions": ["P2-Q09", "P2-Q11"],
        "trace": "workstreams/fields.md",
        "producer": "Store registration/content writers; CurrentResources; Git importer; ApiFacts documents; identity service",
        "consumer": "ordinary current/domain queries, search, typed Exchange, CAS and maintenance",
        "failure": "Loss of identity, content, natural parent or independent registration invariants",
    },
    "historical-domain": {
        "tables": "change_request_observations document_observations change_request_events review_thread_observations repository_inventory_observations repository_name_observations code_observations code_commits code_file_changes code_listings code_acquisitions snapshots ref_observations commits commit_parents tree_entries tag_objects root_manifests root_manifest_entries git_text_facts",
        "classification": "Replace",
        "responsibility": "Retain domain observations/text/relations/targets/decoding; replace fetch/result publication ownership and opaque projections",
        "replacement": "Typed domain publication/fields, approved lifecycle and family-specific conflict/selection predicates",
        "decisions": [
            "P2-Q01",
            "P2-Q02",
            "P2-Q03",
            "P2-Q04",
            "P2-Q06",
            "P2-Q08",
            "P2-Q09",
            "P2-Q10",
        ],
        "trace": "workstreams/publication.md",
        "producer": "ApiFacts ensure_pr/document/event/thread/code; CollectionService._publish_inventory; Git importer/parsing",
        "consumer": "ParserModel publication/selection, eligible/current views, PR/Git queries and Graph proof/export/admit",
        "failure": "Direct result/fetch FKs fail; removing guards admits incomplete or wrong-owner outputs; legitimate domain content disappears",
    },
    "parser-authority": {
        "tables": "parser_profiles parser_profile_capabilities parser_profile_verifications parser_profile_verification_invalidations local_parser_profile_verification_trust parser_profile_selection_scopes parser_profile_selection_decisions parser_profile_selection_predecessors parser_profile_selection_publications parser_profile_selection_staging fact_selection_scopes fact_selection_decisions fact_selection_predecessors fact_selection_publications fact_selection_staging",
        "classification": "Remove after dependency migration",
        "responsibility": "Historical decoder settings, sealed-result eligibility and unresolved domain disputes must migrate; profile/certificate/DAG authority is retired target",
        "replacement": "Actual module/version/decoder evidence, domain validity/seals and explicitly approved candidate/selection rules",
        "decisions": [
            "P2-Q01",
            "P2-Q02",
            "P2-Q03",
            "P2-Q04",
            "P2-Q08",
            "P2-Q09",
            "P2-Q10",
        ],
        "trace": "workstreams/publication.md",
        "producer": "ParserModel/profile administration and historical acquisition/parser services",
        "consumer": "eligible/current views, historical PR/Git readers, Git decoding/search, Graph resolution blocks",
        "failure": "Historical facts become ineligible or lose necessary decoder/ownership/conflict guarantees",
    },
    "domain-publication": {
        "tables": "parsed_results parsed_result_inputs parsed_result_publications git_acquisitions git_acquisition_publications acquisition_roots repository_object_sources root_origins",
        "classification": "Replace",
        "responsibility": "Typed domain/Git ownership, exact input/output/root/object membership and atomic immutable publication, distinct from parser authority",
        "replacement": "Independent repository/Source domain bundles and typed code/Git dependency/root memberships; do not rename universal parser-result",
        "decisions": ["P2-Q03", "P2-Q04", "P2-Q08", "P2-Q10"],
        "trace": "workstreams/publication.md",
        "producer": "ApiFacts.result/ownership/publish, Source discovery, ParserModel and Git importer",
        "consumer": "direct historical FKs, publications/views, query/search, Graph exact closure and code proof",
        "failure": "Unowned, incomplete or changed output becomes eligible, or legitimate historical/Git facts vanish",
    },
    "api-original": {
        "tables": "fetch_occurrences source_input_observations",
        "classification": "Remove after dependency migration",
        "responsibility": "Current implementation binds admitted historical observation, source/input owner, page sequence and restart/cache anchors",
        "replacement": "Normalized domain facts/member/terminal/child/target evidence and separate operational continuation/cache; no mandatory original",
        "decisions": [
            "P2-Q03",
            "P2-Q04",
            "P2-Q05",
            "P2-Q06",
            "P2-Q07",
            "P2-Q09",
            "P2-Q10",
            "P2-Q12",
        ],
        "trace": "workstreams/acquisition.md",
        "producer": "ApiFacts.page/source_input and accepted historical GitHub acquisition",
        "consumer": "historical fact/result FKs, Graph proof, 304 cache origin, root resume and saved code target reads",
        "failure": "Publication breaks, completeness/304 becomes false, committed root restart loses real targets/clocks",
    },
    "collections-and-proof": {
        "tables": "fetch_collections collection_memberships completion_markers incremental_scans inventory_observations",
        "classification": "Replace",
        "responsibility": "Domain scoped enumeration, actual max-time partial/complete evidence, inherited baseline and Source discovery scope",
        "replacement": "Chosen typed collection observations/members/terminal/child seals plus preserved accepted Coverage derivation",
        "decisions": ["P2-Q03", "P2-Q04", "P2-Q05", "P2-Q06", "P2-Q10", "P2-Q12"],
        "trace": "workstreams/completeness.md",
        "producer": "ApiFacts.begin/finish/partial, collector incremental/root/list and CollectionService discovery",
        "consumer": "Coverage admission/current queries, restart/watermark and Graph aggregate/proof requirements",
        "failure": "False complete from valid subset, fallback to old complete, forgotten nested requirements or inherited baseline",
    },
    "accepted-current-and-coverage": {
        "tables": "issue_resources review_resources coverage_scopes coverage_claims current_collection_pages",
        "classification": "Retain as final domain content",
        "responsibility": "Accepted latest current state/field evidence/capture/conflicts and five-column maximum-time Coverage; current immutable receipt responsibility",
        "replacement": "Keep accepted semantics; closed field projection and cursor/physical layout remain pending rather than silently deleting receipts",
        "decisions": ["P2-Q05", "P2-Q06", "P2-Q09", "P2-Q10", "P2-Q12"],
        "trace": "workstreams/completeness.md",
        "producer": "CurrentResources, CurrentCollectionProof, ApiFacts.current_resource/current_page and admit_claim",
        "consumer": "ordinary Issue/review readers, current Coverage and Graph current-resource/receipt dependency validation",
        "failure": "Lost per-field origin, transfer proof, receiver-local checks, current resources, latest partial/conflict or past receipt",
    },
    "shared-cas": {
        "tables": "payloads git_object_payloads unresolved_payloads payload_quarantine payload_admission_staging",
        "classification": "Replace",
        "responsibility": "Required domain logical representation/physical diagnoses, genuine Git rejected content, exact byte/OID verification and CAS-41",
        "replacement": "Remove decoded API proof roles only after closure migration; preserve shared digest/domain integrity and quarantine count",
        "decisions": ["P2-Q04", "P2-Q05", "P2-Q10", "P2-Q11"],
        "trace": "workstreams/exchange.md",
        "producer": "payload/CAS adapters, Git importer, accepted historical ApiFacts and corruption diagnosis",
        "consumer": "typed Git/domain refs, Graph required original/domain bytes, full scan, backup/restore and explicit Git repair",
        "failure": "Shared genuine Git content can evade corruption checks or disappear; active physical quarantine is misreported",
    },
    "exchange-operational": {
        "tables": "exchange_admissions exchange_staging exchange_local_identities exchange_source_provenance exchange_blocked_results exchange_selection_blocks exchange_blocked_coverage_claims identity_relation_staging",
        "classification": "Replace",
        "responsibility": "Portable identity mapping, exact normalized dependency staging, sender definition provenance and real conflict barriers",
        "replacement": "Approved normalized wire/admission/promotion/blocked domain eligibility; no original-only root or selected-profile authority",
        "decisions": ["P2-Q04", "P2-Q05", "P2-Q06", "P2-Q08", "P2-Q10"],
        "trace": "workstreams/exchange.md",
        "producer": "Graph.export/receive/_admit/_promote/refresh_resolution_blocks and identity service",
        "consumer": "portable record encoders, late arrival/promotion, current/eligible views and receiver completeness",
        "failure": "Missing dependencies become false acceptance, conflicts vanish or sender hints authorize raw originals",
    },
    "operations-and-derived-storage": {
        "tables": "resume_scopes resume_cursors collection_progress code_listing_progress acquisition_progress validators jobs job_attempts cache_locators content_locations active_cache_entries cache_leases space_reservations preservation_obligations search_documents index_generations index_membership",
        "classification": "Retain only while another decision is pending",
        "responsibility": "Operational scope/fence/restart/cache/job and derived search/preservation responsibilities; not mandatory transport evidence in final domain",
        "replacement": "Separate chosen operational state/checkpoint lifetime and rebuildable domain readers; retain actual current consumers until migration",
        "decisions": ["P2-Q06", "P2-Q07", "P2-Q08", "P2-Q09", "P2-Q11", "P2-Q12"],
        "trace": "workstreams/acquisition.md",
        "producer": "collection/job/cache/index/preservation services and SQLite Store",
        "consumer": "resume/fenced acquisition, plan/cancellation, conditional cache, content availability and rebuildable search",
        "failure": "Restart/watermark/fencing, frozen job intent, retention obligations or existing query/search availability breaks",
    },
}


def generate():
    inventory = json.loads((DIRECTORY / "dependency-inventory.json").read_text())
    raw = gzip.decompress((ROOT / inventory["source"]["artifact"]).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == inventory["source"]["uncompressed_sha256"]
    source = json.loads(raw)
    tables = inventory["schema"]["tables"]
    product = {table for table, meta in tables.items() if meta["product"]}
    definitions = {}
    for group, definition in GROUPS.items():
        for table in definition["tables"].split():
            assert table not in definitions, table
            definitions[table] = (group, definition)
    assert definitions.keys() == product, {
        "unmapped": sorted(product - definitions.keys()),
        "unknown": sorted(definitions.keys() - product),
    }
    static = defaultdict(lambda: {"producers": set(), "consumers": set()})
    for site in source["sql_sites"]:
        statement = source["sql_statements"][site["statement"]]
        if not site["caller"].startswith("src/"):
            continue
        for access in statement["preparation"].get("accesses", []):
            if access["object"] in product:
                target = "consumers" if access["operation"] == "read" else "producers"
                static[access["object"]][target].add(site["caller"])
    disposition = {}
    for table in sorted(product):
        group, definition = definitions[table]
        disposition[table] = {k: v for k, v in definition.items() if k != "tables"}
        disposition[table].update(
            group=group,
            native_parents=tables[table]["foreign_keys"],
            native_children=sorted(
                child
                for child, meta in tables.items()
                if any(fk["parent"] == table for fk in meta["foreign_keys"])
            ),
            static_prepared_sql={k: sorted(v) for k, v in static[table].items()},
            static_edge_limit="Compilation/static evidence; live chains and existing/missing tests are hand-reviewed in trace document",
        )
    objects = {}
    for name, obj in inventory["schema"]["objects"].items():
        if obj["type"] == "table":
            continue
        owner = disposition.get(obj["owner"])
        if owner:
            classification = owner["classification"]
            reason = "Owner responsibility survives or migrates with it; generated guards/FK indexes are regenerated after vocabulary/owner change"
        else:
            classification = "Replace"
            reason = "View/derived SQL must migrate exact domain eligibility/selection/proof predicates; no unconditional DROP"
        if name == "current_coverage":
            classification = "Retain as final domain content"
            reason = "Accepted exact maximum-time candidate-set derivation; joins/proof barriers may require layout regeneration"
        objects[name] = {
            "type": obj["type"],
            "owner": obj["owner"],
            "classification": classification,
            "reason": reason,
            "sql_sha256": obj["sql_sha256"],
        }
    return {
        "status": "Proposed/Pending Owner Decision; conditional migration map, not a DROP list",
        "baseline_main": "20e0f8d78b77c6c8d37826fd6d639819631e166b",
        "ddl_sha256": inventory["schema"]["ddl_sha256"],
        "tables": disposition,
        "dependent_objects": objects,
        "expected_effects": "Domain field normalization reduces duplicated provider objects; exact normalized proof costs O(members+fragments+children); production bounds are measured separately, final storage depends on approved lifecycles",
        "test_trace": "Each linked workstream lists existing regression paths, executed characterization and missing replacement tests; static edges never prove runtime liveness",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = DIRECTORY / "schema-disposition.json"
    result = json.dumps(generate(), indent=2, sort_keys=True) + "\n"
    if args.check:
        assert target.read_text() == result, "Schema disposition artifact stale"
    else:
        target.write_text(result)
    print(
        json.dumps(
            {
                "product_tables": len(json.loads(result)["tables"]),
                "outcome": "passed",
                "check": args.check,
            }
        )
    )


if __name__ == "__main__":
    main()
