"""Typed results of explicit paired acquisition."""

from __future__ import annotations

from dataclasses import dataclass

from repo_catalog.domain.git_acquisition import GitAcquisitionReport
from repo_catalog.domain.p1_coordination import PairAdmission
from repo_catalog.domain.provider_acquisition import ProviderAcquisitionReport


@dataclass(frozen=True)
class PairedAcquisitionResult:
    """Result of coordinated Core-first + Context-second admission."""

    admission: PairAdmission
    git_report: GitAcquisitionReport | None = None
    provider_report: ProviderAcquisitionReport | None = None
