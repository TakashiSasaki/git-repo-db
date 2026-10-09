"""Offline reanalysis of retained Git domain content.

HTTP responses are optional transport diagnostics. They cannot be reparsed into
historical domain observations through the core, even if a legacy path still
retains an original response while its replacement contracts are deferred.
"""

from repo_catalog.domain.models import CatalogError


class ParsingService:
    def __init__(self, store):
        self.s = store

    def reparse(self, git_acquisition_id, *, select=False, profile_uuid=None):
        """Decode Git content without manufacturing another remote acquisition.

        Git's existing interpretation and explicit-selection behavior remains
        the implementation baseline pending its separate lifecycle decision.
        """
        if not self.s.one(
            "SELECT 1 FROM git_acquisitions WHERE git_acquisition_id=?",
            (git_acquisition_id,),
        ):
            raise CatalogError(
                "PARSER_UNSUPPORTED_INPUT",
                "Core reparse requires a retained Git acquisition; API response replay is retired",
            )
        from repo_catalog.adapters.git.parsing import reparse_git

        return reparse_git(
            self.s,
            git_acquisition_id,
            select=select,
            profile_uuid=profile_uuid,
        )
