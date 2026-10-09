"""Admission and explicit selection for immutable parsed results.

All mutating operations use the caller's transaction. UUIDs are portable identity;
JSON manifests fix dependency sets before rows can become visible as current.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from importlib.resources import files

from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _uuid(value=None):
    value = value or str(uuid.uuid4())
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise CatalogError("INVALID_UUID", "Canonical UUIDv4 required") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise CatalogError("INVALID_UUID", "Canonical UUIDv4 required")
    return value


BUILTIN_CAPABILITIES = [
    {"owner_kind": "repository", "fact_kind": kind}
    for kind in (
        "change-request",
        "pr-title",
        "pr-body",
        "issue-comment",
        "review",
        "review-comment",
        "review-thread",
        "events",
        "code",
        "git",
    )
] + [{"owner_kind": "source", "fact_kind": "inventory"}]
BUILTIN_MODULES = (
    "config.py",
    "adapters/sqlite/parser_model.py",
    "adapters/github/persistence.py",
    "adapters/github/collector.py",
    "adapters/git/importer.py",
    "application/parsing_service.py",
    "application/collection_service.py",
    "application/repository_identity.py",
    "adapters/sqlite/identity_relations.py",
    "application/job_plans.py",
    "adapters/github/identity.py",
    "adapters/github/transport.py",
    "adapters/git/runner.py",
    "adapters/sqlite/text_bodies.py",
    "adapters/sqlite/payloads.py",
    "adapters/sqlite/store.py",
    "domain/time.py",
    "domain/document.py",
    "domain/pr_scope.py",
    "domain/payload.py",
    "domain/models.py",
)


def builtin_definition():
    from repo_catalog.adapters.sqlite.schema import DDL_SHA256

    root = files("repo_catalog")
    implementation = {}
    for path in BUILTIN_MODULES:
        resource = root.joinpath(path)
        implementation[path] = hashlib.sha256(resource.read_bytes()).hexdigest()
    return {
        "implementation": implementation,
        "settings": {
            "parser": "repo-catalog-builtin",
            "format": 1,
            "preservation_profile": "catalog-text-v1",
            "text_policy_id": "utf8-literal-v1",
            "max_text_blob_bytes": 8388608,
        },
        "output_schema": {
            "catalog3": 12,
            "facts": "immutable-result-owned",
            "ddl_sha256": DDL_SHA256.hex(),
        },
        "capabilities": BUILTIN_CAPABILITIES,
    }


class ParserModel:
    def __init__(self, connection):
        self.c = connection

    def _row(self, sql, params=()):
        cursor = self.c.execute(sql, params)
        row = cursor.fetchone()
        return (
            None if row is None else dict(zip((c[0] for c in cursor.description), row))
        )

    def _rows(self, sql, params=()):
        cursor = self.c.execute(sql, params)
        keys = [c[0] for c in cursor.description]
        return [dict(zip(keys, row)) for row in cursor]

    def _changed(self):
        self.c.execute(
            "UPDATE database_identity SET publication_seq=publication_seq+1 WHERE singleton=1"
        )

    def register_profile(
        self, definition, *, parser_version="1", profile_version="1", profile_uuid=None
    ):
        ident = _uuid(profile_uuid)
        for field in ("implementation", "settings", "output_schema"):
            if not isinstance(definition.get(field), dict):
                raise CatalogError("PROFILE_DEFINITION", f"{field} must be an object")
        capabilities = definition.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            raise CatalogError("PROFILE_DEFINITION", "At least one capability required")
        pairs = []
        for capability in capabilities:
            if not isinstance(capability, dict) or set(capability) != {
                "owner_kind",
                "fact_kind",
            }:
                raise CatalogError("PROFILE_DEFINITION", "Invalid capability")
            pair = (capability["owner_kind"], capability["fact_kind"])
            if (
                pair[0] not in ("repository", "source")
                or not isinstance(pair[1], str)
                or not pair[1]
            ):
                raise CatalogError("PROFILE_DEFINITION", "Invalid capability")
            pairs.append(pair)
        if len(set(pairs)) != len(pairs):
            raise CatalogError("PROFILE_DEFINITION", "Duplicate capability")
        encoded = canonical(definition)
        old = self._row(
            "SELECT * FROM parser_profiles WHERE parser_profile_uuidv4=?", (ident,)
        )
        if old:
            if (
                old["parser_version"],
                old["profile_version"],
                old["definition_json"],
            ) != (parser_version, profile_version, encoded):
                raise CatalogError(
                    "IMMUTABLE_IDENTITY_CONFLICT", "Profile UUID content differs"
                )
            return ident
        self.c.execute(
            "INSERT INTO parser_profiles VALUES(?,?,?,?)",
            (ident, parser_version, profile_version, encoded),
        )
        self.c.executemany(
            "INSERT INTO parser_profile_capabilities VALUES(?,?,?)",
            [(ident, *pair) for pair in pairs],
        )
        self._changed()
        return ident

    def verify_profile(
        self,
        profile_uuid,
        *,
        outcome="passed",
        criteria,
        evidence,
        verification_uuid=None,
        verified_at_us=None,
    ):
        ident = _uuid(verification_uuid)
        profile = self._row(
            "SELECT definition_json FROM parser_profiles WHERE parser_profile_uuidv4=?",
            (profile_uuid,),
        )
        if profile is None:
            raise CatalogError("PROFILE_MISSING", "Profile not registered")
        definition = json.loads(profile["definition_json"])
        if outcome == "passed":
            required = {
                (c["owner_kind"], c["fact_kind"]) for c in definition["capabilities"]
            }
            supplied = evidence.get("capabilities")
            if evidence.get("definition") != definition or not isinstance(
                supplied, list
            ):
                raise CatalogError(
                    "VERIFICATION_INCOMPLETE",
                    "Exact profile definition and full capability evidence required",
                )
            pairs = [
                (c.get("owner_kind"), c.get("fact_kind"))
                for c in supplied
                if isinstance(c, dict)
            ]
            if (
                len(pairs) != len(supplied)
                or len(pairs) != len(set(pairs))
                or set(pairs) != required
            ):
                raise CatalogError(
                    "VERIFICATION_INCOMPLETE",
                    "Verification must cover exactly the declared capabilities",
                )
            if any(
                c.get("outcome") != "passed"
                or not isinstance(c.get("checks"), list)
                or not c["checks"]
                for c in supplied
            ):
                raise CatalogError(
                    "VERIFICATION_INCOMPLETE",
                    "Each capability requires successful checks",
                )
        self.c.execute(
            "INSERT INTO parser_profile_verifications VALUES(?,?,?,?,?,?)",
            (
                ident,
                profile_uuid,
                outcome,
                canonical(criteria),
                canonical(evidence),
                verified_at_us if verified_at_us is not None else now_us(),
            ),
        )
        self._changed()
        return ident

    def trust_verification(self, verification_uuid, trusted=True, *, rationale=None):
        self.c.execute(
            "INSERT INTO local_parser_profile_verification_trust VALUES(?,?,?,?) ON CONFLICT(parser_profile_verification_uuidv4) DO UPDATE SET trusted=excluded.trusted,adjudicated_at_us=excluded.adjudicated_at_us,rationale_json=excluded.rationale_json",
            (verification_uuid, int(trusted), now_us(), canonical(rationale or {})),
        )
        self._changed()

    def invalidate_verification(
        self, verification_uuid, reason, *, invalidation_uuid=None
    ):
        ident = _uuid(invalidation_uuid)
        self.c.execute(
            "INSERT INTO parser_profile_verification_invalidations VALUES(?,?,?,?)",
            (ident, verification_uuid, reason, now_us()),
        )
        self._changed()
        return ident

    def ensure_builtin_profile(self):
        definition = builtin_definition()
        manifest_path = files("repo_catalog").joinpath(
            "resources/builtin_parser_verification.json"
        )
        if not manifest_path.is_file():
            raise CatalogError(
                "BUILTIN_VERIFICATION_MISSING",
                "Installed parser verification evidence is unavailable",
            )
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("definition") != definition:
            raise CatalogError(
                "BUILTIN_VERIFICATION_STALE",
                "Parser implementation differs from packaged verification",
            )
        old = self._row(
            "SELECT parser_profile_uuidv4 FROM parser_profiles WHERE definition_json=?",
            (canonical(definition),),
        )
        profile = (
            old["parser_profile_uuidv4"]
            if old
            else self.register_profile(
                definition, parser_version="builtin-1", profile_version="catalog3-12"
            )
        )
        verification = self._row(
            "SELECT v.parser_profile_verification_uuidv4 FROM parser_profile_verifications v WHERE v.parser_profile_uuidv4=? AND v.outcome='passed' AND v.criteria_json=?",
            (profile, canonical(manifest["criteria"])),
        )
        if verification is None:
            uid = self.verify_profile(
                profile, criteria=manifest["criteria"], evidence=manifest
            )
            self.trust_verification(
                uid,
                rationale={
                    "policy": "installed-package-verification",
                    "definition": hashlib.sha256(
                        canonical(definition).encode()
                    ).hexdigest(),
                },
            )
        return profile

    def create_result(
        self,
        profile_uuid,
        *,
        repository_uuidv4=None,
        source_registration_uuidv4=None,
        inputs,
        parsed_at_us=None,
        derivation=None,
        result_uuid=None,
    ):
        if (repository_uuidv4 is None) == (source_registration_uuidv4 is None):
            raise CatalogError(
                "PARSER_OWNER", "Exactly one parsed-result owner required"
            )
        if not inputs or any(
            not isinstance(i, dict)
            or len(i) != 1
            or next(iter(i))
            not in (
                "fetch_occurrence_uuidv4",
                "git_acquisition_id",
                "source_input_uuidv4",
            )
            for i in inputs
        ):
            raise CatalogError("PARSER_INPUT", "Nonempty typed input manifest required")
        ident = _uuid(result_uuid)
        owner = "repository" if repository_uuidv4 else "source"
        self.c.execute(
            "INSERT INTO parsed_results(parsed_result_uuidv4,parser_profile_uuidv4,owner_kind,repository_uuidv4,source_registration_uuidv4,parsed_at_us,input_manifest_json,derivation_json) VALUES(?,?,?,?,?,?,?,?)",
            (
                ident,
                profile_uuid,
                owner,
                repository_uuidv4,
                source_registration_uuidv4,
                parsed_at_us if parsed_at_us is not None else now_us(),
                canonical(inputs),
                canonical(derivation or {}),
            ),
        )
        for ordinal, item in enumerate(inputs):
            self.c.execute(
                "INSERT INTO parsed_result_inputs VALUES(?,?,?,?,?,?,?,?)",
                (
                    ident,
                    ordinal,
                    owner,
                    repository_uuidv4,
                    source_registration_uuidv4,
                    item.get("fetch_occurrence_uuidv4"),
                    item.get("git_acquisition_id"),
                    item.get("source_input_uuidv4"),
                ),
            )
        self._changed()
        return ident

    def publish_result(self, result_uuid):
        if self._row(
            "SELECT 1 FROM parsed_result_publications WHERE parsed_result_uuidv4=?",
            (result_uuid,),
        ):
            return
        manifest = [
            {"table": r["table_name"], "key": json.loads(r["fact_key_json"])}
            for r in self._rows(
                "SELECT table_name,fact_key_json FROM parsed_fact_members WHERE parsed_result_uuidv4=? ORDER BY table_name,fact_key_json",
                (result_uuid,),
            )
        ]
        self.c.execute(
            "INSERT INTO parsed_result_publications SELECT parsed_result_uuidv4,json_array_length(input_manifest_json),?,? FROM parsed_results WHERE parsed_result_uuidv4=?",
            (canonical(manifest), now_us(), result_uuid),
        )
        self._changed()

    def _profile_scope(
        self,
        *,
        repository_uuidv4=None,
        source_registration_uuidv4=None,
        change_request_id=None,
        fact_kind,
    ):
        if (repository_uuidv4 is None) == (source_registration_uuidv4 is None):
            raise CatalogError("PARSER_OWNER", "Exactly one selection owner required")
        row = self._row(
            "SELECT * FROM parser_profile_selection_scopes WHERE repository_uuidv4 IS ? AND source_registration_uuidv4 IS ? AND change_request_id IS ? AND fact_kind=?",
            (
                repository_uuidv4,
                source_registration_uuidv4,
                change_request_id,
                fact_kind,
            ),
        )
        if row:
            return row
        uid = _uuid()
        owner = "repository" if repository_uuidv4 else "source"
        self.c.execute(
            "INSERT INTO parser_profile_selection_scopes VALUES(?,?,?,?,?,?)",
            (
                uid,
                owner,
                repository_uuidv4,
                source_registration_uuidv4,
                change_request_id,
                fact_kind,
            ),
        )
        return self._row(
            "SELECT * FROM parser_profile_selection_scopes WHERE selection_scope_uuidv4=?",
            (uid,),
        )

    def ensure_scope_profile(self, profile_uuid, **scope):
        existing = self._row(
            "SELECT selection_scope_uuidv4 FROM parser_profile_selection_scopes WHERE repository_uuidv4 IS ? AND source_registration_uuidv4 IS ? AND change_request_id IS ? AND fact_kind=?",
            (
                scope.get("repository_uuidv4"),
                scope.get("source_registration_uuidv4"),
                scope.get("change_request_id"),
                scope["fact_kind"],
            ),
        )
        if existing:
            active = self._row(
                "SELECT parser_profile_uuidv4 FROM active_parser_profile_selections WHERE selection_scope_uuidv4=?",
                (existing["selection_scope_uuidv4"],),
            )
            return (
                existing["selection_scope_uuidv4"]
                if active and active["parser_profile_uuidv4"] == profile_uuid
                else None
            )
        verification = self._row(
            "SELECT v.parser_profile_verification_uuidv4 FROM parser_profile_verifications v JOIN local_parser_profile_verification_trust t USING(parser_profile_verification_uuidv4) WHERE v.parser_profile_uuidv4=? AND v.outcome='passed' AND t.trusted=1 AND NOT EXISTS(SELECT 1 FROM parser_profile_verification_invalidations i WHERE i.parser_profile_verification_uuidv4=v.parser_profile_verification_uuidv4)",
            (profile_uuid,),
        )
        if not verification:
            raise CatalogError(
                "PARSER_UNVERIFIED", "No locally trusted whole-profile verification"
            )
        self.select_profile(
            profile_uuid,
            verification["parser_profile_verification_uuidv4"],
            predecessors=[],
            **scope,
        )
        return self._profile_scope(**scope)["selection_scope_uuidv4"]

    def _heads(self, prefix, scope_id):
        uid, scope, _ = self._decision_names(prefix)
        return [
            r[uid]
            for r in self._rows(
                f"SELECT d.{uid} FROM {prefix}_decisions d JOIN {prefix}_publications p USING({uid}) WHERE d.{scope}=? AND NOT EXISTS(SELECT 1 FROM {prefix}_predecessors e JOIN {prefix}_publications ep ON ep.{uid}=e.{uid} WHERE e.predecessor_decision_uuidv4=d.{uid})",
                (scope_id,),
            )
        ]

    @staticmethod
    def _decision_names(prefix):
        return (
            ("selection_decision_uuidv4", "selection_scope_uuidv4", "parser_profile")
            if prefix == "parser_profile_selection"
            else (
                "fact_selection_decision_uuidv4",
                "fact_selection_scope_uuidv4",
                "fact",
            )
        )

    def _default_predecessors(self, prefix, scope_id):
        _, scope, _ = self._decision_names(prefix)
        heads = self._heads(prefix, scope_id)
        if len(heads) > 1 or self._row(
            f"SELECT 1 FROM {prefix}_staging WHERE {scope}=?", (scope_id,)
        ):
            raise CatalogError(
                "SELECTION_UNRESOLVED", "Explicit predecessor resolution required"
            )
        return heads

    def select_profile(
        self,
        profile_uuid,
        verification_uuid,
        *,
        predecessors=None,
        decision_uuid=None,
        issuer="local",
        decided_at_us=None,
        **scope,
    ):
        target = self._profile_scope(**scope)
        sid = target["selection_scope_uuidv4"]
        pred = (
            self._default_predecessors("parser_profile_selection", sid)
            if predecessors is None
            else predecessors
        )
        record = {
            "selection_decision_uuidv4": _uuid(decision_uuid),
            "selection_scope_uuidv4": sid,
            "owner_kind": target["owner_kind"],
            "fact_kind": target["fact_kind"],
            "parser_profile_uuidv4": profile_uuid,
            "parser_profile_verification_uuidv4": verification_uuid,
            "required_verification_outcome": "passed",
            "predecessor_manifest_json": canonical(pred),
            "issuer": issuer,
            "decided_at_us": decided_at_us if decided_at_us is not None else now_us(),
        }
        self._receive("parser_profile_selection", record, staging=False)
        self.promote_staging()
        return record["selection_decision_uuidv4"]

    def select_fact(
        self,
        result_uuid,
        *,
        fact_kind,
        change_request_id=None,
        kind=None,
        provider_change_request_document_id=None,
        provider_resource_id=None,
        fetch_occurrence_uuidv4=None,
        predecessors=None,
        decision_uuid=None,
        issuer="local",
        decided_at_us=None,
    ):
        result = self._row(
            "SELECT * FROM parsed_results WHERE parsed_result_uuidv4=?", (result_uuid,)
        )
        if not result:
            raise CatalogError("PARSER_RESULT_MISSING", "Parsed result unavailable")
        params = (
            result["repository_uuidv4"],
            result["source_registration_uuidv4"],
            change_request_id,
            fact_kind,
            kind,
            provider_change_request_document_id,
            provider_resource_id,
            fetch_occurrence_uuidv4,
        )
        target = self._row(
            "SELECT * FROM fact_selection_scopes WHERE repository_uuidv4 IS ? AND source_registration_uuidv4 IS ? AND change_request_id IS ? AND fact_kind=? AND kind IS ? AND provider_change_request_document_id IS ? AND provider_resource_id IS ? AND fetch_occurrence_uuidv4 IS ?",
            params,
        )
        if not target:
            sid = _uuid()
            self.c.execute(
                "INSERT INTO fact_selection_scopes VALUES(?,?,?,?,?,?,?,?,?,?)",
                (sid, result["owner_kind"], *params),
            )
        else:
            sid = target["fact_selection_scope_uuidv4"]
        pred = (
            self._default_predecessors("fact_selection", sid)
            if predecessors is None
            else predecessors
        )
        record = {
            "fact_selection_decision_uuidv4": _uuid(decision_uuid),
            "fact_selection_scope_uuidv4": sid,
            "parsed_result_uuidv4": result_uuid,
            "repository_uuidv4": result["repository_uuidv4"],
            "source_registration_uuidv4": result["source_registration_uuidv4"],
            "predecessor_manifest_json": canonical(pred),
            "issuer": issuer,
            "decided_at_us": decided_at_us if decided_at_us is not None else now_us(),
        }
        self._receive("fact_selection", record, staging=False)
        self.promote_staging()
        return record["fact_selection_decision_uuidv4"]

    def receive_profile_decision(self, record):
        status = self._receive("parser_profile_selection", record)
        self.promote_staging()
        return status

    def receive_fact_decision(self, record):
        status = self._receive("fact_selection", record)
        self.promote_staging()
        return status

    def _receive(self, prefix, record, *, staging=True):
        uid, scope, _ = self._decision_names(prefix)
        _uuid(record[uid])
        _uuid(record[scope])
        predecessors = json.loads(record["predecessor_manifest_json"])
        if not isinstance(predecessors, list) or len(predecessors) != len(
            set(predecessors)
        ):
            raise CatalogError(
                "SELECTION_MANIFEST", "Unique predecessor UUID list required"
            )
        for predecessor in predecessors:
            _uuid(predecessor)
        old = self._row(
            f"SELECT * FROM {prefix}_decisions WHERE {uid}=?", (record[uid],)
        )
        if old:
            if old != record:
                if staging:
                    self._stage(prefix, record, "immutable identity conflict")
                    return "staged"
                raise CatalogError(
                    "IMMUTABLE_IDENTITY_CONFLICT", "Decision UUID content differs"
                )
            return "duplicate"
        try:
            self.c.execute("SAVEPOINT parser_decision_admit")
            columns = list(record)
            self.c.execute(
                f"INSERT INTO {prefix}_decisions({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                [record[c] for c in columns],
            )
            for predecessor in predecessors:
                self.c.execute(
                    f"INSERT INTO {prefix}_predecessors VALUES(?,?,?)",
                    (record[uid], predecessor, record[scope]),
                )
            self.c.execute(
                f"INSERT INTO {prefix}_publications VALUES(?)", (record[uid],)
            )
            self.c.execute("RELEASE parser_decision_admit")
        except sqlite3.IntegrityError as exc:
            self.c.execute("ROLLBACK TO parser_decision_admit")
            self.c.execute("RELEASE parser_decision_admit")
            if not staging:
                raise
            self._stage(prefix, record, str(exc))
            return "staged"
        self.c.execute(
            f"DELETE FROM {prefix}_staging WHERE {uid}=? AND record_json=?",
            (record[uid], canonical(record)),
        )
        self._changed()
        return "admitted"

    def _stage(self, prefix, record, reason):
        uid, scope, _ = self._decision_names(prefix)
        old = self._row(
            f"SELECT record_json FROM {prefix}_staging WHERE {uid}=?", (record[uid],)
        )
        if old and old["record_json"] != canonical(record):
            raise CatalogError(
                "STAGING_IDENTITY_CONFLICT",
                "Different staged record already retained for UUID",
            )
        if not old:
            self.c.execute(
                f"INSERT INTO {prefix}_staging VALUES(?,?,?,?,?)",
                (record[uid], record[scope], canonical(record), reason, now_us()),
            )
            self._changed()

    def promote_staging(self):
        promoted = 0
        while True:
            progress = 0
            for prefix in ("parser_profile_selection", "fact_selection"):
                for pending in self._rows(f"SELECT record_json FROM {prefix}_staging"):
                    if (
                        self._receive(prefix, json.loads(pending["record_json"]))
                        == "admitted"
                    ):
                        progress += 1
            promoted += progress
            if not progress:
                return promoted
