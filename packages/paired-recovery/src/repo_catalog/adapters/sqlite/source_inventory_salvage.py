"""Typed Source inventory/proof recovery; no donor SQL or completeness flags trusted."""

from __future__ import annotations

import json
import sqlite3

from repo_catalog.adapters.sqlite.context_rows import ROW_TYPES
from repo_catalog.adapters.sqlite.ref_salvage import _validate_source_shape
from repo_catalog.domain.context_registration import registration_json
from repo_catalog.domain.p1_context import CoverageScope, ResourceKey
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.production_context import SourceInventory
from repo_catalog.domain.resource_identification import ResourceIdentification
from repo_catalog.domain.shared_values import CoreFailure, encode
from repo_catalog.domain.source_inventory_scope import validate_source_inventory_scope

SOURCE_CANDIDATES = {
    "source_inventory": "source_inventory_evidence",
    "source_inventory_proof": "source_coverage_proofs",
}


def _charge(work, unit, amount):
    work.require(unit, amount)
    work.charge(unit, amount)


def _row(table, value, work):
    if type(value) is not dict:
        raise ValueError("exact typed Source row required")
    columns, values = ROW_TYPES[table].insert_bindings(value)
    if columns != ROW_TYPES[table].WRITE_COLUMNS:
        raise ValueError("complete Source row required")
    _charge(work, "metadata_units", len(columns))
    _charge(
        work,
        "input_bytes",
        sum(
            len(item.encode("utf-8")) if type(item) is str else 8
            for item in values
            if item is not None
        ),
    )
    return dict(zip(columns, values, strict=True))


def observation_from_row(row, work):
    value = _row("source_inventory_evidence", row, work)
    if value["terminal"] not in (0, 1):
        raise ValueError("typed Source terminal required")
    members = json.loads(value["members_json"])
    resources = json.loads(value["provider_repositories_json"])
    if type(members) is not list or type(resources) is not list:
        raise ValueError("typed Source membership arrays required")
    _charge(work, "metadata_units", len(members) + len(resources))
    observation = SourceInventory(
        value["source_registration_uuidv4"],
        value["scope_json"],
        value["observed_at_us"],
        value["coverage_state"],
        bool(value["terminal"]),
        tuple(members),
        value["provenance_json"],
        provider_repositories=tuple(ResourceKey(*key) for key in resources),
    )
    if observation.values != tuple(value.values()):
        raise ValueError("Source inventory original columns are noncanonical")
    return observation


def _read(conn, table, keys, work, max_bytes):
    # Reject views/virtual tables; project only actual stored write columns.
    work.require("metadata_units", 1)
    try:
        work.require("input_bytes", 16)
    except BaseException:
        work.abandon("metadata_units")
        raise
    try:
        shape = conn.execute(
            "SELECT type='table',sql LIKE 'CREATE TABLE%' FROM sqlite_schema WHERE name=?",
            (table,),
        ).fetchone()
    except BaseException:
        work.abandon("metadata_units")
        work.abandon("input_bytes")
        raise
    work.charge("metadata_units", 1)
    work.charge("input_bytes", 16 if shape is not None else 0)
    if shape is None or shape[0] != 1 or shape[1] != 1:
        raise ValueError("plain stored Source dependency table required")
    names = ROW_TYPES[table].WRITE_COLUMNS
    _validate_source_shape(conn, table, work, required=names, allow_generated=True)
    where = " AND ".join('"' + key + '" IS ?' for key in keys)
    size = "+".join(
        f'CASE WHEN "{name}" IS NULL THEN 0 WHEN typeof("{name}") IN (\'text\',\'blob\') THEN octet_length("{name}") ELSE 8 END'
        for name in names
    )
    work.require("metadata_units", 3)
    try:
        measured = conn.execute(
            f'SELECT {size} FROM "{table}" NOT INDEXED WHERE {where} LIMIT 2',
            tuple(keys.values()),
        ).fetchall()
    except BaseException:
        work.abandon("metadata_units")
        raise
    work.charge("metadata_units", len(measured) + 1)
    if (
        len(measured) != 1
        or type(measured[0][0]) is not int
        or measured[0][0] > max_bytes
    ):
        raise ValueError("Source dependency unavailable or exceeds finite allowance")
    amount = measured[0][0]
    work.require("input_bytes", amount)
    try:
        row = conn.execute(
            f'SELECT {",".join(names)} FROM "{table}" NOT INDEXED WHERE {where} LIMIT 1',
            tuple(keys.values()),
        ).fetchone()
    except BaseException:
        work.abandon("input_bytes")
        raise
    work.charge("input_bytes", amount)
    if row is None:
        raise ValueError("Source dependency changed during extraction")
    return dict(zip(names, row, strict=True))


def source_candidate(conn, table, row, work, *, max_bytes, max_members):
    if table not in SOURCE_CANDIDATES.values():
        return None
    kind = (
        "source_inventory"
        if table == "source_inventory_evidence"
        else "source_inventory_proof"
    )
    ident = str(row.get("source_registration_uuidv4"))
    try:
        if kind == "source_inventory_proof":
            proof = _row(table, row, work)
            inventory_keys = {
                name: proof[
                    {
                        "observed_at_us": "inventory_observed_at_us",
                        "coverage_state": "inventory_state",
                    }.get(name, name)
                ]
                for name in ROW_TYPES["source_inventory_evidence"].WRITE_COLUMNS
            }
            inventory = _read(
                conn, "source_inventory_evidence", inventory_keys, work, max_bytes
            )
        else:
            inventory = row
        observation = observation_from_row(inventory, work)
        if (
            len(observation.repositories) + len(observation.provider_repositories)
            > max_members
        ):
            raise ValueError("finite Source membership limit")
        source = _read(
            conn,
            "sources",
            {"source_registration_uuidv4": observation.source_registration_uuidv4},
            work,
            max_bytes,
        )
        provider = _read(
            conn,
            "providers",
            {"service_instance_uuidv4": source["service_instance_uuidv4"]},
            work,
            max_bytes,
        )
        repositories = [
            _read(
                conn,
                "repository_context",
                {"repository_uuidv4": repository},
                work,
                max_bytes,
            )
            for repository in observation.repositories
        ]
        associations = [
            _read(
                conn,
                "source_repositories",
                {
                    "source_registration_uuidv4": observation.source_registration_uuidv4,
                    "repository_uuidv4": repository,
                },
                work,
                max_bytes,
            )
            for repository in observation.repositories
        ]
        resources = [
            _read(
                conn,
                "resources",
                dict(
                    zip(
                        (
                            "service_instance_uuidv4",
                            "resource_kind",
                            "provider_resource_id",
                        ),
                        resource.coordinates(),
                        strict=True,
                    )
                ),
                work,
                max_bytes,
            )
            for resource in observation.provider_repositories
        ]
        packet = {
            "inventory": inventory,
            "source_registration": source,
            "provider": provider,
            "repositories": repositories,
            "source_repositories": associations,
            "provider_repositories": resources,
        }
        if kind == "source_inventory_proof":
            packet["claim"] = _read(
                conn,
                "coverage_claims",
                {
                    name: proof[name]
                    for name in (
                        "owner_kind",
                        "owner_coordinates_json",
                        "observed_at_us",
                        "coverage_state",
                    )
                },
                work,
                max_bytes,
            )
            packet["proof"] = proof
            packet["scope"] = _read(
                conn,
                "coverage_scopes",
                {
                    name: proof[name]
                    for name in ("owner_kind", "owner_coordinates_json")
                },
                work,
                max_bytes,
            )
        if len(encode(packet)) > max_bytes:
            raise ValueError("finite Source unit payload limit")
        return kind, ident, packet, None
    except CoreFailure as error:
        if error.code in ("BUDGET", "QUERY_BUDGET"):
            raise
        return kind, ident, {"unadmitted_original": row}, str(error)
    except (ValueError, TypeError, KeyError, RecursionError, sqlite3.Error) as error:
        return kind, ident, {"unadmitted_original": row}, str(error)


def decode_source_candidate(kind, packet, work):
    expected = {
        "inventory",
        "source_registration",
        "provider",
        "repositories",
        "source_repositories",
        "provider_repositories",
    } | ({"claim", "proof", "scope"} if kind == "source_inventory_proof" else set())
    if (
        kind not in SOURCE_CANDIDATES
        or type(packet) is not dict
        or set(packet) != expected
    ):
        raise ValueError("exact typed Source recovery unit required")
    observation = observation_from_row(packet["inventory"], work)
    source, provider = (
        _row("sources", packet["source_registration"], work),
        _row("providers", packet["provider"], work),
    )
    if (
        source["source_registration_uuidv4"] != observation.source_registration_uuidv4
        or source["service_instance_uuidv4"] != provider["service_instance_uuidv4"]
    ):
        raise ValueError("Source registration/provider identity mismatch")
    validate_source_inventory_scope(
        observation.scope_json,
        observation.source_registration_uuidv4,
        source["service_instance_uuidv4"],
    )
    registration_json("source", source["configuration_json"])
    registration_json("provider", provider["configuration_json"])
    repositories = [
        _row("repository_context", value, work) for value in packet["repositories"]
    ]
    associations = [
        _row("source_repositories", value, work)
        for value in packet["source_repositories"]
    ]
    resources = [
        _row("resources", value, work) for value in packet["provider_repositories"]
    ]
    if {value["repository_uuidv4"] for value in repositories} != set(
        observation.repositories
    ) or len(repositories) != len(observation.repositories):
        raise ValueError("exact original Git membership dependencies required")
    for value in repositories:
        registration_json("repository", value["configuration_json"])
    if len(associations) != len(observation.repositories) or {
        (value["source_registration_uuidv4"], value["repository_uuidv4"])
        for value in associations
    } != {
        (observation.source_registration_uuidv4, repository)
        for repository in observation.repositories
    }:
        raise ValueError("exact original Source membership dependencies required")
    for value in associations:
        registration_json("membership", value["attributes_json"])
    supplied = set()
    for value in resources:
        key = ResourceKey(
            value["service_instance_uuidv4"],
            value["resource_kind"],
            value["provider_resource_id"],
        )
        if (
            key.resource_kind != "repository"
            or key.service_instance_uuidv4 != source["service_instance_uuidv4"]
        ):
            raise ValueError("Source Provider repository namespace mismatch")
        declaration = ResourceIdentification.from_storage(
            key,
            tuple(
                value[name]
                for name in (
                    "identifier_namespace_kind",
                    "identifier_namespace_id",
                    "document_kind",
                    "provider_document_id",
                )
            ),
        )
        if declaration.document_kind is not None:
            raise ValueError("Source Provider repository member must be unscoped")
        supplied.add(key)
    if supplied != set(observation.provider_repositories) or len(resources) != len(
        supplied
    ):
        raise ValueError("exact original Provider repository dependencies required")
    claim = None
    if kind == "source_inventory_proof":
        raw = _row("coverage_claims", packet["claim"], work)
        proof = _row("source_coverage_proofs", packet["proof"], work)
        scope = CoverageScope(
            raw["owner_kind"], tuple(json.loads(raw["owner_coordinates_json"]))
        )
        claim = CoverageClaim(
            scope, raw["observed_at_us"], raw["coverage_state"], raw["details_json"]
        )
        original_scope = _row("coverage_scopes", packet["scope"], work)
        expected_scope = dict.fromkeys(ROW_TYPES["coverage_scopes"].WRITE_COLUMNS)
        expected_scope.update(
            owner_kind=scope.owner_kind,
            owner_coordinates_json=scope.encoded,
            coverage_kind=scope.base_coverage_kind,
            source_registration_uuidv4=observation.source_registration_uuidv4,
            source_scope_json=observation.scope_json,
        )
        if (
            original_scope != expected_scope
            or type(json.loads(observation.scope_json)) is not dict
            or json.loads(observation.scope_json).get("coverage_kind")
            != scope.base_coverage_kind
        ):
            raise ValueError("Source proof original owner scope is mismatched")
        if (
            scope.owner_kind != "source_inventory"
            or tuple(scope.coordinates[:2])
            != (observation.source_registration_uuidv4, observation.scope_json)
            or tuple(proof.values())
            != (
                scope.owner_kind,
                scope.encoded,
                claim.observed_at_us,
                claim.state,
                *observation.values,
            )
        ):
            raise ValueError(
                "Source proof does not bind the exact original inventory/claim"
            )
    return observation, claim, source, provider, repositories, resources, associations


def admit_source_packet(
    directory, kind, packet, connection, authorization, admission, work
):
    """Atomically admit one source-owned typed unit under explicit current leases."""
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.domain.context_admission import DependencySet, dependencies

    observation, claim, source, provider, repositories, resources, associations = (
        decode_source_candidate(kind, packet, work)
    )
    required = dependencies((observation, claim)) | DependencySet(
        sources={source["source_registration_uuidv4"]},
        provider_registrations={provider["service_instance_uuidv4"]},
        repositories=observation.repositories,
        resources=observation.provider_repositories,
        source_repository_pairs={
            (observation.source_registration_uuidv4, repository)
            for repository in observation.repositories
        },
    )
    with Context.owned_transaction(
        connection, directory, authorization=authorization, admission=admission
    ) as context:
        # Own the same service-issued lease through COMMIT, before target lookups.
        # Missing registrations may be created only after complete local policy
        # and selection authorization. Donor identity/provenance grants nothing.
        lease = context._admission_leases.enter_context(
            authorization.authorize(admission, required)
        )
        context._admission_live_leases.append(lease)
        changed = False
        existing = context.db.execute(
            "SELECT provider_kind FROM providers WHERE service_instance_uuidv4=?",
            (provider["service_instance_uuidv4"],),
        ).fetchone()
        if existing is not None and existing[0] != provider["provider_kind"]:
            raise ValueError(
                "permanent Provider identity conflicts with fresh authority"
            )
        if existing is None:
            context.provider(
                provider["service_instance_uuidv4"],
                provider["provider_kind"],
                provider["configuration_json"],
            )
            changed = True
        existing = context.db.execute(
            "SELECT service_instance_uuidv4 FROM sources WHERE source_registration_uuidv4=?",
            (source["source_registration_uuidv4"],),
        ).fetchone()
        if existing is not None and existing[0] != source["service_instance_uuidv4"]:
            raise ValueError("permanent Source identity conflicts with fresh authority")
        if existing is None:
            context.source(
                source["source_registration_uuidv4"],
                source["service_instance_uuidv4"],
                source["configuration_json"],
            )
            changed = True
        for value in repositories:
            if (
                context.db.execute(
                    "SELECT 1 FROM repository_context WHERE repository_uuidv4=?",
                    (value["repository_uuidv4"],),
                ).fetchone()
                is None
            ):
                context.repository(
                    value["repository_uuidv4"], value["configuration_json"]
                )
                changed = True
        for value in associations:
            if (
                context.db.execute(
                    "SELECT 1 FROM source_repositories WHERE source_registration_uuidv4=? AND repository_uuidv4=?",
                    (value["source_registration_uuidv4"], value["repository_uuidv4"]),
                ).fetchone()
                is None
            ):
                context.associate_source(
                    value["source_registration_uuidv4"],
                    value["repository_uuidv4"],
                    value["attributes_json"],
                    ensure_only=True,
                )
                changed = True
        for value in resources:
            key = ResourceKey(
                value["service_instance_uuidv4"],
                value["resource_kind"],
                value["provider_resource_id"],
            )
            declaration = ResourceIdentification.from_storage(
                key,
                tuple(
                    value[name]
                    for name in (
                        "identifier_namespace_kind",
                        "identifier_namespace_id",
                        "document_kind",
                        "provider_document_id",
                    )
                ),
            )
            if (
                context.db.execute(
                    "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                    key.coordinates(),
                ).fetchone()
                is None
            ):
                context.resource(key, identification=declaration)
                changed = True
            elif context.identification(key) != declaration:
                raise ValueError(
                    "Resource identification conflicts with fresh authority"
                )
        result = context.admit_inventory_history(observation, claim)
        return "insert" if changed or result == "insert" else "duplicate"


def validate_stored_source_authority(connection, work, budget):
    """Revalidate current Source originals and exact dependencies, within bounds.

    Historical completeness need not be current. Validation checks enduring
    domain membership/provenance/owner coordinates, never replays temporal
    admission checks or treats a stored terminal flag as its own proof.
    """
    from repo_catalog.adapters.sqlite.core_recovery_validation import (
        RefValidationBudgetError,
    )
    from repo_catalog.adapters.sqlite.recovery_validation import (
        StoredContextInvariantError,
    )

    remaining = budget.max_input_records
    for kind, table in SOURCE_CANDIDATES.items():
        columns = ROW_TYPES[table].WRITE_COLUMNS
        size = "+".join(f'coalesce(octet_length("{name}"),0)' for name in columns)
        projection = ",".join(
            f'CASE WHEN ({size})<=? THEN "{name}" END' for name in columns
        )
        cursor = connection.execute(
            f'SELECT ({size}),{projection} FROM "{table}" NOT INDEXED',
            (budget.max_payload_bytes,) * len(columns),
        )
        try:
            while True:
                work.require("metadata_units", 1)
                try:
                    work.require("input_bytes", budget.max_payload_bytes)
                except BaseException:
                    work.abandon("metadata_units")
                    raise
                try:
                    row = cursor.fetchone()
                except BaseException:
                    work.abandon("metadata_units")
                    work.abandon("input_bytes")
                    raise
                work.charge("metadata_units", int(row is not None))
                work.charge(
                    "input_bytes",
                    0 if row is None else min(row[0], budget.max_payload_bytes),
                )
                if row is None:
                    break
                if remaining <= 0 or row[0] > budget.max_payload_bytes:
                    raise RefValidationBudgetError(
                        "Finite stored Source evidence limit"
                    )
                remaining -= 1
                original = dict(zip(columns, row[1:], strict=True))
                result = source_candidate(
                    connection,
                    table,
                    original,
                    work,
                    max_bytes=budget.max_payload_bytes,
                    max_members=budget.max_input_records,
                )
                if result[3] is not None:
                    raise StoredContextInvariantError(
                        f"Invalid stored Source authority: {result[3]}"
                    )
                decode_source_candidate(kind, result[2], work)
        except CoreFailure as error:
            if error.code in ("BUDGET", "QUERY_BUDGET"):
                raise RefValidationBudgetError(
                    "Finite stored Source validation work limit"
                ) from error
            raise StoredContextInvariantError(
                "Invalid stored Source authority"
            ) from error
        except (ValueError, TypeError, KeyError, IndexError, UnicodeError) as error:
            raise StoredContextInvariantError(
                "Invalid stored Source authority"
            ) from error
        finally:
            cursor.close()
