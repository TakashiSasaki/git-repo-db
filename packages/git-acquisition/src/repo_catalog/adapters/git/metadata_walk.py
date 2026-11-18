"""Bounded native commit/tree discovery; ordinary blob bodies are never read."""

from dataclasses import dataclass

from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.domain.p1_repository import OID, RepositoryFailure


@dataclass(frozen=True)
class NativeMetadataWalk:
    """Trusted body-free immutable-root selection, derived only during actual work."""

    source: object
    roots: tuple[OID, ...]
    max_objects: int = 100_000

    def intent(self, source, roots):
        if self.source is not source or self.roots != roots:
            raise RepositoryFailure(
                "REQUEST", "metadata-walk", "exact original source/roots required"
            )
        if type(self.max_objects) is not int or not 0 < self.max_objects <= 100_000:
            raise RepositoryFailure("REQUEST", "metadata-walk", "finite object count")
        return ["native-metadata-closure", 1, self.max_objects]

    def discover(self, work):
        return metadata_object_oids(
            self.source, self.roots, work, max_objects=self.max_objects
        )


def metadata_object_oids(source, roots, work, *, max_objects=100_000):
    if (
        type(max_objects) is not int
        or not 0 < max_objects <= 100_000
        or type(roots) is not tuple
        or not roots
        or len(roots) > max_objects
        or any(
            type(oid) is not OID or oid.object_format != source.object_format
            for oid in roots
        )
    ):
        raise RepositoryFailure(
            "REQUEST", "metadata-walk", "bounded typed native roots required"
        )
    # The existing native output port prepays real bytes and finite process work
    # before reading each chunk. Git's blob filter excludes ordinary file data.
    width = 40 if source.object_format == "sha1" else 64
    body = GitNotesSource(source)._output(
        (
            "rev-list",
            "--objects",
            "--filter=blob:none",
            "--no-object-names",
            "--missing=print",
            *(oid.object_oid for oid in roots),
            "--",
        ),
        max_objects * (width + 2),
        work,
    )
    result, missing = [], []
    for line in body.splitlines():
        work.require("metadata_units", 1)
        work.charge("metadata_units", 1)
        if len(result) + len(missing) >= max_objects:
            raise RepositoryFailure("BUDGET", "metadata-walk", "finite object count")
        absent = line.startswith(b"?")
        raw = line[1:] if absent else line
        try:
            oid = OID(source.object_format, raw.decode("ascii"))
        except (UnicodeError, ValueError, TypeError) as error:
            raise RepositoryFailure(
                "GIT_INPUT", "metadata-walk", "invalid native OID"
            ) from error
        (missing if absent else result).append(oid)
    if len(set(result)) != len(result) or len(set(missing)) != len(missing):
        raise RepositoryFailure("GIT_INPUT", "metadata-walk", "duplicate native OID")
    if not set(roots) <= set(result) | set(missing):
        raise RepositoryFailure("GIT_INPUT", "metadata-walk", "native root omitted")
    return tuple(result), tuple(missing)
