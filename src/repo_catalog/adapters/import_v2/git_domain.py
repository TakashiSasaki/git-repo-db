"""Stored Git recipes for the integrated offline converter.

Recipes consume the sealed SQLite archive only. They never consult a mount,
cache, Git executable or network. Legacy verification/completion assertions
remain archived; reconstructed bytes provide separate admitted results.
"""

import hashlib
import re

from . import identity
from .common import ConversionError, canonical, strict_json
from .types import tagged_key

VERSION = "integrated stored Git/1"
RECIPES = (
    "git_acquisitions",
    "git_objects",
    "contents",
    "commits",
    "commit_parents",
    "tree_entries",
    "tag_objects",
    "content_digests",
    "blob_content_map",
    "repository_object_sources",
    "snapshots",
    "ref_observations",
    "acquisition_roots",
    "root_manifests",
    "root_manifest_entries",
    "root_manifest_completion",
    "ref_root_origins",
    "pr_root_origins",
    "unknown_root_origins",
)
SOURCE_TABLES = {
    "git_acquisitions": "collection_runs",
    "root_manifest_completion": "root_manifests",
    "ref_root_origins": "ref_observations",
    "pr_root_origins": "pr_git_links",
    "unknown_root_origins": "acquisition_roots",
}
COLUMNS = {
    "git_acquisitions": (
        "id",
        "repo_id",
        "endpoint_id",
        "endpoint_url",
        "object_format",
        "refs_observed_at",
        "source_id",
        "kind",
        "started_at",
        "observed_at",
        "request",
        "roots_manifest",
    ),
    "git_objects": ("id", "object_format", "oid", "type", "size", "verified"),
    "contents": ("id", "byte_length", "raw_text", "text_state", "created_at"),
    "commits": ("object_id", "tree_id", "raw_headers", "raw_message", "metadata"),
    "commit_parents": ("commit_id", "parent_ordinal", "parent_id"),
    "tree_entries": (
        "tree_id",
        "raw_name",
        "mode",
        "child_format",
        "child_oid",
        "child_id",
    ),
    "tag_objects": ("object_id", "target_id", "raw_payload"),
    "content_digests": (
        "content_id",
        "representation",
        "algorithm",
        "digest",
        "verified_at",
        "pipeline_version",
    ),
    "blob_content_map": ("object_id", "content_id", "acquisition_id"),
    "repository_object_sources": ("repo_id", "object_id", "acquisition_id"),
    "snapshots": (
        "id",
        "acquisition_id",
        "repo_id",
        "published",
        "generation",
        "created_at",
    ),
    "ref_observations": (
        "snapshot_id",
        "raw_ref_name",
        "kind",
        "object_format",
        "target_oid",
        "peeled_oid",
        "target_type",
    ),
    "acquisition_roots": (
        "id",
        "acquisition_id",
        "object_format",
        "oid",
        "role",
        "repo_id",
        "expected_oid",
        "published",
    ),
    "root_manifests": ("tree_id", "complete"),
    "root_manifest_entries": (
        "tree_id",
        "raw_path",
        "mode",
        "object_id",
        "object_format",
        "oid",
    ),
    "root_origins": (
        "id",
        "root_id",
        "origin_kind",
        "raw_ref_name",
        "source_ordinal",
        "snapshot_id",
        "change_request_id",
        "observation_id",
        "repo_id",
    ),
}
KEYS = {
    "commits": ("object_id",),
    "commit_parents": ("commit_id", "parent_ordinal"),
    "tree_entries": ("tree_id", "raw_name"),
    "tag_objects": ("object_id",),
    "content_digests": ("content_id", "representation", "algorithm"),
    "blob_content_map": ("object_id",),
    "repository_object_sources": ("repo_id", "object_id", "acquisition_id"),
    "ref_observations": ("snapshot_id", "raw_ref_name"),
    "root_manifests": ("tree_id",),
    "root_manifest_entries": ("tree_id", "raw_path"),
}
MODES = (0o40000, 0o100644, 0o100755, 0o120000, 0o160000)


class Invalid(identity.Invalid):
    pass


def target_key(table, row):
    values = []
    for column in KEYS.get(table, ("id",)):
        value = row[COLUMNS[table].index(column)]
        if isinstance(value, bytes):
            values.append(("blob", value))
        elif isinstance(value, int):
            values.append(("integer", value))
        else:
            values.append(("text", value.encode("utf-8")))
    return tagged_key(values)


def origin_id(record, root_id, kind):
    """Stable positive SQLite integer, with collisions rejected by the writer."""
    material = canonical([VERSION, record.table, record.key.hex(), root_id, kind])
    return int.from_bytes(hashlib.sha256(material.encode()).digest()[:8], "big") & (
        (1 << 63) - 1
    )


class Context(identity.Context):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.issues = []

    def issue(self, code, column, severity="partial"):
        self.issues.append(("GIT_" + code, severity, column))

    def t(self, record, column, **options):
        try:
            return super().t(record, column, **options)
        except identity.Invalid as exc:
            raise Invalid(exc.code.replace("IDENTITY_", "GIT_"), exc.column) from None

    def integer(self, record, column, *, nullable=False, minimum=None, choices=None):
        kind, raw = record.value(column)
        if kind == "null" and nullable:
            return None
        if kind != "integer":
            raise Invalid("GIT_INVALID_TYPE", column)
        value = int(raw.decode("ascii"))
        if (
            minimum is not None
            and value < minimum
            or choices is not None
            and value not in choices
        ):
            raise Invalid("GIT_INVALID_VALUE", column)
        return value

    def blob(self, record, column, *, nullable=False, nonempty=False):
        kind, value = record.value(column)
        if kind == "null" and nullable:
            return None
        if kind != "blob":
            raise Invalid("GIT_INVALID_TYPE", column)
        if nonempty and not value:
            raise Invalid("GIT_INVALID_VALUE", column)
        return value

    def enum(self, record, column, choices, *, nullable=False):
        value = self.t(record, column, nullable=nullable)
        if value is not None and value not in choices:
            raise Invalid("GIT_UNKNOWN_VALUE", column)
        return value

    def json(self, record, column, *, nullable=False, expected=dict):
        value = self.t(record, column, nullable=nullable)
        if value is not None:
            try:
                if not isinstance(strict_json(value), expected):
                    raise ValueError()
            except ValueError:
                raise Invalid("GIT_INVALID_JSON", column) from None
        return value

    def timestamp(self, record, column):
        value = self.t(record, column, nullable=True)
        if value is not None:
            try:
                identity.instant(value)
            except ValueError:
                raise Invalid("GIT_INVALID_TIME", column) from None
        return value

    def oid(self, record, column, fmt, *, nullable=False, hexadecimal=False):
        if hexadecimal:
            text = self.t(record, column, nullable=nullable)
            if text is None:
                return None
            if not re.fullmatch(
                r"[0-9a-fA-F]{" + str(40 if fmt == "sha1" else 64) + "}", text
            ):
                raise Invalid("GIT_INVALID_OID", column)
            value = bytes.fromhex(text)
        else:
            value = self.blob(record, column, nullable=nullable)
        if value is not None and len(value) != (20 if fmt == "sha1" else 32):
            raise Invalid("GIT_INVALID_OID", column)
        return value

    def source_record(self, table, *key):
        record = self.lookup(table, *key)
        if record is None:
            raise Invalid("GIT_MISSING_REFERENCE", table)
        return record

    def target(self, table, *key):
        predicate = " AND ".join(column + "=?" for column in KEYS.get(table, ("id",)))
        row = self.db.execute(
            f"SELECT * FROM {table} WHERE {predicate}", key
        ).fetchone()
        if row is None:
            raise Invalid("GIT_UNSAFE_DEPENDENCY", table)
        return row

    def object(self, ident, *, kind=None, fmt=None, oid=None, target=True):
        record = self.source_record("git_objects", ident)
        row = (
            self.integer(record, "id"),
            self.enum(record, "object_format", ("sha1", "sha256")),
            self.blob(record, "oid"),
            self.enum(record, "type", ("commit", "tree", "blob", "tag")),
            self.integer(record, "size", minimum=0),
            self.integer(record, "verified"),
        )
        if len(row[2]) != (20 if row[1] == "sha1" else 32):
            raise Invalid("GIT_INVALID_OID", "oid")
        if (
            kind is not None
            and row[3] != kind
            or fmt is not None
            and row[1] != fmt
            or oid is not None
            and row[2] != oid
        ):
            raise Invalid("GIT_OBJECT_RELATION_MISMATCH", "object_id")
        if target:
            self.target("git_objects", ident)
        return row

    def acquisition(self, record, column="run_id", repo=None):
        ident = self.t(record, column, nonempty=True)
        source_record = self.source_record("collection_runs", ident)
        owner = self.t(source_record, "repo_id", nonempty=True)
        if repo is not None and owner != repo:
            raise Invalid("GIT_OWNER_MISMATCH", column)
        target = self.target("git_acquisitions", ident)
        if target["repo_id"] != owner:
            raise Invalid("GIT_OWNER_MISMATCH", column)
        return ident, owner

    def raw_content(self, ident):
        record = self.source_record("contents", ident)
        value = self.t(record, "raw_text", nullable=True)
        if value is None:
            return None
        raw = value.encode("utf-8")
        if len(raw) != self.integer(record, "byte_length", minimum=0):
            raise Invalid("GIT_CONTENT_LENGTH_MISMATCH", "raw_text")
        return raw

    def verify_object(self, row):
        ident, fmt, oid, kind, size, _ = row
        hasher = hashlib.new(fmt)
        hasher.update(f"{kind} {size}\0".encode("ascii"))
        actual_size = 0
        try:
            if kind == "commit":
                record = self.source_record("commits", ident)
                chunks = (
                    self.blob(record, "raw_headers"),
                    b"\n\n",
                    self.blob(record, "raw_message"),
                )
            elif kind == "tag":
                record = self.source_record("tag_objects", ident)
                chunks = (self.blob(record, "raw_payload"),)
            elif kind == "blob":
                record = self.source_record("blob_content_map", ident)
                raw = self.raw_content(self.integer(record, "content_id"))
                if raw is None:
                    self.issue("ORIGINAL_BYTES_MISSING", "verified")
                    return 0
                chunks = (raw,)
            else:
                # A saved parsed-tree marker distinguishes empty from missing.
                self.source_record("root_manifests", ident)
                chunks = self.tree_chunks(ident, fmt)
            for chunk in chunks:
                actual_size += len(chunk)
                hasher.update(chunk)
        except Invalid as exc:
            self.issue(
                "ORIGINAL_BYTES_MISSING"
                if exc.code == "GIT_MISSING_REFERENCE"
                else exc.code.removeprefix("GIT_"),
                "verified",
                "partial" if exc.code == "GIT_MISSING_REFERENCE" else "blocking",
            )
            return 0
        if actual_size != size or hasher.digest() != oid:
            self.issue("OBJECT_HASH_MISMATCH", "verified", "blocking")
            return 0
        return 1

    def tree_chunks(self, ident, fmt):
        for raw_name, mode, encoded_format, child_oid in self.src.execute(
            "SELECT raw_name,mode,CAST(child_format AS BLOB),child_oid FROM tree_entries WHERE tree_id=? ORDER BY CASE WHEN mode=16384 THEN CAST(raw_name||x'2f' AS BLOB) ELSE raw_name END",
            (ident,),
        ):
            try:
                child_format = encoded_format.decode(self.encoding)
            except UnicodeError:
                raise Invalid("GIT_MALFORMED_TEXT", "child_format") from None
            if (
                not isinstance(raw_name, bytes)
                or not raw_name
                or b"/" in raw_name
                or b"\0" in raw_name
                or mode not in MODES
                or child_format != fmt
                or not isinstance(child_oid, bytes)
                or len(child_oid) != (20 if fmt == "sha1" else 32)
            ):
                raise Invalid("GIT_INVALID_TREE_ENTRY", "tree_entries")
            yield f"{mode:o} ".encode("ascii")
            yield raw_name
            yield b"\0"
            yield child_oid

    def header_oids(self, record, name):
        result = []
        for line in self.blob(record, "raw_headers").split(b"\n"):
            if line.startswith(name + b" "):
                value = line[len(name) + 1 :]
                if not re.fullmatch(rb"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", value):
                    raise Invalid("GIT_INVALID_HEADERS", "raw_headers")
                result.append(bytes.fromhex(value.decode("ascii")))
        return result

    def leaf(self, tree_id, path):
        if (
            not path
            or b"\0" in path
            or any(part in (b"", b".", b"..") for part in path.split(b"/"))
        ):
            raise Invalid("GIT_INVALID_PATH", "raw_path")
        parts = path.split(b"/")
        for position, part in enumerate(parts):
            entry = self.source_record("tree_entries", tree_id, part)
            self.target("tree_entries", tree_id, part)
            if position < len(parts) - 1:
                if self.integer(entry, "mode") != 0o40000:
                    raise Invalid("GIT_MANIFEST_PATH_MISMATCH", "raw_path")
                tree_id = self.integer(entry, "child_id")
            else:
                return entry

    def manifest_complete(self, tree_id):
        """Compare stored manifests to the saved tree closure without a graph buffer."""
        count = 0
        traversal = self.src.execute(
            "WITH RECURSIVE walk(tree_id,prefix,visited,depth) AS ("
            "SELECT ?,x'',','||?||',',0 UNION ALL "
            "SELECT e.child_id,CAST(w.prefix||e.raw_name||x'2f' AS BLOB),w.visited||e.child_id||',',w.depth+1 "
            "FROM walk w JOIN tree_entries e ON e.tree_id=w.tree_id WHERE e.mode=16384 AND w.depth<256 AND instr(w.visited,','||e.child_id||',')=0) "
            "SELECT CAST(w.prefix||e.raw_name AS BLOB),e.mode,e.child_id,CAST(e.child_format AS BLOB),e.child_oid,w.visited,w.depth,w.tree_id,e.raw_name "
            "FROM walk w JOIN tree_entries e ON e.tree_id=w.tree_id",
            (tree_id, tree_id),
        )
        for (
            path,
            mode,
            ident,
            encoded_format,
            oid,
            visited,
            depth,
            owner,
            name,
        ) in traversal:
            try:
                fmt = encoded_format.decode(self.encoding)
            except UnicodeError:
                return False
            if mode == 0o40000:
                if depth >= 256:
                    self.issue("MANIFEST_TRAVERSAL_LIMIT", "complete")
                    return None
                if ident is None or f",{ident}," in visited:
                    return False
                try:
                    directory = self.source_record("tree_entries", owner, name)
                    self.project("tree_entries", directory)
                    self.target("tree_entries", owner, name)
                    if self.target("git_objects", ident)["verified"] != 1:
                        return False
                    # A zero row count does not establish a parsed empty tree.
                    self.source_record("root_manifests", ident)
                except Invalid:
                    return False
                continue
            count += 1
            try:
                record = self.source_record("root_manifest_entries", tree_id, path)
                projected = self.manifest_entry(record)
                if projected != (tree_id, path, mode, ident, fmt, oid):
                    return False
            except Invalid:
                return False
        saved = self.src.execute(
            "SELECT count(*) FROM root_manifest_entries WHERE tree_id=?", (tree_id,)
        ).fetchone()[0]
        return count == saved

    def manifest_entry(self, record):
        tree = self.integer(record, "tree_id")
        obj = self.object(tree, kind="tree")
        path = self.blob(record, "raw_path", nonempty=True)
        mode = self.integer(record, "mode", choices=MODES[1:])
        ident = self.integer(record, "object_id", nullable=True)
        fmt = self.enum(record, "object_format", ("sha1", "sha256"))
        oid = self.oid(record, "oid", fmt)
        if fmt != obj[1] or (mode == 0o160000) != (ident is None):
            raise Invalid("GIT_OBJECT_RELATION_MISMATCH", "object_id")
        if ident is not None:
            self.object(ident, kind="blob", fmt=fmt, oid=oid)
        entry = self.leaf(tree, path)
        if (mode, ident, fmt, oid) != (
            self.integer(entry, "mode"),
            self.integer(entry, "child_id", nullable=True),
            self.t(entry, "child_format"),
            self.blob(entry, "child_oid"),
        ):
            raise Invalid("GIT_MANIFEST_PATH_MISMATCH", "raw_path")
        return tree, path, mode, ident, fmt, oid

    def project(self, recipe, record):
        """Return insert rows plus diagnostics; no allocation or writes occur here."""
        if recipe.endswith("root_origins"):
            return self.origins(recipe, record)
        if recipe == "git_acquisitions":
            ident, repo = (
                self.t(record, "id", nonempty=True),
                self.t(record, "repo_id", nonempty=True),
            )
            self.target("repositories", repo)
            endpoint = self.t(record, "endpoint_id", nullable=True, nonempty=True)
            if (
                endpoint is not None
                and self.target("repository_endpoints", endpoint)["repo_id"] != repo
            ):
                raise Invalid("GIT_OWNER_MISMATCH", "endpoint_id")
            row = (
                ident,
                repo,
                endpoint,
                self.t(record, "endpoint_url", nullable=True),
                self.enum(record, "object_format", ("sha1", "sha256"), nullable=True),
                self.timestamp(record, "refs_at"),
                None,
                self.enum(record, "kind", ("git", "pr", "legacy")),
                self.timestamp(record, "started_at"),
                None,
                self.json(record, "request"),
                self.json(record, "roots_manifest", nullable=True, expected=list),
            )
        elif recipe == "git_objects":
            row = self.object(self.integer(record, "id"), target=False)
            if row[5] not in (0, 1):
                self.issue("INVALID_VERIFICATION_ASSERTION", "verified", "blocking")
            row = (*row[:5], self.verify_object(row))
        elif recipe == "contents":
            ident, length = (
                self.integer(record, "id"),
                self.integer(record, "byte_length", minimum=0),
            )
            text = self.t(record, "raw_text", nullable=True)
            state = self.t(record, "text_state")
            if state not in ("eligible", "nul", "non_utf8", "oversize", "unknown"):
                state = "unknown"
                self.issue("UNKNOWN_TEXT_STATE", "text_state")
            if text is not None and len(text.encode("utf-8")) != length:
                raise Invalid("GIT_CONTENT_LENGTH_MISMATCH", "raw_text")
            if text is not None and (
                state == "non_utf8" or state == "eligible" and "\0" in text
            ):
                raise Invalid("GIT_TEXT_STATE_MISMATCH", "text_state")
            if text is None:
                self.issue("ORIGINAL_BYTES_MISSING", "raw_text")
            row = (ident, length, text, state, self.timestamp(record, "created_at"))
        elif recipe == "commits":
            ident, tree = (
                self.integer(record, "object_id"),
                self.integer(record, "tree_id"),
            )
            obj = self.object(ident, kind="commit")
            root = self.object(tree, kind="tree", fmt=obj[1])
            if self.header_oids(record, b"tree") != [root[2]]:
                raise Invalid("GIT_HEADER_TREE_MISMATCH", "tree_id")
            row = (
                ident,
                tree,
                self.blob(record, "raw_headers"),
                self.blob(record, "raw_message"),
                self.json(record, "metadata"),
            )
            parents = self.header_oids(record, b"parent")
            actual = self.src.execute(
                "SELECT p.parent_ordinal,g.oid FROM commit_parents p JOIN git_objects g ON g.id=p.parent_id WHERE p.commit_id=? ORDER BY p.parent_ordinal",
                (ident,),
            )
            count = 0
            for ordinal, oid in actual:
                if ordinal != count or count >= len(parents) or parents[count] != oid:
                    self.issue("PARENT_ORDER_MISMATCH", "commit_parents", "blocking")
                    break
                count += 1
            if count != len(parents):
                self.issue("PARENT_ORDER_MISMATCH", "commit_parents", "blocking")
        elif recipe == "commit_parents":
            ident, ordinal, parent = (
                self.integer(record, "commit_id"),
                self.integer(record, "parent_ordinal", minimum=0),
                self.integer(record, "parent_id"),
            )
            obj = self.object(ident, kind="commit")
            other = self.object(parent, kind="commit", fmt=obj[1])
            self.target("commits", ident)
            parents = self.header_oids(self.source_record("commits", ident), b"parent")
            if ordinal >= len(parents) or parents[ordinal] != other[2]:
                raise Invalid("GIT_PARENT_ORDER_MISMATCH", "parent_ordinal")
            row = (ident, ordinal, parent)
        elif recipe == "tree_entries":
            tree = self.integer(record, "tree_id")
            obj = self.object(tree, kind="tree")
            name = self.blob(record, "raw_name", nonempty=True)
            if b"/" in name or b"\0" in name or name in (b".", b".."):
                raise Invalid("GIT_INVALID_TREE_ENTRY", "raw_name")
            mode = self.integer(record, "mode", choices=MODES)
            fmt = self.enum(record, "child_format", ("sha1", "sha256"))
            oid, child = (
                self.oid(record, "child_oid", fmt),
                self.integer(record, "child_id", nullable=True),
            )
            if fmt != obj[1] or (mode == 0o160000) != (child is None):
                raise Invalid("GIT_OBJECT_RELATION_MISMATCH", "child_id")
            if child is not None:
                self.object(
                    child, kind="tree" if mode == 0o40000 else "blob", fmt=fmt, oid=oid
                )
            row = (tree, name, mode, fmt, oid, child)
        elif recipe == "tag_objects":
            ident, target = (
                self.integer(record, "object_id"),
                self.integer(record, "target_id"),
            )
            obj = self.object(ident, kind="tag")
            other = self.object(target, fmt=obj[1])
            raw = self.blob(record, "raw_payload")
            headers = raw.split(b"\n\n", 1)[0].split(b"\n")
            object_values = [
                line[7:] for line in headers if line.startswith(b"object ")
            ]
            target_types = [line[5:] for line in headers if line.startswith(b"type ")]
            try:
                valid = (
                    len(object_values) == 1
                    and target_types == [other[3].encode("ascii")]
                    and re.fullmatch(rb"[0-9a-fA-F]+", object_values[0]) is not None
                    and bytes.fromhex(object_values[0].decode("ascii")) == other[2]
                )
            except ValueError:
                valid = False
            if not valid:
                raise Invalid("GIT_TAG_TARGET_MISMATCH", "target_id")
            row = (ident, target, raw)
        elif recipe == "content_digests":
            ident = self.integer(record, "content_id")
            self.target("contents", ident)
            representation = self.enum(record, "representation", ("raw-content-v1",))
            algorithm = self.enum(record, "algorithm", ("md5", "sha1", "sha256"))
            value = self.blob(record, "digest")
            if len(value) != {"md5": 16, "sha1": 20, "sha256": 32}[algorithm]:
                raise Invalid("GIT_INVALID_DIGEST", "digest")
            raw = self.raw_content(ident)
            if raw is not None and hashlib.new(algorithm, raw).digest() != value:
                raise Invalid("GIT_CONTENT_DIGEST_MISMATCH", "digest")
            if raw is None:
                self.issue("DIGEST_BYTES_UNAVAILABLE", "digest")
            row = (
                ident,
                representation,
                algorithm,
                value,
                self.timestamp(record, "verified_at"),
                self.t(record, "pipeline_version", nonempty=True),
            )
        elif recipe == "blob_content_map":
            ident, content = (
                self.integer(record, "object_id"),
                self.integer(record, "content_id"),
            )
            obj = self.object(ident, kind="blob")
            if self.target("contents", content)["byte_length"] != obj[4]:
                raise Invalid("GIT_CONTENT_LENGTH_MISMATCH", "content_id")
            acquisition, _ = self.acquisition(record)
            row = (ident, content, acquisition)
        elif recipe == "repository_object_sources":
            repo, ident = (
                self.t(record, "repo_id", nonempty=True),
                self.integer(record, "object_id"),
            )
            self.target("repositories", repo)
            self.object(ident)
            acquisition, _ = self.acquisition(record, repo=repo)
            row = (repo, ident, acquisition)
        elif recipe == "snapshots":
            repo = self.t(record, "repo_id", nonempty=True)
            acquisition, _ = self.acquisition(record, repo=repo)
            row = (
                self.t(record, "id", nonempty=True),
                acquisition,
                repo,
                self.integer(record, "published", choices=(0, 1)),
                self.integer(record, "generation", minimum=0),
                self.timestamp(record, "created_at"),
            )
        elif recipe == "ref_observations":
            snapshot = self.t(record, "snapshot_id", nonempty=True)
            self.target("snapshots", snapshot)
            fmt = self.enum(record, "object_format", ("sha1", "sha256"))
            row = (
                snapshot,
                self.blob(record, "raw_ref_name", nonempty=True),
                self.enum(record, "kind", ("head", "tag", "other")),
                fmt,
                self.oid(record, "target_oid", fmt),
                self.oid(record, "peeled_oid", fmt, nullable=True),
                self.enum(
                    record,
                    "target_type",
                    ("commit", "tree", "blob", "tag"),
                    nullable=True,
                ),
            )
        elif recipe == "acquisition_roots":
            repo = self.t(record, "repo_id", nonempty=True)
            acquisition, _ = self.acquisition(record, repo=repo)
            fmt = self.enum(record, "object_format", ("sha1", "sha256"))
            acquired_format = self.target("git_acquisitions", acquisition)[
                "object_format"
            ]
            if acquired_format is not None and acquired_format != fmt:
                raise Invalid("GIT_OBJECT_RELATION_MISMATCH", "object_format")
            row = (
                self.integer(record, "id"),
                acquisition,
                fmt,
                self.oid(record, "oid", fmt),
                self.t(record, "role", nonempty=True),
                repo,
                self.oid(record, "expected_oid", fmt, nullable=True, hexadecimal=True),
                self.integer(record, "published", choices=(0, 1)),
            )
            if row[6] is not None and row[6] != row[3]:
                self.issue("EXPECTED_OID_MISMATCH", "expected_oid", "blocking")
        elif recipe in {"root_manifests", "root_manifest_completion"}:
            tree = self.integer(record, "tree_id")
            self.object(tree, kind="tree")
            complete = self.integer(record, "complete", choices=(0, 1))
            if complete:
                admitted = (
                    self.manifest_complete(tree)
                    if self.target("git_objects", tree)["verified"] == 1
                    else False
                )
                if not admitted:
                    complete = 0
                    if admitted is not None:
                        self.issue("MANIFEST_COVERAGE_MISMATCH", "complete", "blocking")
            row = (tree, 0 if recipe == "root_manifests" else complete)
            if recipe == "root_manifest_completion":
                return [("root_manifests", row, "derived")]
        elif recipe == "root_manifest_entries":
            row = self.manifest_entry(record)
            self.target("root_manifests", row[0])
        else:
            raise ConversionError("UNKNOWN_GIT_RECIPE")
        return [(recipe, row, "identity")]

    def ref_candidates(self, record):
        rows = self.project("ref_observations", record)
        _, ref, _ = rows[0]
        snapshot = self.source_record("snapshots", ref[0])
        acquisition = self.t(snapshot, "run_id")
        repo = self.t(snapshot, "repo_id")
        oid = ref[5] if ref[5] is not None else ref[4]
        for (ident,) in self.src.execute(
            "SELECT id FROM acquisition_roots WHERE run_id=? AND repo_id=? AND object_format=? AND oid=? ORDER BY id",
            (acquisition, repo, ref[3], oid),
        ):
            try:
                self.target("acquisition_roots", ident)
                root = self.source_record("acquisition_roots", ident)
                self.project("acquisition_roots", root)
            except Invalid:
                continue
            yield ident, ref, repo

    def pr_candidate(self, record):
        root_id = self.integer(record, "acquisition_id", nullable=True)
        if root_id is None:
            return None
        root = self.target("acquisition_roots", root_id)
        role = self.enum(record, "role", ("head", "base", "merge"))
        fmt = self.enum(record, "object_format", ("sha1", "sha256"))
        oid = self.oid(record, "oid", fmt)
        if (role, fmt, oid) != (root["role"], root["object_format"], root["oid"]):
            raise Invalid("GIT_PR_ROOT_MISMATCH", "acquisition_id")
        code_id = self.integer(record, "code_observation")
        source_code = self.source_record("pr_code_observations", code_id)
        pr_id, observation = (
            self.t(source_code, "pr_id"),
            self.integer(source_code, "observation_id"),
        )
        code = self.target("code_observations", code_id)
        owner = self.target("change_requests", pr_id)
        self.target("change_request_observations", observation)
        source_root = self.source_record("acquisition_roots", root_id)
        number = self.integer(source_root, "pr_number", nullable=True)
        claimed_observation = self.integer(source_root, "observation_id", nullable=True)
        if (
            owner["repo_id"] != root["repo_id"]
            or code["change_request_id"] != pr_id
            or code["observation_id"] != observation
            or number is not None
            and number != owner["number"]
            or claimed_observation is not None
            and claimed_observation != observation
        ):
            raise Invalid("GIT_PR_ROOT_MISMATCH", "observation_id")
        linked = self.db.execute(
            "SELECT root_id FROM code_acquisitions WHERE code_observation_id=? AND role=?",
            (code_id, role),
        ).fetchone()
        if linked is None or linked[0] != root_id:
            raise Invalid("GIT_UNSAFE_DEPENDENCY", "code_acquisitions")
        return root_id, code_id, pr_id, observation, root["repo_id"]

    def origins(self, recipe, record):
        rows = []
        if recipe == "ref_root_origins":
            for ident, ref, repo in self.ref_candidates(record):
                ordinal = self.src.execute(
                    "SELECT count(*) FROM ref_observations WHERE snapshot_id=? AND raw_ref_name<?",
                    (ref[0], ref[1]),
                ).fetchone()[0]
                rows.append(
                    (
                        "root_origins",
                        (
                            origin_id(record, ident, "ref"),
                            ident,
                            "ref",
                            ref[1],
                            ordinal,
                            ref[0],
                            None,
                            None,
                            repo,
                        ),
                        "split",
                    )
                )
        elif recipe == "pr_root_origins":
            candidate = self.pr_candidate(record)
            if candidate is not None:
                root, code, pr, observation, repo = candidate
                ordinal = code if code >= 0 else origin_id(record, root, "ordinal")
                rows.append(
                    (
                        "root_origins",
                        (
                            origin_id(record, root, "pr_role"),
                            root,
                            "pr_role",
                            None,
                            ordinal,
                            None,
                            pr,
                            observation,
                            repo,
                        ),
                        "split",
                    )
                )
        else:
            root_id = self.integer(record, "id")
            root = self.target("acquisition_roots", root_id)
            known = False
            for encoded_snapshot, name in self.src.execute(
                "SELECT CAST(f.snapshot_id AS BLOB),f.raw_ref_name FROM ref_observations f JOIN snapshots s ON s.id=f.snapshot_id WHERE s.run_id=? AND f.object_format=? AND COALESCE(f.peeled_oid,f.target_oid)=?",
                (root["acquisition_id"], root["object_format"], root["oid"]),
            ):
                try:
                    snapshot = encoded_snapshot.decode(self.encoding)
                    ref = self.source_record("ref_observations", snapshot, name)
                    if any(
                        ident == root_id for ident, _, _ in self.ref_candidates(ref)
                    ):
                        known = True
                        break
                except (Invalid, UnicodeError):
                    pass
            if not known:
                for code, encoded_role, oid in self.src.execute(
                    "SELECT code_observation,CAST(role AS BLOB),oid FROM pr_git_links WHERE acquisition_id=?",
                    (root_id,),
                ):
                    try:
                        role = encoded_role.decode(self.encoding)
                        link = self.source_record("pr_git_links", code, role, oid)
                        if self.pr_candidate(link) is not None:
                            known = True
                            break
                    except (Invalid, UnicodeError):
                        pass
            if not known:
                self.issue("ROOT_ORIGIN_UNKNOWN", "id")
                rows.append(
                    (
                        "root_origins",
                        (
                            origin_id(record, root_id, "legacy_unknown"),
                            root_id,
                            "legacy_unknown",
                            None,
                            0,
                            None,
                            None,
                            None,
                            root["repo_id"],
                        ),
                        "split",
                    )
                )
        return rows


def prepare(db, src, run, recipe, index, records, *, encoding="UTF-8", verifying=False):
    """Prepare one bounded batch for the integrated writer and independent audit."""
    context = Context(db, src, run, encoding, verifying=verifying)
    output = {"operations": [], "mappings": [], "diagnostics": [], "decisions": []}
    for record in records:
        context.issues = []
        record_id = context.record_id(record)
        rows = []
        valid = True
        try:
            rows = context.project(recipe, record)
        except Invalid as exc:
            valid = False
            context.issues.append((exc.code, "blocking", exc.column))
        for table, row, relation in rows:
            output["operations"].append(
                {
                    "record_id": record_id,
                    "table": table,
                    "operation": "manifest_completion"
                    if recipe == "root_manifest_completion"
                    else "insert",
                    "row": row,
                }
            )
            output["mappings"].append(
                [
                    record_id,
                    table,
                    target_key(table, row).hex(),
                    relation,
                    f"{VERSION}; {recipe}; exact saved source identity/provenance",
                ]
            )
        output["decisions"].append(
            {
                "record_id": record_id,
                "source_key": record.key.hex(),
                "source_sha256": record.row_sha256.hex(),
                "disposition": "normalized" if valid else "archive_only",
            }
        )
        output["diagnostics"].extend(
            [
                "I31",
                code,
                severity,
                canonical({"record_id": record_id, "column": column, "recipe": recipe}),
            ]
            for code, severity, column in sorted(set(context.issues))
        )
    return output
