"""Compatibility facade for independently selected acquisition capabilities.

Resolve each public capability only when requested; implementation ownership stays
in the corresponding Git, Provider or paired module.
"""

from importlib import import_module

_EXPORTS = {
    "_charge": "repo_catalog.application.git_acquisition",
    "_PreparedCore": "repo_catalog.application.git_acquisition",
    "_finish_ref_inventories": "repo_catalog.application.git_acquisition",
    "_defer_ref_work": "repo_catalog.application.git_acquisition",
    "_open_core": "repo_catalog.application.git_acquisition",
    "_open_operational": "repo_catalog.application.git_acquisition",
    "GitAcquisition": "repo_catalog.application.git_acquisition",
    "ProviderAcquisition": "repo_catalog.application.provider_acquisition",
    "_reconcile_context_dependencies_in_tx": "repo_catalog.application.paired_acquisition",
    "PairedAcquisitionCoordinator": "repo_catalog.application.paired_acquisition",
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
