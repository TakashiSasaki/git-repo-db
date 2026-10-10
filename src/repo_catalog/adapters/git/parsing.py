"""Verified intrinsic Git structures and explicitly addressed decoder values."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.transactions import atomic_unit
from repo_catalog.domain.git_decoding import (
    DECODER_FIELDS,
    decode_blob,
    decode_commit,
    decoder_settings,
    validate_decoded_value,
)
from repo_catalog.domain.git_intrinsic import (
    commit_structure,
    tag_structure,
    tree_structure,
)
from repo_catalog.domain.git_object import validate_git_object
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us

PARSER_MODULE = "repo_catalog.adapters.git.parsing"
PARSER_VERSION = "git-object-v2"


class _ConnectionStore:
    """The SQLite port used when Exchange already owns the outer transaction."""

    def __init__(self, connection):
        from repo_catalog.config import DEFAULTS

        self.connection = connection
        self.config = DEFAULTS
        register_git_object_sql_function(connection)

    def execute(self, sql, values=()):
        cursor = self.connection.execute(sql, values)
        cursor.row_factory = sqlite3.Row
        return cursor

    def one(self, sql, values=()):
        return self.execute(sql, values).fetchone()

    def all(self, sql, values=()):
        return self.execute(sql, values).fetchall()

    def advance_local_revision(self):
        self.execute(
            "UPDATE database_identity SET local_revision=local_revision+1 WHERE singleton=1"
        )

    def transaction(self):
        return atomic_unit(self.connection)


def install_git_object(
    connection,
    fmt,
    oid,
    object_type,
    body,
    *,
    repository_uuid=None,
    acquisition=None,
    decode=True,
    **decoder_settings,
):
    """Install canonical bytes through the direct-object SQLite writer."""
    return GitParsing(
        _ConnectionStore(connection), repository_uuid, **decoder_settings
    ).install_object(
        fmt, oid, object_type, body, acquisition=acquisition, decode=decode
    )


def validate_git_acquisition(connection, acquisition):
    """Check actual refs and reachable canonical object dependencies."""
    return GitParsing(_ConnectionStore(connection)).validate_acquisition(acquisition)


def validate_git_fact(connection, table, row):
    """Verify a claimed decoder value against its real, direct Git subject.

    This checks supported decoding primitives, not whole-parser certificates or
    provenance ranking. Sender module/version stays the producer attribution.
    The caller owns insertion and portable-identity remapping.
    """
    if table not in ("git_commit_facts", "git_text_facts", "git_name_facts"):
        raise CatalogError("GIT_DECODER_FACT", "Unknown direct Git value family")
    store = _ConnectionStore(connection)
    row = dict(row)
    obj_id = (
        row["tree_git_object_id"] if table == "git_name_facts" else row["git_object_id"]
    )
    return _validate_git_fact_subject(
        store, table, row, _git_fact_subject(store, obj_id)
    )


def _git_fact_subject(store, obj_id):
    obj = store.one(
        "SELECT g.*,p.payload_sha256,b.body FROM available_git_objects g JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 WHERE g.git_object_id=?",
        (obj_id,),
    )
    if obj is None:
        raise CatalogError(
            "EXCHANGE_DEPENDENCY_MISSING", "Direct Git decoder subject is unavailable"
        )
    validate_git_object(
        obj["object_format"],
        obj["oid"],
        obj["type"],
        obj["size"],
        obj["body"],
        obj["payload_sha256"],
    )
    return obj


def _validate_git_fact_subject(store, table, row, obj):
    settings = {key: row[key] for key in DECODER_FIELDS}
    decoder_settings(settings, row["decoder_key"])
    obj_id = obj["git_object_id"]
    if table == "git_text_facts":
        if obj["type"] != "blob":
            raise CatalogError("GIT_DECODER_FACT", "Text decoder subject is not a blob")
        content = store.one(
            "SELECT content_id FROM blob_content_map WHERE git_object_id=?", (obj_id,)
        )
        if content is None or row["content_id"] != content[0]:
            raise CatalogError(
                "GIT_DECODER_FACT", "Text content owner contradicts raw blob"
            )
        family, subject, value, metadata = (
            "text",
            row["text_state"],
            row["raw_text"],
            None,
        )
    elif table == "git_commit_facts":
        if obj["type"] != "commit":
            raise CatalogError(
                "GIT_DECODER_FACT", "Metadata decoder subject is not a commit"
            )
        family, subject, value, metadata = (
            "commit",
            None,
            row["message_text"],
            row["metadata"],
        )
    else:
        entry = store.one(
            "SELECT 1 FROM tree_entries WHERE tree_git_object_id=? AND raw_name=?",
            (obj_id, row["raw_name"]),
        )
        if obj["type"] != "tree" or entry is None:
            raise CatalogError(
                "EXCHANGE_DEPENDENCY_MISSING", "Exact Git name subject is unavailable"
            )
        family, subject, value, metadata = (
            "name",
            row["raw_name"],
            row["decoded_name"],
            None,
        )
    try:
        validate_decoded_value(
            family,
            obj["object_format"],
            obj["body"],
            row["decoder_key"],
            settings,
            subject,
            value,
            metadata,
        )
    except (TypeError, ValueError, AttributeError, UnicodeError) as error:
        raise CatalogError(
            "GIT_DECODER_FACT", "Invalid direct Git decoded value"
        ) from error
    if family == "commit":
        row["metadata"] = json.dumps(json.loads(row["metadata"]), sort_keys=True)
    return row


def git_fact_validation_issues(connection):
    """Check retained decoder values, validating each actual subject once.

    This ephemeral read groups candidates by their direct object key. It does
    not install a certificate or make interpretations depend on a batch.
    """
    store = _ConnectionStore(connection)
    issues = []
    for owner in store.execute(
        "SELECT git_object_id FROM git_text_facts UNION SELECT git_object_id FROM git_commit_facts "
        "UNION SELECT tree_git_object_id FROM git_name_facts"
    ):
        obj_id = owner[0]
        try:
            obj, subject_error = _git_fact_subject(store, obj_id), None
        except CatalogError as error:
            obj, subject_error = None, error
        for table in ("git_text_facts", "git_commit_facts", "git_name_facts"):
            field = (
                "tree_git_object_id" if table == "git_name_facts" else "git_object_id"
            )
            for row in store.execute(
                f"SELECT * FROM {table} WHERE {field}=?", (obj_id,)
            ):
                try:
                    if subject_error is not None:
                        raise subject_error
                    _validate_git_fact_subject(store, table, dict(row), obj)
                except (
                    TypeError,
                    ValueError,
                    KeyError,
                    AttributeError,
                    UnicodeError,
                    CatalogError,
                ) as error:
                    code = (
                        error.code
                        if isinstance(error, CatalogError)
                        else "GIT_DECODER_FACT"
                    )
                    if code == "EXCHANGE_DEPENDENCY_MISSING":
                        code = "GIT_DECODER_SUBJECT_UNAVAILABLE"
                    issues.append(
                        {
                            "code": code,
                            "table": table,
                            "git_object_id": obj_id,
                            "decoder_key": row["decoder_key"],
                        }
                    )
    return issues


class GitParsing:
    def __init__(
        self,
        store,
        repository_uuid=None,
        *,
        token=None,
        text_encoding="utf-8",
        metadata_encoding="utf-8",
        metadata_errors="backslashreplace",
        max_text_blob_bytes=None,
    ):
        self.s, self.repo, self.token = store, repository_uuid, token
        self._install_depth = 0
        self.encoding, self.metadata_encoding, self.errors = (
            text_encoding,
            metadata_encoding,
            metadata_errors,
        )
        self.limit = (
            store.config["preservation"]["max_text_blob_bytes"]
            if max_text_blob_bytes is None
            else max_text_blob_bytes
        )
        if (
            self.encoding not in ("utf-8", "latin-1")
            or self.metadata_encoding not in ("utf-8", "latin-1")
            or self.errors not in ("strict", "replace", "backslashreplace")
            or type(self.limit) is not int
            or self.limit < 0
        ):
            raise CatalogError("PARSER_DECODER", "Unsupported Git decoding settings")
        self.decoder = {
            "parser_module": PARSER_MODULE,
            "parser_version": PARSER_VERSION,
            "text_encoding": self.encoding,
            "metadata_encoding": self.metadata_encoding,
            "metadata_errors": self.errors,
            "max_text_blob_bytes": self.limit,
        }
        self.decoder_key = hashlib.sha256(
            json.dumps(self.decoder, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def check(self):
        if self.token is not None:
            self.token.check()

    def write(self, sql, values):
        """Writes never split the enclosing object's transaction at a threshold."""
        self.check()
        self.s.execute(sql, values)

    def fact(self, table, values, keys):
        values = dict(values)
        prior = self.s.one(
            f"SELECT * FROM {table} WHERE " + " AND ".join(f"{key}=?" for key in keys),
            tuple(values[k] for k in keys),
        )
        if prior:
            changes = {}
            for key, value in values.items():
                if prior[key] == value:
                    continue
                if (
                    key.endswith("git_object_id")
                    and prior[key] is None
                    and value is not None
                ):
                    changes[key] = value
                else:
                    raise CatalogError(
                        "IMMUTABLE_IDENTITY_CONFLICT",
                        "Existing Git object structure or decoder value differs",
                    )
            if changes:
                self.write(
                    f"UPDATE {table} SET "
                    + ",".join(f"{key}=?" for key in changes)
                    + " WHERE "
                    + " AND ".join(f"{key}=?" for key in keys),
                    (*changes.values(), *(values[k] for k in keys)),
                )
            return
        if table in ("git_commit_facts", "git_text_facts"):
            values["git_fact_uuidv4"] = str(uuid.uuid4())
        self.write(
            f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
            tuple(values.values()),
        )

    def decode(self, raw):
        try:
            return raw.decode(self.metadata_encoding, self.errors)
        except UnicodeError as error:
            raise CatalogError(
                "PARSER_DECODE", "Git metadata decoding failed"
            ) from error

    def object(self, fmt, oid, expected_type=None):
        obj = self.s.one(
            "SELECT g.git_object_id,g.type FROM git_objects g JOIN git_object_payloads p USING(git_object_id) WHERE g.object_format=? AND g.oid=? AND g.verified=1",
            (fmt, oid),
        )
        if (
            obj is not None
            and expected_type is not None
            and obj["type"] != expected_type
        ):
            raise CatalogError(
                "GIT_OBJECT_IDENTITY", "Git target type contradicts bytes"
            )
        return obj["git_object_id"] if obj else None

    def install_object(
        self, fmt, oid, object_type, body, *, acquisition=None, decode=True
    ):
        """Admit real bytes and their entire intrinsic structure as one unit.

        Exchange can use this entry point instead of trusting sender relations.
        An omitted target remains its canonical OID with a NULL local object ID.
        """
        validate_git_object(fmt, oid, object_type, len(body), body)
        with self.s.transaction():
            before = self.s.connection.total_changes
            payload = intern_payload(
                self.s.connection, body, representation="git-object-raw-v1"
            )
            existing = self.s.one(
                "SELECT * FROM git_objects WHERE object_format=? AND oid=?", (fmt, oid)
            )
            if existing:
                if existing["type"] != object_type or existing["size"] != len(body):
                    raise CatalogError(
                        "GIT_OBJECT_IDENTITY", "Conflicting Git identity"
                    )
                obj_id = existing["git_object_id"]
                if not existing["verified"]:
                    self.s.execute(
                        "UPDATE git_objects SET verified=1 WHERE git_object_id=?",
                        (obj_id,),
                    )
            else:
                obj_id = self.s.execute(
                    "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,?,?,1)",
                    (fmt, oid, object_type, len(body)),
                ).lastrowid
            self.fact(
                "git_object_payloads",
                {
                    "git_object_id": obj_id,
                    "payload_representation": payload.representation,
                    "payload_sha256": payload.sha256,
                },
                ("git_object_id",),
            )
            if acquisition is not None:
                run = self.s.one(
                    "SELECT repository_uuidv4 FROM git_acquisitions WHERE git_acquisition_id=?",
                    (acquisition,),
                )
                if run is None or (self.repo is not None and run[0] != self.repo):
                    raise CatalogError(
                        "PARSER_INPUT_MISSING", "Unknown acquired Git owner"
                    )
                self.fact(
                    "repository_object_sources",
                    {
                        "repository_uuidv4": run[0],
                        "git_object_id": obj_id,
                        "git_acquisition_id": acquisition,
                    },
                    ("repository_uuidv4", "git_object_id", "git_acquisition_id"),
                )
            obj = self.s.one(
                "SELECT * FROM git_objects WHERE git_object_id=?", (obj_id,)
            )
            self._install_depth += 1
            try:
                self.parse_object(obj, body, decode=decode)
            finally:
                self._install_depth -= 1
            if self.s.connection.total_changes != before:
                self.s.advance_local_revision()
        return obj_id

    def _content(self, obj_id, body):
        mapped = self.s.one(
            "SELECT content_id FROM blob_content_map WHERE git_object_id=?", (obj_id,)
        )
        digest = hashlib.sha256(body).digest()
        existing = self.s.one(
            "SELECT m.content_id FROM blob_content_map m JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 WHERE p.payload_sha256=? AND b.body=? LIMIT 1",
            (digest, body),
        )
        cid = (
            (mapped[0] if mapped else existing[0])
            if mapped or existing
            else self.s.execute(
                "INSERT INTO contents(byte_length,created_at_us) VALUES(?,?)",
                (len(body), now_us()),
            ).lastrowid
        )
        if self.s.one("SELECT byte_length FROM contents WHERE content_id=?", (cid,))[
            0
        ] != len(body):
            raise CatalogError(
                "GIT_OBJECT_IDENTITY", "Raw content length contradicts Git bytes"
            )
        self.fact(
            "blob_content_map",
            {"git_object_id": obj_id, "content_id": cid},
            ("git_object_id",),
        )
        for algo in ("md5", "sha1", "sha256"):
            expected = hashlib.new(algo, body).digest()
            prior = self.s.one(
                "SELECT digest FROM content_digests WHERE content_id=? AND representation='raw-content-v1' AND algorithm=?",
                (cid, algo),
            )
            if prior and prior[0] != expected:
                raise CatalogError(
                    "GIT_OBJECT_IDENTITY", "Raw content digest contradicts Git bytes"
                )
            if not prior:
                self.write(
                    "INSERT INTO content_digests(content_id,representation,algorithm,digest,verified_at_us,pipeline_version) VALUES(?,'raw-content-v1',?,?,?,'v1')",
                    (cid, algo, expected, now_us()),
                )

    def parse_object(self, obj, data, *, decode=True):
        self.check()
        validate_git_object(
            obj["object_format"], obj["oid"], obj["type"], obj["size"], data
        )
        try:
            with self.s.transaction():
                before = self.s.connection.total_changes
                if obj["type"] == "commit":
                    self.commit(obj, data, decode=decode)
                elif obj["type"] == "tree":
                    self.tree(obj, data, decode=decode)
                elif obj["type"] == "tag":
                    self.tag(obj, data)
                elif obj["type"] == "blob":
                    if decode:
                        self.text(obj, data)
                    else:
                        self._content(obj["git_object_id"], data)
                if (
                    self._install_depth == 0
                    and self.s.connection.total_changes != before
                ):
                    self.s.advance_local_revision()
        except (ValueError, StopIteration, IndexError, KeyError, UnicodeError) as error:
            raise CatalogError(
                "GIT_OBJECT_STRUCTURE", "Malformed intrinsic Git object"
            ) from error

    def commit(self, obj, data, *, decode=True):
        structure = commit_structure(obj["object_format"], data)
        headers, message = structure["raw_headers"], structure["raw_message"]
        fmt, obj_id = obj["object_format"], obj["git_object_id"]
        tree = structure["tree_oid"]
        parents = structure["parents"]
        self.fact(
            "commits",
            {
                "git_object_id": obj_id,
                "tree_format": fmt,
                "tree_oid": tree,
                "tree_git_object_id": self.object(fmt, tree, "tree"),
                "tree_header_offset": structure["tree_header_offset"],
                "parent_count": len(parents),
                "raw_headers": headers,
                "raw_message": message,
            },
            ("git_object_id",),
        )
        for ordinal, parent in enumerate(parents):
            self.fact(
                "commit_parents",
                {
                    "commit_git_object_id": obj_id,
                    "parent_ordinal": ordinal,
                    "parent_header_offset": parent["parent_header_offset"],
                    "parent_format": fmt,
                    "parent_oid": parent["parent_oid"],
                    "parent_git_object_id": self.object(
                        fmt, parent["parent_oid"], "commit"
                    ),
                },
                ("commit_git_object_id", "parent_ordinal"),
            )
        if not decode:
            return
        try:
            message_text, metadata = decode_commit(fmt, data, self.decoder)
        except UnicodeError as error:
            raise CatalogError(
                "PARSER_DECODE", "Git metadata decoding failed"
            ) from error
        self.fact(
            "git_commit_facts",
            {
                "git_object_id": obj_id,
                "decoder_key": self.decoder_key,
                "parser_module": PARSER_MODULE,
                "parser_version": PARSER_VERSION,
                "metadata_encoding": self.metadata_encoding,
                "metadata_errors": self.errors,
                "text_encoding": self.encoding,
                "max_text_blob_bytes": self.limit,
                "message_text": message_text,
                "metadata": json.dumps(metadata, sort_keys=True),
            },
            ("git_object_id", "decoder_key"),
        )

    def tree(self, obj, data, *, decode=True):
        entries = tree_structure(obj["object_format"], data)
        for entry in entries:
            mode, child = entry["mode"], entry["child_oid"]
            entry.update(
                tree_git_object_id=obj["git_object_id"],
                child_format=obj["object_format"],
                child_git_object_id=None
                if mode == 0o160000
                else self.object(
                    obj["object_format"], child, "tree" if mode == 0o40000 else "blob"
                ),
            )
        self.fact(
            "tree_objects",
            {"git_object_id": obj["git_object_id"], "entry_count": len(entries)},
            ("git_object_id",),
        )
        for entry in entries:
            self.fact("tree_entries", entry, ("tree_git_object_id", "raw_name"))
            if not decode:
                continue
            self.fact(
                "git_name_facts",
                {
                    "tree_git_object_id": obj["git_object_id"],
                    "raw_name": entry["raw_name"],
                    "decoder_key": self.decoder_key,
                    **self.decoder,
                    "decoded_name": self.decode(entry["raw_name"]),
                },
                ("tree_git_object_id", "raw_name", "decoder_key"),
            )

    def tag(self, obj, data):
        structure = tag_structure(obj["object_format"], data)
        target, typ = structure["target_oid"], structure["target_type"]
        self.fact(
            "tag_objects",
            {
                "git_object_id": obj["git_object_id"],
                "target_format": obj["object_format"],
                "target_oid": target,
                "target_type": typ,
                "target_git_object_id": self.object(obj["object_format"], target, typ),
                "raw_payload": data,
            },
            ("git_object_id",),
        )

    def text(self, obj, data):
        self._content(obj["git_object_id"], data)
        state, text = decode_blob(data, self.encoding, self.limit)
        content = self.s.one(
            "SELECT content_id FROM blob_content_map WHERE git_object_id=?",
            (obj["git_object_id"],),
        )
        if not content:
            raise CatalogError(
                "INCOMPLETE_CLOSURE", "Missing raw blob content identity"
            )
        self.fact(
            "git_text_facts",
            {
                "git_object_id": obj["git_object_id"],
                "content_id": content[0],
                "decoder_key": self.decoder_key,
                "parser_module": PARSER_MODULE,
                "parser_version": PARSER_VERSION,
                "text_encoding": self.encoding,
                "max_text_blob_bytes": self.limit,
                "metadata_encoding": self.metadata_encoding,
                "metadata_errors": self.errors,
                "text_state": state,
                "raw_text": text,
            },
            ("git_object_id", "decoder_key"),
        )

    def parse_acquisition(self, acquisition, refs=None):
        run = self.s.one(
            "SELECT * FROM git_acquisitions WHERE git_acquisition_id=?", (acquisition,)
        )
        if run is None or (
            self.repo is not None and run["repository_uuidv4"] != self.repo
        ):
            raise CatalogError("PARSER_INPUT_MISSING", "Unknown acquired Git owner")
        self.repo = run["repository_uuidv4"]
        captured = json.loads(run["roots_manifest"] or "[]")
        if refs is not None and refs != captured:
            raise CatalogError("INTEGRITY_ERROR", "Refs differ from fixed acquisition")
        count = 0
        for row in self.s.execute(
            "SELECT git_object_id FROM repository_object_sources WHERE git_acquisition_id=? AND repository_uuidv4=?",
            (acquisition, self.repo),
        ):
            obj = self.s.one(
                "SELECT g.*,p.payload_sha256,b.body FROM git_objects g JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 WHERE g.git_object_id=?",
                (row[0],),
            )
            if obj is None:
                raise CatalogError("INCOMPLETE_CLOSURE", "Missing acquired Git bytes")
            if self.s.one(
                "SELECT 1 FROM payload_quarantine WHERE sha256=?",
                (obj["payload_sha256"],),
            ):
                raise CatalogError(
                    "PAYLOAD_CORRUPTION", "Quarantined Git input cannot be parsed"
                )
            validate_git_object(
                obj["object_format"],
                obj["oid"],
                obj["type"],
                obj["size"],
                obj["body"],
                obj["payload_sha256"],
            )
            self.parse_object(obj, obj["body"])
            count += 1
        for ref in captured:
            if ref["name"].startswith("refs/heads/") or ref.get("role") == "head":
                oid = self.object(
                    run["object_format"], bytes.fromhex(ref["oid"]), "commit"
                )
                commit = self.s.one(
                    "SELECT tree_git_object_id FROM commits WHERE git_object_id=?",
                    (oid,),
                )
                if commit is None or commit[0] is None:
                    raise CatalogError("INCOMPLETE_CLOSURE", "Head tree is unavailable")
                self.manifest(commit[0])
        return count

    def manifest(self, tree):
        prior = self.s.one(
            "SELECT complete FROM root_manifests WHERE tree_git_object_id=?", (tree,)
        )
        if prior and prior[0]:
            return
        entries, stack, complete = [], [(tree, b"", frozenset())], True
        while stack:
            current, prefix, ancestors = stack.pop()
            if current in ancestors:
                raise CatalogError("GIT_OBJECT_STRUCTURE", "Cyclic tree graph")
            if not self.s.one(
                "SELECT 1 FROM available_git_objects WHERE git_object_id=? AND type='tree'",
                (current,),
            ):
                complete = False
                continue
            for entry in self.s.all(
                "SELECT * FROM tree_entries WHERE tree_git_object_id=? ORDER BY raw_name",
                (current,),
            ):
                self.check()
                path = prefix + entry["raw_name"]
                child = (
                    None
                    if entry["mode"] == 0o160000
                    else self.object(
                        entry["child_format"],
                        entry["child_oid"],
                        "tree" if entry["mode"] == 0o40000 else "blob",
                    )
                )
                if entry["mode"] == 0o40000:
                    if child is None:
                        complete = False
                    else:
                        stack.append((child, path + b"/", ancestors | {current}))
                else:
                    if child is None and entry["mode"] != 0o160000:
                        complete = False
                    entries.append(
                        {
                            "tree_git_object_id": tree,
                            "raw_path": path,
                            "mode": entry["mode"],
                            "git_object_id": child,
                            "object_format": entry["child_format"],
                            "oid": entry["child_oid"],
                        }
                    )
        if not complete:
            raise CatalogError(
                "INCOMPLETE_CLOSURE", "Root manifest has missing descendants"
            )
        with self.s.transaction():
            before = self.s.connection.total_changes
            self.fact(
                "root_manifests",
                {
                    "tree_git_object_id": tree,
                    "complete": 1,
                    "entry_count": len(entries),
                },
                ("tree_git_object_id",),
            )
            for entry in entries:
                self.fact(
                    "root_manifest_entries", entry, ("tree_git_object_id", "raw_path")
                )
            if self.s.connection.total_changes != before:
                self.s.advance_local_revision()

    def validate_acquisition(self, acquisition):
        run = self.s.one(
            "SELECT * FROM git_acquisitions WHERE git_acquisition_id=?", (acquisition,)
        )
        if run is None or run["roots_manifest"] is None:
            raise CatalogError("INCOMPLETE_CLOSURE", "Fixed Git capture is missing")
        refs = json.loads(run["roots_manifest"])
        required = {(run["object_format"], bytes.fromhex(ref["oid"])) for ref in refs}
        required.update(
            (run["object_format"], bytes.fromhex(ref["peeled"]))
            for ref in refs
            if ref.get("peeled")
        )
        sources = {
            (row["object_format"], row["oid"]): row["git_object_id"]
            for row in self.s.all(
                "SELECT g.* FROM repository_object_sources r JOIN available_git_objects g USING(git_object_id) WHERE r.git_acquisition_id=?",
                (acquisition,),
            )
        }
        required.update(
            (root["object_format"], root["oid"])
            for root in self.s.all(
                "SELECT object_format,oid FROM acquisition_roots WHERE git_acquisition_id=?",
                (acquisition,),
            )
        )
        visited = set()
        while required:
            identity = required.pop()
            if identity in visited:
                continue
            obj_id = sources.get(identity)
            if obj_id is None:
                raise CatalogError(
                    "INCOMPLETE_CLOSURE", "Observed Git target is unavailable"
                )
            visited.add(identity)
            for row in self.s.all(
                "SELECT tree_format AS fmt,tree_oid AS oid FROM commits WHERE git_object_id=? "
                "UNION ALL SELECT parent_format,parent_oid FROM commit_parents WHERE commit_git_object_id=? "
                "UNION ALL SELECT child_format,child_oid FROM tree_entries WHERE tree_git_object_id=? AND mode<>57344 "
                "UNION ALL SELECT target_format,target_oid FROM tag_objects WHERE git_object_id=?",
                (obj_id, obj_id, obj_id, obj_id),
            ):
                required.add((row["fmt"], row["oid"]))
        all_sources = self.s.one(
            "SELECT count(*) FROM repository_object_sources WHERE git_acquisition_id=?",
            (acquisition,),
        )[0]
        if len(sources) != all_sources:
            raise CatalogError(
                "INCOMPLETE_CLOSURE", "Acquired Git object bytes are unavailable"
            )
        snapshot = self.s.one(
            "SELECT snapshot_id FROM snapshots WHERE git_acquisition_id=?",
            (acquisition,),
        )
        if snapshot:
            import base64

            observed = self.s.all(
                "SELECT * FROM ref_observations WHERE snapshot_id=?", (snapshot[0],)
            )
            expected = {
                base64.b64decode(ref["name_b64"]): (
                    run["object_format"],
                    bytes.fromhex(ref["oid"]),
                    bytes.fromhex(ref["peeled"]) if ref.get("peeled") else None,
                    ref["type"],
                )
                for ref in refs
            }
            actual = {
                row["raw_ref_name"]: (
                    row["object_format"],
                    row["target_oid"],
                    row["peeled_oid"],
                    row["target_type"],
                )
                for row in observed
            }
            if expected != actual:
                raise CatalogError(
                    "INTEGRITY_ERROR", "Ref capture differs from exact observed roots"
                )
        return len(visited)


class _IntrinsicVerifier(GitParsing):
    """Run the actual canonical parser through a read-only relation checker."""

    def parse_object(self, obj, data, *, decode=False):
        try:
            if obj["type"] == "commit":
                self.commit(obj, data, decode=False)
            elif obj["type"] == "tree":
                self.tree(obj, data, decode=False)
            elif obj["type"] == "tag":
                self.tag(obj, data)
            elif obj["type"] == "blob":
                self._content(obj["git_object_id"], data)
        except (ValueError, StopIteration, IndexError, KeyError, UnicodeError) as error:
            raise CatalogError(
                "GIT_OBJECT_STRUCTURE", "Malformed intrinsic Git object"
            ) from error

    def fact(self, table, values, keys):
        prior = self.s.one(
            f"SELECT * FROM {table} WHERE " + " AND ".join(f"{key}=?" for key in keys),
            tuple(values[key] for key in keys),
        )
        if prior is None:
            raise CatalogError(
                "GIT_OBJECT_STRUCTURE", "Canonical Git structural row is missing"
            )
        for key, value in values.items():
            if (
                key.endswith("git_object_id")
                and prior[key] is None
                and value is not None
            ):
                continue  # Canonical OID is retained while local linking is optional.
            if prior[key] != value:
                raise CatalogError(
                    "GIT_OBJECT_STRUCTURE",
                    "Stored intrinsic relation contradicts canonical Git bytes",
                )

    def _content(self, obj_id, body):
        mapped = self.s.one(
            "SELECT content_id FROM blob_content_map WHERE git_object_id=?", (obj_id,)
        )
        if mapped is None:
            return  # Raw blob bytes have no intrinsic parent/entry relation.
        size = self.s.one(
            "SELECT byte_length FROM contents WHERE content_id=?", (mapped[0],)
        )
        if size is None or size[0] != len(body):
            raise CatalogError(
                "GIT_OBJECT_STRUCTURE",
                "Blob content identity contradicts canonical Git bytes",
            )
        for row in self.s.all(
            "SELECT algorithm,digest FROM content_digests WHERE content_id=?",
            (mapped[0],),
        ):
            if hashlib.new(row["algorithm"], body).digest() != row["digest"]:
                raise CatalogError(
                    "GIT_OBJECT_STRUCTURE",
                    "Blob content digest contradicts canonical Git bytes",
                )


def verify_git_object_structure(connection, object_id):
    """Verify complete intrinsic rows and reject extra facts of a foreign type."""
    store = _ConnectionStore(connection)
    obj = store.one(
        "SELECT g.*,p.payload_sha256,b.body FROM git_objects g JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256 WHERE g.git_object_id=?",
        (object_id,),
    )
    if obj is None:
        raise CatalogError(
            "GIT_OBJECT_STRUCTURE", "Canonical Git object payload is missing"
        )
    validate_git_object(
        obj["object_format"],
        obj["oid"],
        obj["type"],
        obj["size"],
        obj["body"],
        obj["payload_sha256"],
    )
    for table, key, expected_type in (
        ("commits", "git_object_id", "commit"),
        ("commit_parents", "commit_git_object_id", "commit"),
        ("tree_objects", "git_object_id", "tree"),
        ("tree_entries", "tree_git_object_id", "tree"),
        ("tag_objects", "git_object_id", "tag"),
        ("blob_content_map", "git_object_id", "blob"),
    ):
        if obj["type"] != expected_type and store.one(
            f"SELECT 1 FROM {table} WHERE {key}=? LIMIT 1", (object_id,)
        ):
            raise CatalogError(
                "GIT_OBJECT_STRUCTURE",
                "Extraneous intrinsic relation belongs to a different Git type",
            )
    verifier = _IntrinsicVerifier(store)
    verifier.parse_object(obj, obj["body"], decode=False)
    if obj["type"] == "tree":
        expected = store.one(
            "SELECT entry_count FROM tree_objects WHERE git_object_id=?", (object_id,)
        )[0]
        actual = store.one(
            "SELECT count(*) FROM tree_entries WHERE tree_git_object_id=?", (object_id,)
        )[0]
        if expected != actual:
            raise CatalogError(
                "GIT_OBJECT_STRUCTURE", "Extraneous intrinsic tree entries"
            )
    elif obj["type"] == "commit":
        expected = store.one(
            "SELECT parent_count FROM commits WHERE git_object_id=?", (object_id,)
        )[0]
        actual = store.one(
            "SELECT count(*) FROM commit_parents WHERE commit_git_object_id=?",
            (object_id,),
        )[0]
        if expected != actual:
            raise CatalogError(
                "GIT_OBJECT_STRUCTURE", "Extraneous intrinsic commit parents"
            )
    return True


def reparse_git(store, acquisition, **decoder_settings):
    run = store.one(
        "SELECT * FROM git_acquisitions WHERE git_acquisition_id=?", (acquisition,)
    )
    if run is None:
        raise CatalogError("NOT_FOUND", "Unknown Git acquisition UUID")
    parser = GitParsing(store, run["repository_uuidv4"], **decoder_settings)
    count = parser.parse_acquisition(acquisition)
    return {
        "git_acquisition_id": acquisition,
        "decoder_key": parser.decoder_key,
        "decoded_objects": count,
    }
