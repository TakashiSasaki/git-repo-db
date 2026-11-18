"""Reparse retained permitted metadata with finite durable actual-work accounting."""

import json
from dataclasses import replace

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.application.git_acquisition import GitAcquisition
from repo_catalog.application.repository_query import RepositoryQueryService
from repo_catalog.domain.git_native import (
    DECODER,
    DECODER_VERSION,
    headers,
    parse_metadata,
    parse_tree,
)
from repo_catalog.domain.p1_repository import (
    OID,
    Provenance,
    RepositoryFailure,
    ScalarClaim,
    account_verification,
    encode,
)
from repo_catalog.domain.query_contracts import SnapshotFenceToken


class RetainedReparseSource:
    """Trusted checked read port; its bounded intent contains no derived claims.

    The live snapshot is a capability, never a DTO or persisted original. A retry
    reuses the original selected physical copies and original snapshot identity;
    their immutable bytes are freshly verified in the current pinned snapshot.
    """

    def __init__(self, unit, snapshot, reader, intent, notes):
        self.unit, self.snapshot, self.reader = unit, snapshot, reader
        self.intent, self.notes = intent, notes

    def read_claims(self, work):
        settings = self.intent["decoder_settings"]
        version = DECODER_VERSION + ":" + encode(settings)
        maximum = self.intent["max_object_bytes"]
        claims = []

        def decode(raw, subject, *, metadata=False):
            work.require("verification_bytes", len(raw))
            work.charge("verification_bytes", len(raw))
            encoding = settings["metadata_encoding" if metadata else "text_encoding"]
            errors = settings["metadata_errors" if metadata else "errors"]
            try:
                return raw.decode(encoding, errors)
            except UnicodeError as error:
                raise RepositoryFailure(
                    "PARSER_DECODE", subject, "Git metadata decoding failed"
                ) from error

        def add(subject, field, value, original):
            work.require("metadata_units", 1)
            work.charge("metadata_units", 1)
            claims.append(ScalarClaim(subject, field, value, original))

        # Validate and derive all selected originals before publishing decoder
        # claims. Strict decoding failure cannot leave a partial decoder report.
        for fmt, oid, copy in self.intent["selected_copies"]:
            object_oid = OID(fmt, oid)
            row = self.snapshot.repository_store.read_metadata_copy(
                object_oid, copy, work, max_bytes=maximum
            )
            with account_verification(work):
                parsed = parse_metadata(fmt, row["native_type"], row["body"])
                work.require("input_bytes", len(row["body"]))
                work.charge("input_bytes", len(row["body"]))
                if row["native_type"] in ("commit", "tag"):
                    _, _, message = headers(row["body"], row["native_type"])
                    parsed.scalars["message"] = decode(message, object_oid.key)
                    for field in (
                        "author",
                        "committer",
                        "author_name",
                        "author_email",
                        "committer_name",
                        "committer_email",
                        "tag_name",
                        "tagger",
                    ):
                        if field in parsed.scalars:
                            parsed.scalars[field] = decode(
                                parsed.scalars[field].encode(
                                    "utf-8", "surrogateescape"
                                ),
                                object_oid.key,
                                metadata=True,
                            )
                observation = encode(
                    [
                        self.unit.capture_origin_uuidv4,
                        self.unit.capture_uuidv4,
                        *object_oid.key,
                    ]
                )
                if row["native_type"] == "tree":
                    for raw_name in parse_tree(fmt, row["body"]):
                        decoded = decode(raw_name, object_oid.key, metadata=True)
                        original = Provenance(
                            self.unit.source_attribution,
                            observation,
                            encode(["reparse-tree-entry", raw_name.hex()]),
                            DECODER,
                            version,
                        )
                        for field, value in (
                            ("raw_name_hex", raw_name.hex()),
                            ("decoded_name", decoded),
                            ("decoder_settings", encode(settings)),
                        ):
                            add(object_oid, field, value, original)
            parsed.scalars["decoder_settings"] = encode(settings)
            for field, value in parsed.scalars.items():
                original = Provenance(
                    self.unit.source_attribution,
                    observation,
                    "reparse-" + field,
                    DECODER,
                    version,
                )
                add(object_oid, field, value, original)
        for claim, mapping in self.notes:
            checked = self.reader.read_ref_note_bytes(
                claim, mapping, work, max_metadata_bytes=maximum
            )
            if (
                not checked.available
                or not checked.verified
                or checked.body_bytes is None
            ):
                raise ValueError(
                    "NOTES_ROLE_UNAVAILABLE: note bytes have no current receiver proof"
                )
            work.require("input_bytes", len(checked.body_bytes))
            work.charge("input_bytes", len(checked.body_bytes))
            decoded = decode(checked.body_bytes, mapping.note_object_oid.key)
            original = Provenance(
                self.unit.source_attribution,
                encode([claim.identity, mapping.key]),
                "reparse-note-message",
                DECODER,
                version,
            )
            add(mapping.note_object_oid, "message", decoded, original)
            add(mapping.note_object_oid, "decoder_settings", encode(settings), original)
        return tuple(claims)


def reparse(
    directory,
    unit,
    objects,
    *,
    request=None,
    new_request=False,
    text_encoding="utf-8",
    errors="surrogateescape",
    metadata_encoding="utf-8",
    metadata_errors="backslashreplace",
    max_object_bytes=64 * 1024 * 1024,
    notes=(),
):
    if (
        not (objects or notes)
        or len(objects) + len(notes) > 100_000
        or not 0 < max_object_bytes <= 64 * 1024 * 1024
    ):
        raise ValueError("INPUT_LIMIT")
    if unit.native_objects or unit.scalar_claims or unit.relation_groups or unit.notes:
        raise ValueError("reparse input must contain original capture metadata only")
    if metadata_encoding not in ("utf-8", "latin-1") or metadata_errors not in (
        "strict",
        "replace",
        "backslashreplace",
        "surrogateescape",
    ):
        raise ValueError("unsupported metadata decoder settings")
    settings = {
        "text_encoding": text_encoding,
        "errors": errors,
        "metadata_encoding": metadata_encoding,
        "metadata_errors": metadata_errors,
    }
    note_keys = json.loads(
        encode([[claim.identity, mapping.key] for claim, mapping in notes])
    )
    scope = [
        "metadata-reparse",
        unit.capture_origin_uuidv4,
        unit.capture_uuidv4,
        [list(item.key) for item in objects],
        note_keys,
        text_encoding,
        errors,
        metadata_encoding,
        metadata_errors,
        max_object_bytes,
    ]
    with OperationalAcquisitionLedger(directory) as ledger:
        _, _, work, progress = ledger.create_budget(
            scope=scope, request=request, new_request=new_request
        )
        reader = RepositoryQueryService(directory, mode="repository_only")
        with reader.open_snapshot(required_store="repository") as snapshot:
            selection_scope = encode(
                [
                    "retained-reparse-source",
                    unit.capture_origin_uuidv4,
                    unit.capture_uuidv4,
                ]
            )
            original = progress.load(selection_scope)
            if original is None:
                copies = []
                for object_oid in objects:
                    rows = snapshot.repository_store.sql(
                        "SELECT physical_copy_uuidv4 FROM retained_metadata WHERE object_format=? AND object_oid=? ORDER BY physical_copy_uuidv4 LIMIT 1",
                        object_oid.key,
                    )
                    if not rows:
                        raise ValueError("BYTES_UNAVAILABLE: metadata was not retained")
                    copies.append([*object_oid.key, rows[0][0]])
                original = progress.save_once(
                    selection_scope,
                    {
                        "kind": "retained-reparse-source-v1",
                        "snapshot_token": snapshot.token.encode(),
                        "selected_copies": copies,
                        "notes": note_keys,
                        "decoder_settings": settings,
                        "max_object_bytes": max_object_bytes,
                    },
                )
            token = SnapshotFenceToken.parse(original["snapshot_token"])
            if (
                original["kind"] != "retained-reparse-source-v1"
                or original["decoder_settings"] != settings
                or original["max_object_bytes"] != max_object_bytes
                or original["notes"] != note_keys
                or [item[:2] for item in original["selected_copies"]]
                != [list(item.key) for item in objects]
                or (token.repository_uuidv4, token.catalog_instance_uuidv4)
                != (
                    snapshot.token.repository_uuidv4,
                    snapshot.token.catalog_instance_uuidv4,
                )
            ):
                raise RepositoryFailure(
                    "INCOMPATIBLE_REPLAY",
                    "metadata-reparse",
                    "original retained selection changed",
                )
            admitted = replace(
                unit,
                nominal_objects=tuple(
                    dict.fromkeys(
                        (*objects, *(mapping.note_object_oid for _, mapping in notes))
                    )
                ),
            )
            source = RetainedReparseSource(admitted, snapshot, reader, original, notes)
            return GitAcquisition(directory, operational=ledger).acquire_metadata_only(
                admitted,
                work=work,
                progress=progress,
                new_request=False,
                request_identity=request,
                reparse_source=source,
            )
