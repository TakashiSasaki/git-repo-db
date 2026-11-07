"""Compatibility exports for acquisition public values.

Resolve each public capability only when requested; implementation ownership stays
in the corresponding Git, Provider or paired module.
"""

from importlib import import_module

_EXPORTS = {
    "AcquisitionError": "repo_catalog.domain.acquisition_errors",
    "RefNotesInput": "repo_catalog.domain.git_acquisition",
    "NotesAcquisitionSpec": "repo_catalog.domain.git_acquisition",
    "GitMetadataInput": "repo_catalog.domain.git_acquisition",
    "GitNativeAcquisitionRequest": "repo_catalog.domain.git_acquisition",
    "GitAcquisitionReport": "repo_catalog.domain.git_acquisition",
    "ProviderRegistration": "repo_catalog.domain.provider_acquisition",
    "RepositoryRegistration": "repo_catalog.domain.provider_acquisition",
    "SourceRegistration": "repo_catalog.domain.provider_acquisition",
    "ProviderIssueIntake": "repo_catalog.domain.provider_acquisition",
    "ProviderPullRequestIntake": "repo_catalog.domain.provider_acquisition",
    "ProviderReviewIntake": "repo_catalog.domain.provider_acquisition",
    "ProviderReviewThreadIntake": "repo_catalog.domain.provider_acquisition",
    "ProviderReviewCommentIntake": "repo_catalog.domain.provider_acquisition",
    "ProviderIssueCommentIntake": "repo_catalog.domain.provider_acquisition",
    "ProviderTimelineIntake": "repo_catalog.domain.provider_acquisition",
    "ProviderRepositoryIntake": "repo_catalog.domain.provider_acquisition",
    "ProviderCommitContextIntake": "repo_catalog.domain.provider_acquisition",
    "ProviderFileContextIntake": "repo_catalog.domain.provider_acquisition",
    "DetachedResourceTransfer": "repo_catalog.domain.provider_acquisition",
    "ProviderIntakeBatch": "repo_catalog.domain.provider_acquisition",
    "ProviderAcquisitionReport": "repo_catalog.domain.provider_acquisition",
    "DependencyReconciliationReport": "repo_catalog.domain.provider_acquisition",
    "make_provenance": "repo_catalog.domain.provider_acquisition",
    "PairedAcquisitionResult": "repo_catalog.domain.paired_acquisition",
}
__all__ = [name for name in _EXPORTS if not name.startswith("_")]


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
