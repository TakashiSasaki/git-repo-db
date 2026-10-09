"""Explicit synthetic parser provenance for structural contract fixtures."""

import uuid

from repo_catalog.adapters.sqlite.parser_model import (
    BUILTIN_CAPABILITIES,
    ParserModel,
    canonical,
)


def repository_uuid(label):
    return {
        "a": "00000000-0000-4000-8000-000000000301",
        "b": "00000000-0000-4000-8000-000000000302",
        "new": "00000000-0000-4000-8000-000000000303",
    }.get(label, label)


def register_test_profile(db):
    definition = {
        "implementation": {"fixture": "structural-contract-v1"},
        "settings": {},
        "output_schema": {},
        "capabilities": BUILTIN_CAPABILITIES,
    }
    model = ParserModel(db)
    existing = db.execute(
        "SELECT parser_profile_uuidv4 FROM parser_profiles WHERE definition_json=?",
        (canonical(definition),),
    ).fetchone()
    if existing:
        return existing[0]
    profile = model.register_profile(definition)
    verification = model.verify_profile(
        profile,
        criteria={"fixture": "synthetic"},
        evidence={
            "definition": definition,
            "capabilities": [
                {**c, "outcome": "passed", "checks": ["synthetic fixture"]}
                for c in definition["capabilities"]
            ],
        },
    )
    model.trust_verification(verification, rationale={"fixture": "synthetic"})
    return profile


def new_result(db, repo, *, inputs=None):
    repo = repository_uuid(repo)
    if inputs is None:
        acquisition = db.execute(
            "SELECT git_acquisition_id FROM git_acquisitions WHERE repository_uuidv4=?",
            (repo,),
        ).fetchone()
        if acquisition is None:
            uid = str(uuid.uuid4())
            db.execute(
                "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,request) VALUES(?,?,'git','{}')",
                (uid, repo),
            )
        else:
            uid = acquisition[0]
        inputs = [{"git_acquisition_id": uid}]
    return ParserModel(db).create_result(
        register_test_profile(db), repository_uuidv4=repo, inputs=inputs
    )


def enrich(db, table, values):
    values = dict(values)
    if "repository_uuidv4" in values:
        values["repository_uuidv4"] = repository_uuid(values["repository_uuidv4"])
    if table in ("documents", "review_threads", "reviews", "review_comments"):
        for key in (
            "deleted",
            "author",
            "url",
            "metadata",
            "payload",
            "observed_at_us",
            "review_thread_provider_resource_id",
        ):
            values.pop(key, None)
    if table == "fetch_occurrences":
        values.setdefault("fetch_occurrence_uuidv4", str(uuid.uuid4()))
        values.setdefault(
            "repository_uuidv4",
            db.execute(
                "SELECT repository_uuidv4 FROM fetch_collections WHERE fetch_collection_id=?",
                (values["fetch_collection_id"],),
            ).fetchone()[0],
        )
    fact_uuids = {
        "change_request_observations": "change_request_observation_uuidv4",
        "document_observations": "document_observation_uuidv4",
        "code_observations": "code_observation_uuidv4",
        "change_request_events": "change_request_event_uuidv4",
    }
    if table in fact_uuids:
        values.setdefault(fact_uuids[table], str(uuid.uuid4()))
    if table in (
        *fact_uuids,
        "code_commits",
        "code_file_changes",
        "snapshots",
        "ref_observations",
    ):
        repo = values.get("repository_uuidv4")
        if repo is None and "change_request_id" in values:
            repo = db.execute(
                "SELECT repository_uuidv4 FROM change_requests WHERE change_request_id=?",
                (values["change_request_id"],),
            ).fetchone()[0]
        if repo is None and "code_listing_id" in values:
            repo = db.execute(
                "SELECT r.repository_uuidv4 FROM code_listings l JOIN change_requests r USING(change_request_id) WHERE l.code_listing_id=?",
                (values["code_listing_id"],),
            ).fetchone()[0]
        if table == "ref_observations":
            result, repo = db.execute(
                "SELECT parsed_result_uuidv4,repository_uuidv4 FROM snapshots WHERE snapshot_id=?",
                (values["snapshot_id"],),
            ).fetchone()
            values.setdefault("parsed_result_uuidv4", result)
        values.setdefault("repository_uuidv4", repo)
        if "parsed_result_uuidv4" not in values:
            occurrence = values.get(
                "fetch_occurrence_id", values.get("origin_fetch_occurrence_id")
            )
            inputs = None
            if occurrence:
                row = db.execute(
                    "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences WHERE fetch_occurrence_id=?",
                    (occurrence,),
                ).fetchone()
                if row:
                    inputs = [{"fetch_occurrence_uuidv4": row[0]}]
            values["parsed_result_uuidv4"] = new_result(db, repo, inputs=inputs)
    return values
