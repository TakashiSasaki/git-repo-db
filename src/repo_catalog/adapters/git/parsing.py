"""Immutable interpretations of verified, independently retained Git object bytes."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager

from repo_catalog.adapters.sqlite.parser_model import ParserModel, builtin_definition
from repo_catalog.domain.git_object import validate_git_object
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us


class GitParsing:
    def __init__(self, store, result_uuid, token=None):
        self.s = store
        self.result = result_uuid
        self.token = token
        self._stage_depth = 0
        self._batching = False
        self._batch_rows = 0
        self._batch_bytes = 0
        row = store.one(
            "SELECT * FROM parsed_results WHERE parsed_result_uuidv4=?", (result_uuid,)
        )
        self.repo = row["repository_uuidv4"]
        definition = json.loads(
            store.one(
                "SELECT definition_json FROM parser_profiles WHERE parser_profile_uuidv4=?",
                (row["parser_profile_uuidv4"],),
            )[0]
        )
        installed = builtin_definition()
        if (
            definition["implementation"] != installed["implementation"]
            or definition["output_schema"] != installed["output_schema"]
        ):
            raise CatalogError(
                "PARSER_UNSUPPORTED_PROFILE",
                "Installed Git parser does not implement this profile",
            )
        settings = definition["settings"]
        self.encoding = settings.get("git_text_encoding", "utf-8")
        self.metadata_encoding = settings.get("git_metadata_encoding", "utf-8")
        self.errors = settings.get("git_metadata_errors", "backslashreplace")
        if (
            self.encoding not in ("utf-8", "latin-1")
            or self.metadata_encoding not in ("utf-8", "latin-1")
            or self.errors not in ("strict", "replace", "backslashreplace")
        ):
            raise CatalogError(
                "PARSER_UNSUPPORTED_PROFILE", "Unsupported Git decoding settings"
            )
        self.limit = settings.get("max_text_blob_bytes", 8388608)
        if type(self.limit) is not int or self.limit < 0:
            raise CatalogError(
                "PARSER_UNSUPPORTED_PROFILE", "Invalid Git text size limit"
            )

    @contextmanager
    def staged_writes(self):
        """Bound acquisition staging; publication still seals every exact member.

        Explicit reparse callers may hold an outer atomic transaction. Acquisition
        writers retain already committed unsealed facts across interruption and
        resume them under their original result/fact identities.
        """
        if self._stage_depth:
            yield
            return
        self._stage_depth = 1
        self._batching = not self.s.connection.in_transaction
        self._batch_rows = self._batch_bytes = 0
        try:
            yield
            if self._batching and self.s.connection.in_transaction:
                self.s.execute("COMMIT")
        except BaseException:
            if self._batching and self.s.connection.in_transaction:
                self.s.execute("ROLLBACK")
            raise
        finally:
            self._stage_depth = 0
            self._batching = False

    def write(self, sql, values):
        if self.token is not None:
            self.token.check()
        if self._batching and not self.s.connection.in_transaction:
            self.s.execute("BEGIN IMMEDIATE")
        self.s.execute(sql, values)
        if self._batching:
            self._batch_rows += 1
            self._batch_bytes += sum(
                len(value.encode("utf8"))
                if isinstance(value, str)
                else len(value)
                if isinstance(value, bytes)
                else 8
                for value in values
            )
            cfg = self.s.config["collection"]
            if (
                self._batch_rows >= cfg["write_batch_rows"]
                or self._batch_bytes >= cfg["write_batch_bytes"]
            ):
                self.s.execute("COMMIT")
                self._batch_rows = self._batch_bytes = 0

    def fact(self, table, values, keys):
        """Resume an unsealed result without changing the identity of existing facts."""
        values = dict(values)
        values.update(
            parsed_result_uuidv4=self.result,
            repository_uuidv4=self.repo,
            git_acquisition_id=self.acquisition,
        )
        prior = self.s.one(
            f"SELECT * FROM {table} WHERE parsed_result_uuidv4=? AND "
            + " AND ".join(f"{key}=?" for key in keys),
            (self.result, *(values[k] for k in keys)),
        )
        if prior:
            if any(prior[k] != v for k, v in values.items()):
                raise CatalogError(
                    "IMMUTABLE_IDENTITY_CONFLICT", "Existing Git interpretation differs"
                )
            return
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

    def parse_acquisition(self, acquisition, refs):
        with self.staged_writes():
            self._parse_acquisition(acquisition, refs)

    def _parse_acquisition(self, acquisition, refs):
        self.acquisition = acquisition
        if not self.s.one(
            "SELECT 1 FROM git_acquisition_publications WHERE git_acquisition_id=? AND repository_uuidv4=?",
            (acquisition, self.repo),
        ):
            raise CatalogError(
                "PARSER_INPUT_MISSING",
                "Exact acquired Git byte membership is unpublished",
            )
        objects = self.s.execute(
            "SELECT g.*,b.payload_sha256,s.body FROM repository_object_sources r JOIN git_objects g USING(git_object_id) JOIN git_object_payloads b USING(git_object_id) JOIN stored_bytes s ON s.sha256=b.payload_sha256 WHERE r.repository_uuidv4=? AND r.git_acquisition_id=? ORDER BY g.git_object_id",
            (self.repo, acquisition),
        )
        for obj in objects:
            if self.token is not None:
                self.token.check()
            data = obj["body"]
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
                data,
                obj["payload_sha256"],
            )
            # Source membership exists for all dependencies before structural facts.
            if obj["type"] == "commit":
                self.commit(obj, data)
            elif obj["type"] == "tree":
                self.tree(obj, data)
            elif obj["type"] == "tag":
                data = obj["body"]
                target = self.object(
                    obj["object_format"],
                    bytes.fromhex(data.split(b"\n", 1)[0].split(b" ", 1)[1].decode()),
                )
                self.fact(
                    "tag_objects",
                    {
                        "git_object_id": obj["git_object_id"],
                        "target_git_object_id": target,
                        "raw_payload": data,
                    },
                    ("git_object_id",),
                )
            elif obj["type"] == "blob":
                self.text(obj, data)
        for ref in refs:
            if ref["name"].startswith("refs/heads/") or ref.get("role") == "head":
                oid = self.object(
                    self.s.one(
                        "SELECT object_format FROM git_acquisitions WHERE git_acquisition_id=?",
                        (acquisition,),
                    )[0],
                    bytes.fromhex(ref["oid"]),
                )
                commit = self.s.one(
                    "SELECT tree_git_object_id FROM commits WHERE parsed_result_uuidv4=? AND git_object_id=?",
                    (self.result, oid),
                )
                if commit is None:
                    raise CatalogError("INTEGRITY_ERROR", "Head must target a commit")
                self.manifest(commit[0])

    def object(self, fmt, oid):
        obj = self.s.git_object_id(fmt, oid)
        if obj is None:
            raise CatalogError("INCOMPLETE_CLOSURE", "Missing Git object dependency")
        return obj

    def commit(self, obj, data):
        headers, message = data.split(b"\n\n", 1)
        entries = [
            line.split(b" ", 1)
            for line in headers.split(b"\n")
            if not line.startswith(b" ")
        ]
        tree = next(value for key, value in entries if key == b"tree")
        metadata = {
            key.decode("ascii", "backslashreplace"): self.decode(value)
            for key, value in entries
            if key not in (b"tree", b"parent")
        }
        self.fact(
            "commits",
            {
                "git_object_id": obj["git_object_id"],
                "tree_git_object_id": self.object(
                    obj["object_format"], bytes.fromhex(tree.decode())
                ),
                "raw_headers": headers,
                "raw_message": message,
                "message_text": self.decode(message),
                "metadata": json.dumps(metadata, sort_keys=True),
            },
            ("git_object_id",),
        )
        for ordinal, parent in enumerate(
            value for key, value in entries if key == b"parent"
        ):
            self.fact(
                "commit_parents",
                {
                    "commit_git_object_id": obj["git_object_id"],
                    "parent_ordinal": ordinal,
                    "parent_git_object_id": self.object(
                        obj["object_format"], bytes.fromhex(parent.decode())
                    ),
                },
                ("commit_git_object_id", "parent_ordinal"),
            )

    def tree(self, obj, data):
        self.fact(
            "root_manifests",
            {"tree_git_object_id": obj["git_object_id"], "complete": 0},
            ("tree_git_object_id",),
        ) if not self.s.one(
            "SELECT 1 FROM root_manifests WHERE parsed_result_uuidv4=? AND tree_git_object_id=?",
            (self.result, obj["git_object_id"]),
        ) else None
        offset = 0
        width = 20 if obj["object_format"] == "sha1" else 32
        while offset < len(data):
            space = data.index(b" ", offset)
            end = data.index(b"\0", space)
            mode = int(data[offset:space], 8)
            name = data[space + 1 : end]
            child = data[end + 1 : end + 1 + width]
            if not name or b"/" in name or len(child) != width:
                raise CatalogError("INTEGRITY_ERROR", "Malformed tree entry")
            self.fact(
                "tree_entries",
                {
                    "tree_git_object_id": obj["git_object_id"],
                    "raw_name": name,
                    "decoded_name": self.decode(name),
                    "mode": mode,
                    "child_format": obj["object_format"],
                    "child_oid": child,
                    "child_git_object_id": None
                    if mode == 0o160000
                    else self.object(obj["object_format"], child),
                },
                ("tree_git_object_id", "raw_name"),
            )
            offset = end + 1 + width

    def text(self, obj, data):
        state = "oversize"
        text = None
        if len(data) <= self.limit:
            try:
                value = data.decode(self.encoding, "strict")
                state = "nul" if "\0" in value else "eligible"
                if state == "eligible":
                    text = value
            except UnicodeError:
                state = "non_utf8"
        content = self.s.one(
            "SELECT content_id FROM blob_content_map WHERE git_object_id=?",
            (obj["git_object_id"],),
        )
        if not content:
            raise CatalogError("INCOMPLETE_CLOSURE", "Missing raw content identity")
        self.fact(
            "git_text_facts",
            {
                "git_object_id": obj["git_object_id"],
                "content_id": content[0],
                "text_state": state,
                "raw_text": text,
            },
            ("git_object_id",),
        )

    def manifest(self, tree):
        with self.staged_writes():
            self._manifest(tree)

    def _manifest(self, tree):
        if self.s.one(
            "SELECT complete FROM root_manifests WHERE parsed_result_uuidv4=? AND tree_git_object_id=?",
            (self.result, tree),
        )[0]:
            return
        stack = [(tree, b"")]
        while stack:
            current, prefix = stack.pop()
            for entry in self.s.all(
                "SELECT * FROM tree_entries WHERE parsed_result_uuidv4=? AND tree_git_object_id=? ORDER BY raw_name",
                (self.result, current),
            ):
                path = prefix + entry["raw_name"]
                if entry["mode"] == 0o40000:
                    stack.append((entry["child_git_object_id"], path + b"/"))
                else:
                    self.fact(
                        "root_manifest_entries",
                        {
                            "tree_git_object_id": tree,
                            "raw_path": path,
                            "decoded_path": self.decode(path),
                            "mode": entry["mode"],
                            "git_object_id": entry["child_git_object_id"],
                            "object_format": entry["child_format"],
                            "oid": entry["child_oid"],
                        },
                        ("tree_git_object_id", "raw_path"),
                    )
        # Complete is a separate immutable boundary after every bounded entry
        # batch is retained, so interrupted manifests remain explicitly partial.
        if self._batching and self.s.connection.in_transaction:
            self.s.execute("COMMIT")
            self._batch_rows = self._batch_bytes = 0
        self.write(
            "UPDATE root_manifests SET complete=1 WHERE parsed_result_uuidv4=? AND tree_git_object_id=?",
            (self.result, tree),
        )


def publish_git_acquisition(store, acquisition, repository):
    """Freeze the complete acquired input before publishing any interpretation."""
    if store.one(
        "SELECT 1 FROM git_acquisition_publications WHERE git_acquisition_id=?",
        (acquisition,),
    ):
        return
    objects = [
        {
            "object_format": row["object_format"],
            "oid": row["oid"].hex(),
            "payload": {
                "representation": row["payload_representation"],
                "sha256": row["payload_sha256"].hex(),
            },
        }
        for row in store.all(
            "SELECT g.object_format,g.oid,p.payload_representation,p.payload_sha256 FROM repository_object_sources r JOIN git_objects g USING(git_object_id) JOIN git_object_payloads p USING(git_object_id) WHERE r.git_acquisition_id=? AND r.repository_uuidv4=? ORDER BY g.object_format,g.oid",
            (acquisition, repository),
        )
    ]
    roots = [
        {
            "object_format": row["object_format"],
            "oid": row["oid"].hex(),
            "role": row["role"],
        }
        for row in store.all(
            "SELECT object_format,oid,role FROM acquisition_roots WHERE git_acquisition_id=? AND repository_uuidv4=? ORDER BY object_format,oid,role",
            (acquisition, repository),
        )
    ]
    store.execute(
        "INSERT INTO git_acquisition_publications VALUES(?,?,?,?)",
        (
            acquisition,
            repository,
            json.dumps(objects, sort_keys=True, separators=(",", ":")),
            json.dumps(roots, sort_keys=True, separators=(",", ":")),
        ),
    )


def reparse_git(store, acquisition, *, select=False, profile_uuid=None):
    run = store.one(
        "SELECT * FROM git_acquisitions WHERE git_acquisition_id=?", (acquisition,)
    )
    if run is None:
        raise CatalogError("NOT_FOUND", "Unknown Git acquisition UUID")
    model = ParserModel(store.connection)
    with store.transaction():
        profile = profile_uuid or model.ensure_builtin_profile()
        result = model.create_result(
            profile,
            repository_uuidv4=run["repository_uuidv4"],
            inputs=[{"git_acquisition_id": acquisition}],
            derivation={"kind": "git", "decoder": "git-object-v1"},
        )
        refs = json.loads(run["roots_manifest"] or "[]")
        parser = GitParsing(store, result)
        parser.parse_acquisition(acquisition, refs)
        snapshot_id = None
        if run["kind"] == "git":
            snapshot_id = str(uuid.uuid4())
            generation = store.one(
                "SELECT coalesce(max(generation),0)+1 FROM snapshots WHERE repository_uuidv4=?",
                (run["repository_uuidv4"],),
            )[0]
            store.execute(
                "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_uuidv4,parsed_result_uuidv4,published,generation,created_at_us) VALUES(?,?,?,?,1,?,?)",
                (
                    snapshot_id,
                    acquisition,
                    run["repository_uuidv4"],
                    result,
                    generation,
                    now_us(),
                ),
            )
            for ref in refs:
                import base64

                store.execute(
                    "INSERT INTO ref_observations(repository_uuidv4,parsed_result_uuidv4,snapshot_id,raw_ref_name,kind,object_format,target_oid,peeled_oid,target_type) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        run["repository_uuidv4"],
                        result,
                        snapshot_id,
                        base64.b64decode(ref["name_b64"]),
                        "head" if ref["name"].startswith("refs/heads/") else "tag",
                        run["object_format"],
                        bytes.fromhex(ref["oid"]),
                        bytes.fromhex(ref["peeled"]) if ref["peeled"] else None,
                        ref["type"],
                    ),
                )
        model.publish_result(result)
        if select:
            active = store.one(
                "SELECT parser_profile_uuidv4 FROM effective_repository_parser_profiles WHERE repository_uuidv4=? AND fact_kind='git'",
                (run["repository_uuidv4"],),
            )
            if not active or active[0] != profile:
                raise CatalogError(
                    "PARSER_UNSELECTED_PROFILE",
                    "Explicitly select and verify the Git profile before selecting this result",
                )
            model.select_fact(result, fact_kind="git", git_acquisition_id=acquisition)
            if run["kind"] == "git":
                model.select_fact(result, fact_kind="git")
    return {
        "parsed_result_uuidv4": result,
        "git_acquisition_id": acquisition,
        "snapshot_id": snapshot_id,
        "selected": select,
    }
