"""Carrier qualification — where the substrate earns its keep operationally.

This is where brokerages actually take losses: double-brokering, cargo
theft, cloned carrier identities, lapsed or insufficient insurance, and
carriers operating without authority. A single bad load can exceed a
quarter of contribution, which makes this the first place the evidence
machinery is protecting money rather than a report.

FOUR OUTCOMES, NOT A BOOLEAN. The dangerous one is the third.

    ELIGIBLE            every check passed, and each names its source
    NOT_ELIGIBLE        a check FAILED on evidence
    ELIGIBLE_PENDING    a check will pass once a named thing is supplied
    CANNOT_DETERMINE    a check could not be run at all

A boolean gate collapses CANNOT_DETERMINE into whichever neighbour it
happens to fail towards: fail-closed and an unreachable registry looks
like a fraudulent carrier; fail-open and it looks like a clean one. Both
are wrong in the same way -- the system reports a fact about the carrier
when the observable was a fact about the CHECK. That is class 7 in the
place where it costs money.

AN INSURANCE CERTIFICATE IS A validWhile PREDICATE. It is valid until a
date, for a coverage amount, from a named insurer, and it is verifiable
with the insurer rather than with the carrier. A certificate valid when
you booked and lapsed before pickup is exactly the knownAt-versus-period
distinction, and getting it wrong is a liability rather than a reporting
error -- so `covers()` takes the WHOLE period of the movement, not the
instant of booking.

DOUBLE-BROKERING IS A DIVERGENCE. The carrier you tendered to and the
carrier named on the bill of lading are two claims about one movement.
That is the mirror-statistics shape, and a persistent directional gap for
one carrier is a finding the classifier already knows how to surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

ELIGIBLE = "ELIGIBLE"
NOT_ELIGIBLE = "NOT_ELIGIBLE"
ELIGIBLE_PENDING = "ELIGIBLE_PENDING"
CANNOT_DETERMINE = "CANNOT_DETERMINE"

#: How a fact about a carrier was come by. The distinction the EDGAR work
#: raised: who is asserting this, and do they have an interest in it.
REGULATOR_PUBLISHED = "regulator_published"
INSURER_CONFIRMED = "insurer_confirmed"
BROKER_NOTE = "broker_note"
CARRIER_SELF_ASSERTED = "carrier_self_asserted"

#: The evidence class each attestation route maps to. Declared here as a
#: local mapping and NOT as a redefinition of the repository's ingest
#: vocabulary: `commerce/` may not import `epistemics`, so it names the
#: route and the class it claims, and lets the owning layer judge.
CLASS_OF_ROUTE: Mapping[str, str] = {
    REGULATOR_PUBLISHED: "measured",
    INSURER_CONFIRMED: "measured",
    BROKER_NOTE: "asserted",
    CARRIER_SELF_ASSERTED: "asserted",
}

#: Routes that may satisfy a check on their own. A carrier's word about
#: its own insurance is not evidence of insurance; it is evidence of what
#: the carrier says.
INDEPENDENT_ROUTES = frozenset({REGULATOR_PUBLISHED, INSURER_CONFIRMED})

CERTIFICATE_NOT_SUPPLIED = "CERTIFICATE_NOT_SUPPLIED"
CERTIFICATE_LAPSES_INSIDE_THE_MOVEMENT = "CERTIFICATE_LAPSES_INSIDE_THE_MOVEMENT"
COVERAGE_BELOW_THE_REQUIREMENT = "COVERAGE_BELOW_THE_REQUIREMENT"
ATTESTED_ONLY_BY_THE_CARRIER = "ATTESTED_ONLY_BY_THE_CARRIER"
AUTHORITY_NOT_ON_FILE = "AUTHORITY_NOT_ON_FILE"
AUTHORITY_REVOKED_BY_THE_REGULATOR = "AUTHORITY_REVOKED_BY_THE_REGULATOR"
REGISTRY_UNREACHABLE = "REGISTRY_UNREACHABLE"
CARRIER_CLAIM_CONTRADICTS_THE_REGULATOR = "CARRIER_CLAIM_CONTRADICTS_THE_REGULATOR"
BILL_OF_LADING_NAMES_A_DIFFERENT_CARRIER = "BILL_OF_LADING_NAMES_A_DIFFERENT_CARRIER"

#: Class 7 on a vetting run.
NO_CHECKS_BECAUSE_NONE_WERE_REQUIRED = "NO_CHECKS_BECAUSE_NONE_WERE_REQUIRED"
NO_CHECKS_BECAUSE_NO_EVIDENCE_WAS_SUPPLIED = "NO_CHECKS_BECAUSE_NO_EVIDENCE_WAS_SUPPLIED"


@dataclass(frozen=True)
class Attestation:
    """A fact about a carrier, and who says so."""

    route: str
    observed_at: str
    detail: str = ""

    @property
    def evidence_class(self) -> str:
        return CLASS_OF_ROUTE.get(self.route, "asserted")

    @property
    def independent(self) -> bool:
        return self.route in INDEPENDENT_ROUTES


@dataclass(frozen=True)
class InsuranceCertificate:
    """A validWhile predicate with money attached."""

    insurer: str
    coverage: float
    currency: str
    valid_from: str
    valid_until: str
    attestation: Attestation

    def covers(self, period_start: str, period_end: str) -> bool:
        """The WHOLE movement, not the booking instant.

        A certificate valid on the day you booked and lapsed before pickup
        is the failure this signature exists to make impossible to write
        by accident: there is no way to ask this object about a single
        date.
        """
        return self.valid_from <= period_start and period_end <= self.valid_until


@dataclass(frozen=True)
class AuthorityStatus:
    """What the regulator publishes, and separately what the carrier says."""

    active: Optional[bool]
    attestation: Attestation


@dataclass(frozen=True)
class Check:
    name: str
    outcome: str
    code: Optional[str] = None
    detail: str = ""
    remedy: Optional[str] = None

    @property
    def blocking(self) -> bool:
        return self.outcome in (NOT_ELIGIBLE, CANNOT_DETERMINE)


@dataclass(frozen=True)
class Vetting:
    carrier: str
    outcome: str
    checks: Tuple[Check, ...]
    empty_because: Optional[str] = None

    @property
    def failures(self) -> Tuple[Check, ...]:
        return tuple(c for c in self.checks if c.outcome == NOT_ELIGIBLE)

    @property
    def undetermined(self) -> Tuple[Check, ...]:
        return tuple(c for c in self.checks if c.outcome == CANNOT_DETERMINE)

    @property
    def pending(self) -> Tuple[Check, ...]:
        return tuple(c for c in self.checks if c.outcome == ELIGIBLE_PENDING)


def check_insurance(certificate: Optional[InsuranceCertificate], *, required: float,
                    currency: str, period_start: str, period_end: str) -> Check:
    if certificate is None:
        return Check("insurance", ELIGIBLE_PENDING, CERTIFICATE_NOT_SUPPLIED,
                     "no certificate on file for this movement.",
                     "obtain a certificate of insurance naming the movement's dates, confirmed "
                     "with the insurer rather than forwarded by the carrier.")
    if not certificate.attestation.independent:
        return Check("insurance", CANNOT_DETERMINE, ATTESTED_ONLY_BY_THE_CARRIER,
                     f"the certificate is attested by {certificate.attestation.route!r}. A "
                     "carrier's word about its own insurance is evidence of what the carrier "
                     "says, not of coverage — and a cloned identity forwards a real document.",
                     "confirm the policy number directly with the named insurer.")
    if certificate.currency != currency:
        return Check("insurance", CANNOT_DETERMINE, "COVERAGE_IN_ANOTHER_CURRENCY",
                     f"coverage is {certificate.coverage} {certificate.currency} against a "
                     f"requirement in {currency}; comparing them needs a rate and a date.",
                     f"restate the requirement in {certificate.currency}, or convert at a stated "
                     "rate and date.")
    if certificate.coverage < required:
        return Check("insurance", NOT_ELIGIBLE, COVERAGE_BELOW_THE_REQUIREMENT,
                     f"{certificate.coverage} {certificate.currency} against a requirement of "
                     f"{required}.",
                     "raise the coverage or reduce the cargo value on this movement.")
    if not certificate.covers(period_start, period_end):
        return Check("insurance", NOT_ELIGIBLE, CERTIFICATE_LAPSES_INSIDE_THE_MOVEMENT,
                     f"valid {certificate.valid_from}..{certificate.valid_until} against a "
                     f"movement running {period_start}..{period_end}. Valid at booking is not "
                     "valid at delivery, and the gap is a liability rather than a reporting error.",
                     "obtain a renewed certificate covering the delivery date before tendering.")
    return Check("insurance", ELIGIBLE, detail=f"{certificate.coverage} {certificate.currency} "
                                               f"from {certificate.insurer}, "
                                               f"{certificate.attestation.route}")


def check_authority(status: Optional[AuthorityStatus],
                    carrier_claim: Optional[bool] = None) -> Check:
    if status is None:
        return Check("authority", CANNOT_DETERMINE, REGISTRY_UNREACHABLE,
                     "the regulator's register could not be read, so nothing is known about this "
                     "carrier's authority. This is a fact about the CHECK: it is not evidence "
                     "that authority is absent, and it is not evidence that it is present.",
                     "retry the register, or obtain a dated printout from the regulator.")
    if status.active is None:
        return Check("authority", CANNOT_DETERMINE, AUTHORITY_NOT_ON_FILE,
                     "the register answered and holds no record under this identity. A carrier "
                     "absent from the register and a carrier revoked by it are different, and a "
                     "cloned identity presents as the first.",
                     "confirm the legal name and registration number against the carrier's own "
                     "operating authority document.")
    if status.active is False:
        return Check("authority", NOT_ELIGIBLE, AUTHORITY_REVOKED_BY_THE_REGULATOR,
                     f"the register reports authority inactive as at {status.attestation.observed_at}.",
                     "do not tender. Reinstatement is the carrier's to obtain and to evidence.")
    if carrier_claim is not None and carrier_claim != status.active:
        return Check("authority", NOT_ELIGIBLE, CARRIER_CLAIM_CONTRADICTS_THE_REGULATOR,
                     f"the carrier asserts {carrier_claim} and the register publishes "
                     f"{status.active}. A divergence between an interested party's claim and a "
                     "regulator's publication is a first-class finding, not a data-entry note.",
                     "resolve with the regulator before tendering; record the divergence either way.")
    return Check("authority", ELIGIBLE,
                 detail=f"active per {status.attestation.route} at {status.attestation.observed_at}")


def vet(carrier: str, checks: Sequence[Check]) -> Vetting:
    """Combine checks WITHOUT collapsing the third state.

    Order matters and is deliberate: a real failure outranks an
    undetermined check, because a carrier the register says is revoked is
    not made ambiguous by a second check that could not run.
    """
    checks = tuple(checks)
    if not checks:
        return Vetting(carrier, CANNOT_DETERMINE, (),
                       empty_because=(f"{NO_CHECKS_BECAUSE_NONE_WERE_REQUIRED}: no check was run, "
                                      "so this carrier is not vetted. An empty check list reads "
                                      "as a clean sheet and is the opposite of one."))
    if any(c.outcome == NOT_ELIGIBLE for c in checks):
        outcome = NOT_ELIGIBLE
    elif any(c.outcome == CANNOT_DETERMINE for c in checks):
        outcome = CANNOT_DETERMINE
    elif any(c.outcome == ELIGIBLE_PENDING for c in checks):
        outcome = ELIGIBLE_PENDING
    else:
        outcome = ELIGIBLE
    return Vetting(carrier, outcome, checks)


@dataclass(frozen=True)
class BrokeringDivergence:
    """Tendered-to versus named-on-the-bill-of-lading."""

    movement: str
    tendered_to: str
    bill_of_lading_names: str
    diverges: bool
    finding: Optional[str] = None


def check_double_brokering(movement: str, tendered_to: str,
                           bill_of_lading_names: Optional[str]) -> BrokeringDivergence:
    if not bill_of_lading_names:
        return BrokeringDivergence(
            movement, tendered_to, "", diverges=False,
            finding=("BILL_OF_LADING_NOT_SEEN: no bill of lading was captured for this movement, "
                     "so the carrier that actually moved it is unknown. This is not agreement "
                     "between the two claims; it is one claim."))
    if bill_of_lading_names != tendered_to:
        return BrokeringDivergence(
            movement, tendered_to, bill_of_lading_names, diverges=True,
            finding=(f"{BILL_OF_LADING_NAMES_A_DIFFERENT_CARRIER}: tendered to "
                     f"{tendered_to!r}, moved by {bill_of_lading_names!r}. Two claims about one "
                     "movement. A single instance may be a legitimate interline; a persistent "
                     "directional gap for one carrier is the pattern worth ranking."))
    return BrokeringDivergence(movement, tendered_to, bill_of_lading_names, diverges=False)


def render(vetting: Vetting) -> str:
    lines = [f"CARRIER {vetting.carrier} — {vetting.outcome}"]
    if vetting.empty_because:
        lines.append(f"  (no checks) {vetting.empty_because}")
    for check in vetting.checks:
        lines.append(f"  {check.name:<12} {check.outcome}"
                     + (f" [{check.code}]" if check.code else ""))
        if check.detail:
            lines.append(f"  {'':<12} {check.detail}")
        if check.remedy:
            lines.append(f"  {'':<12} remedy: {check.remedy}")
    if vetting.undetermined:
        lines.append("  ! UNDETERMINED checks are not passes and not failures: "
                     f"{[c.name for c in vetting.undetermined]}")
    return "\n".join(lines)
