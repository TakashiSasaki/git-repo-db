"""Bounded history/tree/path/diff reads over a single pinned Repository snapshot.

Checked intrinsic relations supply canonical topology. Unambiguous attributed
metadata-only relations remain traversable with reported qualification and partial
results; conflicting alternatives never become a selected graph.
"""

from __future__ import annotations

import json

from repo_catalog.application.repository_query import RepositoryQueryService
from repo_catalog.domain.p1_repository import OID
from repo_catalog.domain.query_contracts import QueryError


class GitHistoryQuery(RepositoryQueryService):
    def __init__(self, directory, **kwargs):
        kwargs.setdefault("mode", "repository_only")
        super().__init__(directory, **kwargs)

    def _limit(self, value):
        if type(value) is not int or not 1 <= value <= 100_000:
            raise QueryError("INPUT_LIMIT", "history", "limit must be 1..100000")
        return value

    @staticmethod
    def _members(repository_store, object_oid, relation):
        projection = repository_store.relations(object_oid, relation)
        if projection.canonical is None:
            # Metadata-only catalogs still carry genuine attributed topology.
            # Traverse an unambiguous original while preserving its qualification;
            # do not upgrade it to receiver-intrinsic proof or choose a conflict.
            if projection.reported_conflict:
                return None, projection
            closed = {
                repr(item["membership"]): item
                for item in projection.alternatives
                if item["status"] in ("complete", "known_empty")
            }
            if len(closed) == 1:
                return next(iter(closed.values()))["membership"], projection
            return None, projection
        status, members = projection.canonical
        return members if status in ("complete", "known_empty") else None, projection

    def history(self, start, *, limit=100, first_parent=False):
        self._limit(limit)
        with self.open_snapshot(required_store="repository") as snapshot:
            return self._history(
                snapshot.repository_store, snapshot.token, start, limit, first_parent
            )

    def _history(self, repository_store, token, start, limit, first_parent):
        pending, seen, items, missing, reported = [start], set(), [], [], []
        missing_details = []
        while pending and len(items) < limit:
            object_oid = pending.pop()
            if object_oid.key in seen:
                continue
            seen.add(object_oid.key)
            tree, tree_projection = self._members(
                repository_store, object_oid, "commit_tree"
            )
            parents, parent_projection = self._members(
                repository_store, object_oid, "commit_parents"
            )
            if tree is None or parents is None:
                key = list(object_oid.key)
                missing.append(key)
                incomplete = {
                    name: (
                        "conflicting"
                        if projection.reported_conflict
                        else "incomplete"
                        if projection.canonical is not None or projection.alternatives
                        else "unobserved"
                    )
                    for name, members, projection in (
                        ("commit_tree", tree, tree_projection),
                        ("commit_parents", parents, parent_projection),
                    )
                    if members is None
                }
                missing_details.append(
                    {
                        "object_oid": key,
                        "oid_known": bool(
                            repository_store.sql(
                                "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                                object_oid.key,
                            )
                        ),
                        "relations": incomplete,
                    }
                )
            elif (
                tree_projection.canonical is None or parent_projection.canonical is None
            ):
                reported.append(list(object_oid.key))
            items.append(
                {
                    "object_oid": list(object_oid.key),
                    "tree": tree_projection,
                    "parents": parent_projection,
                    "message": repository_store.scalar(object_oid, "message"),
                    "author": repository_store.scalar(object_oid, "author"),
                    "committer_time_us": repository_store.scalar(
                        object_oid, "committer_time_us"
                    ),
                }
            )
            if parents is not None:
                selected = parents[:1] if first_parent else parents
                pending.extend(
                    OID(member[1], member[2]) for member in reversed(selected)
                )
        return {
            "items": items,
            "missing": missing,
            "missing_details": missing_details,
            "reported_topology": reported,
            "has_more": bool(pending),
            "status": "partial" if missing or pending or reported else "complete",
            "snapshot_token": token.encode(),
        }

    def _tree_oid(self, repository_store, object_oid):
        kind = repository_store.scalar(object_oid, "type").canonical
        if kind == ["known", "tree"]:
            return object_oid
        if kind is None:
            projection = repository_store.scalar(object_oid, "type")
            values = {repr(item["value"]) for item in projection.alternatives}
            if not projection.reported_conflict and values == {repr(["known", "tree"])}:
                return object_oid
        members, _ = self._members(repository_store, object_oid, "commit_tree")
        return OID(members[0][1], members[0][2]) if members else None

    def _tree(self, repository_store, start, *, max_entries, recursive):
        root = self._tree_oid(repository_store, start)
        if root is None:
            return [], [list(start.key)], False, []
        pending, entries, missing, reported = [(b"", root, frozenset())], [], [], []
        while pending:
            prefix, object_oid, ancestors = pending.pop()
            if object_oid.key in ancestors:
                raise QueryError(
                    "INVALID_TOPOLOGY", "tree", "cycle in intrinsic tree graph"
                )
            members, projection = self._members(
                repository_store, object_oid, "tree_entries"
            )
            if members is None:
                missing.append(list(object_oid.key))
                continue
            if projection.canonical is None:
                reported.append(list(object_oid.key))
            names = self._decoded_names(repository_store, object_oid)
            for member in members:
                if len(entries) >= max_entries:
                    return entries, missing, True, reported
                (mode, name_hex), fmt, target = member
                raw_path = prefix + bytes.fromhex(name_hex)
                entries.append(
                    {
                        "path": raw_path,
                        "mode": mode,
                        "object_format": fmt,
                        "object_oid": target,
                        "qualification": "receiver_intrinsic"
                        if projection.canonical is not None
                        else "reported",
                        **names.get(
                            name_hex,
                            {
                                "decoded_name": None,
                                "decoder_conflict": False,
                                "decoded_name_candidates": [],
                            },
                        ),
                    }
                )
                if recursive and mode in ("40000", "040000"):
                    pending.append(
                        (
                            raw_path + b"/",
                            OID(fmt, target),
                            ancestors | {object_oid.key},
                        )
                    )
        return entries, missing, False, reported

    @staticmethod
    def _decoded_names(repository_store, object_oid):
        # Pair actual entry bytes, decoded value and settings by their complete
        # original provenance. Tree-wide scalar conflicts cannot pair one name
        # with another entry's decoder or select a preferred producer.
        paired = {}
        for field in ("raw_name_hex", "decoded_name", "decoder_settings"):
            for item in repository_store.scalar(object_oid, field).alternatives:
                if item["value"][0] != "known":
                    continue
                key = tuple(item["provenance"])
                paired.setdefault(key, {}).setdefault(field, set()).add(
                    item["value"][1]
                )
        names = {}
        for original, fields in paired.items():
            if set(fields) != {
                "raw_name_hex",
                "decoded_name",
                "decoder_settings",
            } or any(len(values) != 1 for values in fields.values()):
                continue
            (raw_hex,) = fields["raw_name_hex"]
            (decoded,) = fields["decoded_name"]
            (encoded_settings,) = fields["decoder_settings"]
            try:
                settings = json.loads(encoded_settings)
                encoding, errors = (
                    settings["metadata_encoding"],
                    settings["metadata_errors"],
                )
                if (
                    encoding not in ("utf-8", "latin-1")
                    or errors
                    not in ("strict", "replace", "backslashreplace", "surrogateescape")
                    or bytes.fromhex(raw_hex).decode(encoding, errors) != decoded
                ):
                    continue
            except (ValueError, TypeError, KeyError, LookupError):
                continue
            names.setdefault(raw_hex, []).append(
                {
                    "decoded_name": decoded,
                    "decoder_settings": settings,
                    "provenance": list(original),
                    "qualification": "reported",
                }
            )
        result = {}
        for raw_hex, candidates in names.items():
            values = {item["decoded_name"] for item in candidates}
            result[raw_hex] = {
                "decoded_name": next(iter(values)) if len(values) == 1 else None,
                "decoder_conflict": len(values) > 1,
                "decoded_name_candidates": candidates,
            }
        return result

    def tree(self, start, *, max_entries=1000, recursive=False, path=None):
        self._limit(max_entries)
        with self.open_snapshot(required_store="repository") as snapshot:
            entries, missing, limited, reported = self._tree(
                snapshot.repository_store,
                start,
                max_entries=max_entries,
                recursive=recursive or path is not None,
            )
            if path is not None:
                entries = [entry for entry in entries if entry["path"] == path]
            return {
                "items": entries,
                "missing": missing,
                "limited": limited,
                "reported_topology": reported,
                "status": "partial" if missing or limited or reported else "complete",
                "snapshot_token": snapshot.token.encode(),
            }

    def diff(self, left, right, *, max_entries=1000):
        self._limit(max_entries)
        with self.open_snapshot(required_store="repository") as snapshot:
            l_items, l_missing, l_limit, l_reported = self._tree(
                snapshot.repository_store, left, max_entries=max_entries, recursive=True
            )
            r_items, r_missing, r_limit, r_reported = self._tree(
                snapshot.repository_store,
                right,
                max_entries=max_entries,
                recursive=True,
            )
            l_map = {item["path"]: item for item in l_items}
            r_map = {item["path"]: item for item in r_items}
            complete = not (
                l_missing or r_missing or l_limit or r_limit or l_reported or r_reported
            )
            changes = []
            for path in sorted(l_map.keys() | r_map.keys()):
                before, after = l_map.get(path), r_map.get(path)
                if before != after:
                    changes.append(
                        {
                            "path": path,
                            "before": before,
                            "after": after,
                            "kind": "modified"
                            if before and after
                            else ("added" if after else "deleted")
                            if complete
                            else "unknown",
                        }
                    )
            return {
                "items": changes,
                "missing": l_missing + r_missing,
                "status": "complete" if complete else "partial",
                "snapshot_token": snapshot.token.encode(),
            }

    def compare(self, left, right, *, selection="symmetric", limit=1000):
        if selection not in ("left-only", "right-only", "common", "symmetric"):
            raise ValueError("unknown commit set selection")
        left_result = self.history(left, limit=limit)
        right_result = self.history(right, limit=limit)
        if left_result["snapshot_token"] != right_result["snapshot_token"]:
            raise QueryError(
                "STALE_SNAPSHOT", "compare", "Repository changed during comparison"
            )
        left_keys = {tuple(item["object_oid"]) for item in left_result["items"]}
        right_keys = {tuple(item["object_oid"]) for item in right_result["items"]}
        selected = {
            "left-only": left_keys - right_keys,
            "right-only": right_keys - left_keys,
            "common": left_keys & right_keys,
            "symmetric": left_keys ^ right_keys,
        }[selection]
        complete = left_result["status"] == right_result["status"] == "complete"
        # Missing ancestry cannot establish a negative set membership claim.
        return {
            "items": [list(key) for key in sorted(selected)]
            if complete or selection == "common"
            else [],
            "observed_candidates": [list(key) for key in sorted(selected)],
            "status": "complete" if complete else "partial",
            "snapshot_token": left_result["snapshot_token"],
        }

    def path_history(self, start, path, *, limit=100, max_entries=1000):
        self._limit(limit)
        self._limit(max_entries)
        # One pinned snapshot and its one SQLite work budget cover the whole
        # graph/path query; many commits cannot reset validation/read work.
        max_entries = min(max_entries, max(1, 100_000 // limit))
        with self.open_snapshot(required_store="repository") as snapshot:
            history = self._history(
                snapshot.repository_store, snapshot.token, start, limit, False
            )
            items = []
            partial = history["status"] != "complete"
            for commit in history["items"]:
                entries, missing, limited, reported = self._tree(
                    snapshot.repository_store,
                    OID(*commit["object_oid"]),
                    max_entries=max_entries,
                    recursive=True,
                )
                status = "partial" if missing or limited or reported else "complete"
                partial |= status != "complete"
                items.append(
                    {
                        "commit": commit,
                        "path_entries": [
                            entry for entry in entries if entry["path"] == path
                        ],
                        "status": status,
                    }
                )
            return {
                "items": items,
                "status": "partial" if partial else "complete",
                "snapshot_token": snapshot.token.encode(),
            }

    def digest(self, algorithm, digest, *, byte_length=None, limit=1000):
        """Inspect actual retained metadata bytes; never infer digests from an OID."""
        import hashlib
        import re

        self._limit(limit)
        names = {
            "raw-md5": ("md5", 32),
            "raw-sha1": ("sha1", 40),
            "raw-sha256": ("sha256", 64),
        }
        if algorithm not in names:
            raise ValueError("unsupported byte digest algorithm")
        name, width = names[algorithm]
        if (
            type(digest) is not str
            or re.fullmatch("[0-9a-f]{" + str(width) + "}", digest) is None
        ):
            raise ValueError("canonical lowercase hex digest required")
        if byte_length is not None and (
            type(byte_length) is not int or byte_length < 0
        ):
            raise ValueError("nonnegative byte length required")
        with self.open_snapshot(required_store="repository") as snapshot:
            rows = snapshot.repository_store.sql(
                "SELECT DISTINCT object_format,object_oid FROM retained_metadata ORDER BY object_format,object_oid LIMIT ?",
                (limit + 1,),
            )
            matches = []
            for row in rows[:limit]:
                object_oid = OID(row[0], row[1])
                body = snapshot.repository_store.read_metadata(object_oid)
                actual = hashlib.new(name, body, usedforsecurity=False).hexdigest()
                if actual == digest and (
                    byte_length is None or byte_length == len(body)
                ):
                    matches.append(
                        {
                            "object_oid": list(object_oid.key),
                            "algorithm": algorithm,
                            "digest": actual,
                            "byte_length": len(body),
                            "verified": True,
                        }
                    )
            return {
                "items": matches,
                "scanned_count": min(len(rows), limit),
                "status": "partial" if len(rows) > limit else "complete",
                "snapshot_token": snapshot.token.encode(),
            }
