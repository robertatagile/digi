"""Legislation as a controlled object (ADR-009, docs/13).

A platform legislation library holds versioned, effective-dated obligations.
A tenant obligation register binds each applicable obligation to a kernel control,
a pack rule or an attested manual procedure, or justifies why it does not apply.
The coverage gate refuses a pack release while an applicable in-force obligation is unbound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from .controls import Approval, ControlError, require_approvals

OBLIGATION_TYPES = ("gate", "limit", "record", "report", "disclosure", "timing", "attestation")


@dataclass(frozen=True)
class Obligation:
    id: str
    legislation: str  # e.g. "FICA", "FAIS", "COFI", "FSR", "CISCA"
    ref: str  # section or standard reference
    requirement: str
    type: str
    applies_to: tuple[str, ...]  # tenant types: "manco", "lisp"
    source: str

    def __post_init__(self) -> None:
        if self.type not in OBLIGATION_TYPES:
            raise ControlError(f"unknown obligation type {self.type!r}")
        if not self.source:
            raise ControlError(f"obligation {self.id} needs a source (ADR-008)")


@dataclass(frozen=True)
class LegislationVersion:
    legislation: str
    version: int
    effective_from: date
    status: str  # "in_force" or "pending"
    obligations: tuple[Obligation, ...]
    source: str
    approvers: tuple[str, ...]


class LegislationLibrary:
    """Platform owned. Versions are appended, never edited. Two approvers, neither the maker."""

    def __init__(self) -> None:
        self._versions: list[LegislationVersion] = []

    def publish(
        self,
        *,
        legislation: str,
        effective_from: date,
        status: str,
        obligations: Iterable[Obligation],
        source: str,
        maker: str,
        approvals: Iterable[Approval],
    ) -> LegislationVersion:
        if status not in ("in_force", "pending"):
            raise ControlError(f"unknown legislation status {status!r}")
        if not source:
            raise ControlError("a legislation version needs a source, for example a Gazette number")
        approvals = require_approvals(maker, approvals, minimum=2)
        obligations = tuple(obligations)
        for o in obligations:
            if o.legislation != legislation:
                raise ControlError(f"obligation {o.id} belongs to {o.legislation}, not {legislation}")
        existing = [v for v in self._versions if v.legislation == legislation]
        version = LegislationVersion(
            legislation=legislation,
            version=len(existing) + 1,
            effective_from=effective_from,
            status=status,
            obligations=obligations,
            source=source,
            approvers=tuple(a.actor for a in approvals),
        )
        self._versions.append(version)
        return version

    def versions(self, legislation: str) -> list[LegislationVersion]:
        return [v for v in self._versions if v.legislation == legislation]

    def current(self, legislation: str, *, as_at: date) -> Optional[LegislationVersion]:
        """The latest version effective on or before `as_at`."""
        pool = [v for v in self.versions(legislation) if v.effective_from <= as_at]
        return pool[-1] if pool else None

    def applicable(self, *, tenant_type: str, as_at: date) -> list[Obligation]:
        """In-force obligations for a tenant type as at a date, from each instrument's current version."""
        result: list[Obligation] = []
        for legislation in sorted({v.legislation for v in self._versions}):
            current = self.current(legislation, as_at=as_at)
            if current is None or current.status != "in_force":
                continue
            result.extend(o for o in current.obligations if tenant_type in o.applies_to)
        return result

    def pending(self, *, tenant_type: str, as_at: date) -> list[tuple[Obligation, date]]:
        """Obligations that will apply later and do not apply yet.

        Either the instrument's latest version is still pending (COFI today), or it is in force
        from a future date (an amendment). Obligations already applicable now are left out.
        """
        applicable_now = {o.id for o in self.applicable(tenant_type=tenant_type, as_at=as_at)}
        result: list[tuple[Obligation, date]] = []
        for legislation in sorted({v.legislation for v in self._versions}):
            latest = self.versions(legislation)[-1]
            if latest.status == "pending" or latest.effective_from > as_at:
                result.extend(
                    (o, latest.effective_from)
                    for o in latest.obligations
                    if tenant_type in o.applies_to and o.id not in applicable_now
                )
        return result


@dataclass(frozen=True)
class Binding:
    obligation_id: str
    owner_role: str
    implementations: tuple[str, ...] = ()  # "kernel:...", "pack:...", "manual:..."
    not_applicable_reason: Optional[str] = None
    approvers: tuple[str, ...] = ()

    @property
    def is_exclusion(self) -> bool:
        return self.not_applicable_reason is not None


@dataclass(frozen=True)
class CoverageReport:
    as_at: date
    covered: tuple[str, ...]
    excluded: tuple[str, ...]
    gaps: tuple[str, ...]
    pending: tuple[tuple[str, date], ...]

    @property
    def complete(self) -> bool:
        return not self.gaps


class ObligationRegister:
    """Tenant owned. The manco binds, attests and justifies. It cannot remove a library obligation."""

    def __init__(self, tenant: str, tenant_type: str) -> None:
        self.tenant = tenant
        self.tenant_type = tenant_type
        self._bindings: dict[str, Binding] = {}

    def bind(self, *, obligation_id: str, owner_role: str, implementations: Iterable[str]) -> Binding:
        implementations = tuple(implementations)
        if not implementations:
            raise ControlError(f"a binding for {obligation_id} needs at least one implementation")
        for impl in implementations:
            if not impl.startswith(("kernel:", "pack:", "manual:", "calendar:")):
                raise ControlError(f"implementation {impl!r} must be kernel:, pack:, manual: or calendar:")
        binding = Binding(obligation_id=obligation_id, owner_role=owner_role, implementations=implementations)
        self._bindings[obligation_id] = binding
        return binding

    def exclude(self, *, obligation_id: str, reason: str, maker: str, approvals: Iterable[Approval]) -> Binding:
        """Not applicable is a decision with a reason and two approvers. Never a deletion."""
        if not reason.strip():
            raise ControlError("a not-applicable decision needs a reason")
        approvals = require_approvals(maker, approvals, minimum=2)
        binding = Binding(
            obligation_id=obligation_id,
            owner_role="head_of_compliance",
            not_applicable_reason=reason,
            approvers=tuple(a.actor for a in approvals),
        )
        self._bindings[obligation_id] = binding
        return binding

    def binding(self, obligation_id: str) -> Optional[Binding]:
        return self._bindings.get(obligation_id)

    def coverage(self, library: LegislationLibrary, *, as_at: date) -> CoverageReport:
        covered: list[str] = []
        excluded: list[str] = []
        gaps: list[str] = []
        for obligation in library.applicable(tenant_type=self.tenant_type, as_at=as_at):
            binding = self._bindings.get(obligation.id)
            if binding is None:
                gaps.append(obligation.id)
            elif binding.is_exclusion:
                excluded.append(obligation.id)
            else:
                covered.append(obligation.id)
        pending = tuple((o.id, when) for o, when in library.pending(tenant_type=self.tenant_type, as_at=as_at))
        return CoverageReport(as_at, tuple(covered), tuple(excluded), tuple(gaps), pending)

    def release_gate(self, library: LegislationLibrary, *, as_at: date) -> CoverageReport:
        """The pack validator calls this. Gaps block the release."""
        report = self.coverage(library, as_at=as_at)
        if report.gaps:
            raise ControlError(
                f"pack release blocked for {self.tenant}: unbound obligations {', '.join(report.gaps)} (C11)"
            )
        return report
