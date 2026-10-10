"""Direct Git context and explicit decoder-candidate reads."""

from __future__ import annotations

import json

from repo_catalog.domain.models import CatalogError


def decoder_settings(store, decoder_key):
    """Read a concrete candidate's settings without creating parser authority."""
    fields = "parser_module,parser_version,text_encoding,metadata_encoding,metadata_errors,max_text_blob_bytes"
    if decoder_key is None:
        return {"metadata_encoding": "utf-8", "metadata_errors": "backslashreplace"}
    settings = {
        tuple(row)
        for row in store.all(
            f"SELECT {fields} FROM git_commit_facts WHERE decoder_key=? "
            f"UNION SELECT {fields} FROM git_text_facts WHERE decoder_key=? "
            f"UNION SELECT {fields} FROM git_name_facts WHERE decoder_key=?",
            (decoder_key, decoder_key, decoder_key),
        )
    }
    if len(settings) != 1:
        raise CatalogError(
            "PARSER_DECODER", "Explicit Git decoder is missing or inconsistent"
        )
    return dict(zip(fields.split(","), settings.pop()))


def decoded_name(store, tree_id, raw_name, *, decoder_key=None):
    candidates = [
        dict(row)
        for row in store.all(
            "SELECT * FROM git_name_facts WHERE tree_git_object_id=? AND raw_name=?",
            (tree_id, raw_name),
        )
    ]
    selected = (
        [row for row in candidates if row["decoder_key"] == decoder_key]
        if decoder_key is not None
        else candidates
    )
    values = {row["decoded_name"] for row in selected}
    return {
        "decoded_name": next(iter(values)) if len(values) == 1 else None,
        "decoder_conflict": len(values) > 1,
        "candidates": candidates,
    }


def decoded_fact(store, object_id, object_type, *, decoder_key=None):
    """Return a value only when explicit choice or agreeing candidates permits it.

    Different decoder outputs remain visible. Module/version, arrival order and
    UUID order never decide a competing interpretation.
    """
    table, outputs = {
        "commit": ("git_commit_facts", ("message_text", "metadata")),
        "blob": ("git_text_facts", ("content_id", "text_state", "raw_text")),
    }[object_type]
    candidates = [
        dict(row)
        for row in store.all(
            f"SELECT f.* FROM {table} f JOIN available_git_objects g USING(git_object_id) WHERE f.git_object_id=?",
            (object_id,),
        )
    ]
    selected = (
        [row for row in candidates if row["decoder_key"] == decoder_key]
        if decoder_key is not None
        else candidates
    )
    groups = {
        tuple(
            json.dumps(json.loads(row[field]), sort_keys=True)
            if field == "metadata"
            else row[field]
            for field in outputs
        )
        for row in selected
    }
    conflict = len(groups) > 1
    fact = None
    if selected and not conflict:
        if len(selected) == 1:
            fact = selected[0]
        else:
            # Agreeing values retain every actual decoder attribution.
            fact = {
                "git_object_id": object_id,
                **{key: selected[0][key] for key in outputs},
            }
            fact["decoder_evidence"] = [
                {key: value for key, value in row.items() if key not in outputs}
                for row in selected
            ]
    return {
        "fact": fact,
        "decoder_conflict": conflict,
        "decoder_missing": decoder_key is not None and not selected,
        "candidates": candidates,
    }


def object_context(store, context, object_id, object_type):
    owner = context["repository_uuidv4"]
    acquisition = context.get("git_acquisition_id")
    clauses, parameters = (
        ["r.repository_uuidv4=?", "r.git_object_id=?"],
        [owner, object_id],
    )
    if acquisition is not None and context.get("historical"):
        clauses.append("r.git_acquisition_id=?")
        parameters.append(acquisition)
    present = store.one(
        "SELECT 1 FROM repository_object_sources r JOIN available_git_objects g USING(git_object_id) WHERE "
        + " AND ".join(clauses)
        + " AND g.type=? LIMIT 1",
        (*parameters, object_type),
    )
    result = {**context, "object_available": present is not None}
    if present is not None and object_type in ("commit", "blob"):
        decoded = decoded_fact(
            store, object_id, object_type, decoder_key=context.get("decoder_key")
        )
        result["decoder_conflict"] = decoded["decoder_conflict"]
        result["decoder_candidates"] = [
            {
                key: row[key]
                for key in ("decoder_key", "parser_module", "parser_version")
            }
            for row in decoded["candidates"]
        ]
    return result


def current_content_facts(
    store, content_id, repository_uuids=None, *, decoder_key=None
):
    """Maintenance/search lookup of current capture text without profile views."""
    clauses, parameters = ["m.content_id=?"], [content_id]
    if repository_uuids is not None:
        if not repository_uuids:
            return []
        clauses.append(
            "s.repository_uuidv4 IN (" + ",".join("?" for _ in repository_uuids) + ")"
        )
        parameters.extend(repository_uuids)
    objects = store.all(
        "SELECT DISTINCT s.repository_uuidv4,r.git_object_id FROM current_snapshots s "
        "JOIN repository_object_sources r ON r.git_acquisition_id=s.git_acquisition_id "
        "JOIN blob_content_map m USING(git_object_id) WHERE " + " AND ".join(clauses),
        tuple(parameters),
    )
    facts = []
    for obj in objects:
        result = decoded_fact(
            store, obj["git_object_id"], "blob", decoder_key=decoder_key
        )
        if result["fact"] is not None:
            facts.append(
                {**result["fact"], "repository_uuidv4": obj["repository_uuidv4"]}
            )
        elif result["decoder_conflict"]:
            facts.append(
                {
                    "git_object_id": obj["git_object_id"],
                    "repository_uuidv4": obj["repository_uuidv4"],
                    "content_id": content_id,
                    "text_state": "decoder_conflict",
                    "raw_text": None,
                    "decoder_candidates": result["candidates"],
                }
            )
    return facts
