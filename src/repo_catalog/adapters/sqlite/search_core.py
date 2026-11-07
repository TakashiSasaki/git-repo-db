"""Git-authority Search extraction, loaded only for Git projections."""

from __future__ import annotations

import json

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.production_search import BoundedDocuments
from repo_catalog.domain.p1_core import OID, GitObservation, Provenance
from repo_catalog.domain.query_contracts import canonical_json


def extract_git_metadata_documents(
    core: GitCore,
) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    """Extract searchable `git_metadata` documents and summaries from a pinned `GitCore`.

    Indexes commit/tag messages, author/committer/tagger identities, tag names,
    ref observations, and decoded tree entry names. Strictly excludes ordinary
    file blobs (`type == 'blob'`).
    """
    documents: dict[str, str] = BoundedDocuments()
    summaries: dict[str, dict[str, object]] = {}

    # 1. Inspect git_objects and their scalar/relation claims
    obj_rows = core.sql(
        "SELECT object_format,object_oid FROM git_objects ORDER BY object_format,object_oid"
    )
    for row in obj_rows:
        object_oid = OID(row[0], row[1])
        type_proj = core.scalar(object_oid, "type")
        known_types = {
            alt["value"][1]
            for alt in type_proj.alternatives
            if isinstance(alt["value"], list)
            and len(alt["value"]) == 2
            and alt["value"][0] == "known"
        }
        canonical_type = (
            type_proj.canonical[1]
            if isinstance(type_proj.canonical, list)
            and len(type_proj.canonical) == 2
            and type_proj.canonical[0] == "known"
            else None
        )
        # Strictly exclude ordinary file blobs
        if canonical_type == "blob" or (known_types == {"blob"}):
            continue

        # Scalar text fields for commit/tag/metadata
        for field in (
            "message",
            "author",
            "author_name",
            "author_email",
            "committer",
            "committer_name",
            "committer_email",
            "tag_name",
            "tagger",
            "decoded_name",
        ):
            proj = core.scalar(object_oid, field)
            for alt in proj.alternatives:
                val = alt["value"]
                if (
                    isinstance(val, list)
                    and len(val) == 2
                    and val[0] == "known"
                    and isinstance(val[1], str)
                    and val[1]
                ):
                    prov_json = canonical_json(alt["provenance"])
                    doc_key = canonical_json(
                        [
                            "scalar",
                            object_oid.object_format,
                            object_oid.object_oid,
                            field,
                            prov_json,
                        ]
                    )
                    documents[doc_key] = val[1]
                    summaries[doc_key] = {
                        "checked": alt["checked"],
                        "field": field,
                        "object_oid": object_oid.object_oid,
                        "kind": "scalar",
                        "native_type": canonical_type,
                        "object_format": object_oid.object_format,
                        "provenance": alt["provenance"],
                    }

        # Tree entry names (decoded from hex)
        tree_proj = core.relations(object_oid, "tree_entries")
        for alt in tree_proj.alternatives:
            prov_json = canonical_json(alt["provenance"])
            for member in alt["membership"]:
                coord, target_fmt, target_object_oid = member
                mode, name_hex = coord[0], coord[1]
                decoded_name = bytes.fromhex(name_hex).decode(
                    "utf-8", "backslashreplace"
                )
                doc_key = canonical_json(
                    [
                        "tree_entry",
                        object_oid.object_format,
                        object_oid.object_oid,
                        name_hex,
                        target_object_oid,
                        prov_json,
                    ]
                )
                documents[doc_key] = decoded_name
                summaries[doc_key] = {
                    "checked": alt["checked"],
                    "entry_mode": mode,
                    "entry_name": decoded_name,
                    "object_oid": object_oid.object_oid,
                    "kind": "tree_entry",
                    "object_format": object_oid.object_format,
                    "target_object_oid": [target_fmt, target_object_oid],
                }

    # 2. Ref observations
    obs_rows = core.sql(
        "SELECT capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,kind,scope,value,provenance "
        "FROM git_observations WHERE kind='ref' "
        "ORDER BY capture_origin_uuidv4,capture_uuidv4,scope,provenance"
    )
    for row in obs_rows:
        observation = GitObservation(
            row[0],
            row[1],
            row[2],
            row[3],
            tuple(json.loads(row[4])),
            json.loads(row[5]),
            Provenance(*json.loads(row[6])),
        )
        value = observation.value
        ref_name = value.get("ref")
        if isinstance(ref_name, str) and ref_name:
            doc_key = canonical_json(
                [
                    "ref_observation",
                    row[0],
                    row[1],
                    ref_name,
                    row[6],
                ]
            )
            target = value.get("target")
            searchable = (
                f"{ref_name} {target[1]}"
                if isinstance(target, list) and len(target) == 2
                else ref_name
            )
            documents[doc_key] = searchable
            summaries[doc_key] = {
                "capture_origin_uuidv4": row[0],
                "capture_uuidv4": row[1],
                "kind": "ref_observation",
                "observed_at_us": value.get("observed_at_us"),
                "ref": ref_name,
                "target": target,
            }

    return documents, summaries
