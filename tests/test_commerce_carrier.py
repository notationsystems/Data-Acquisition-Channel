"""Carrier vetting graded, with the third state as the subject.

The test that carries the point is
`test_cannot_determine_is_not_collapsed_into_either_neighbour`. A boolean
gate renders an unreachable registry identical to a fraudulent carrier
(fail-closed) or to a clean one (fail-open). Both report a fact about the
CARRIER when the observable was a fact about the CHECK, and here that
mistake costs a load.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.carrier import (ATTESTED_ONLY_BY_THE_CARRIER,  # noqa: E402
                              AUTHORITY_NOT_ON_FILE, AUTHORITY_REVOKED_BY_THE_REGULATOR,
                              BILL_OF_LADING_NAMES_A_DIFFERENT_CARRIER, CANNOT_DETERMINE,
                              CARRIER_CLAIM_CONTRADICTS_THE_REGULATOR, CARRIER_SELF_ASSERTED,
                              CERTIFICATE_LAPSES_INSIDE_THE_MOVEMENT, CERTIFICATE_NOT_SUPPLIED,
                              COVERAGE_BELOW_THE_REQUIREMENT, ELIGIBLE, ELIGIBLE_PENDING,
                              INSURER_CONFIRMED, NOT_ELIGIBLE, REGISTRY_UNREACHABLE,
                              REGULATOR_PUBLISHED, Attestation, AuthorityStatus,
                              InsuranceCertificate, check_authority, check_double_brokering,
                              check_insurance, render, vet)

INSURER = Attestation(INSURER_CONFIRMED, "2026-08-01")
CARRIER_SAYS = Attestation(CARRIER_SELF_ASSERTED, "2026-08-01")
REGULATOR = Attestation(REGULATOR_PUBLISHED, "2026-08-30")


def _cert(**over: object) -> InsuranceCertificate:
    base = dict(insurer="Acme Marine", coverage=250_000.0, currency="CAD",
                valid_from="2026-01-01", valid_until="2026-12-31", attestation=INSURER)
    base.update(over)
    return InsuranceCertificate(**base)  # type: ignore[arg-type]


def _insurance(**kw: object):
    args = dict(required=100_000.0, currency="CAD", period_start="2026-09-01",
                period_end="2026-09-05")
    args.update(kw)
    return check_insurance(args.pop("certificate", _cert()), **args)  # type: ignore[arg-type]


# =====================================================================
# The certificate is a validWhile predicate over the WHOLE movement
# =====================================================================

def test_a_certificate_valid_at_booking_but_lapsed_before_delivery_fails():
    """The knownAt-versus-period distinction, where getting it wrong is a
    liability rather than a reporting error."""
    check = _insurance(certificate=_cert(valid_until="2026-09-03"),
                       period_start="2026-09-01", period_end="2026-09-05")
    assert check.outcome == NOT_ELIGIBLE
    assert check.code == CERTIFICATE_LAPSES_INSIDE_THE_MOVEMENT
    assert "valid at booking is not" in (check.detail or "").lower()


def test_the_certificate_cannot_be_asked_about_a_single_date():
    """Structural: `covers` takes a period, so the single-instant check
    that produces the lapse bug cannot be written by accident."""
    import inspect
    signature = inspect.signature(InsuranceCertificate.covers)
    assert list(signature.parameters) == ["self", "period_start", "period_end"]


def test_coverage_below_the_requirement_fails_with_the_numbers():
    check = _insurance(certificate=_cert(coverage=50_000.0))
    assert check.outcome == NOT_ELIGIBLE and check.code == COVERAGE_BELOW_THE_REQUIREMENT


def test_a_certificate_attested_only_by_the_carrier_cannot_be_determined():
    """A cloned identity forwards a real document. The carrier's word about
    its own insurance is evidence of what the carrier says."""
    check = _insurance(certificate=_cert(attestation=CARRIER_SAYS))
    assert check.outcome == CANNOT_DETERMINE
    assert check.code == ATTESTED_ONLY_BY_THE_CARRIER
    assert "insurer" in (check.remedy or "")


def test_no_certificate_is_pending_rather_than_failed():
    """Not supplied and supplied-and-insufficient are different situations
    with different remedies."""
    check = _insurance(certificate=None)
    assert check.outcome == ELIGIBLE_PENDING and check.code == CERTIFICATE_NOT_SUPPLIED


def test_coverage_in_another_currency_is_undetermined_not_compared():
    check = _insurance(certificate=_cert(currency="USD"))
    assert check.outcome == CANNOT_DETERMINE


def test_a_good_certificate_passes():
    assert _insurance().outcome == ELIGIBLE


# =====================================================================
# Authority: a sourced observation, and the divergence when claims differ
# =====================================================================

def test_an_unreachable_register_is_undetermined_and_says_so_about_the_check():
    check = check_authority(None)
    assert check.outcome == CANNOT_DETERMINE and check.code == REGISTRY_UNREACHABLE
    assert "fact about the CHECK" in check.detail
    assert "not evidence that authority is absent" in check.detail


def test_absent_from_the_register_differs_from_revoked_by_it():
    absent = check_authority(AuthorityStatus(None, REGULATOR))
    revoked = check_authority(AuthorityStatus(False, REGULATOR))
    assert absent.code == AUTHORITY_NOT_ON_FILE and absent.outcome == CANNOT_DETERMINE
    assert revoked.code == AUTHORITY_REVOKED_BY_THE_REGULATOR and revoked.outcome == NOT_ELIGIBLE
    assert absent.detail != revoked.detail


def test_a_carrier_claim_contradicting_the_regulator_is_a_first_class_finding():
    check = check_authority(AuthorityStatus(True, REGULATOR), carrier_claim=False)
    assert check.outcome == NOT_ELIGIBLE
    assert check.code == CARRIER_CLAIM_CONTRADICTS_THE_REGULATOR
    assert "not a data-entry note" in check.detail


def test_the_attestation_route_carries_an_evidence_class_and_independence():
    assert REGULATOR.independent and REGULATOR.evidence_class == "measured"
    assert not CARRIER_SAYS.independent and CARRIER_SAYS.evidence_class == "asserted"


# =====================================================================
# The third state, which is the whole point
# =====================================================================

def test_cannot_determine_is_not_collapsed_into_either_neighbour():
    """A boolean gate makes an unreachable registry look like a fraudulent
    carrier or a clean one, depending on which way it fails. Both report a
    fact about the carrier when the observable was about the check."""
    vetting = vet("Carrier A", [_insurance(), check_authority(None)])
    assert vetting.outcome == CANNOT_DETERMINE
    assert vetting.outcome != ELIGIBLE, "fail-open would tender this load"
    assert vetting.outcome != NOT_ELIGIBLE, "fail-closed would blacklist a possibly-clean carrier"
    assert [c.name for c in vetting.undetermined] == ["authority"]


def test_a_real_failure_outranks_an_undetermined_check():
    """A carrier the register says is revoked is not made ambiguous by a
    second check that could not run."""
    vetting = vet("Carrier B", [_insurance(certificate=_cert(coverage=1.0)),
                                check_authority(None)])
    assert vetting.outcome == NOT_ELIGIBLE


def test_all_four_outcomes_are_reachable_and_distinct():
    outcomes = {
        vet("a", [_insurance(), check_authority(AuthorityStatus(True, REGULATOR))]).outcome,
        vet("b", [_insurance(certificate=None)]).outcome,
        vet("c", [check_authority(None)]).outcome,
        vet("d", [check_authority(AuthorityStatus(False, REGULATOR))]).outcome,
    }
    assert outcomes == {ELIGIBLE, ELIGIBLE_PENDING, CANNOT_DETERMINE, NOT_ELIGIBLE}


def test_a_carrier_with_no_checks_is_not_eligible_by_default():
    """An empty check list reads as a clean sheet and is the opposite."""
    vetting = vet("Carrier C", [])
    assert vetting.outcome == CANNOT_DETERMINE
    assert vetting.empty_because is not None
    assert "opposite of one" in vetting.empty_because


def test_every_non_passing_check_carries_a_remedy():
    for check in (_insurance(certificate=None), check_authority(None),
                  check_authority(AuthorityStatus(False, REGULATOR)),
                  _insurance(certificate=_cert(attestation=CARRIER_SAYS))):
        assert check.remedy, f"{check.name}/{check.code} refuses with no remedy"
        assert len(check.remedy.split()) > 5


def test_render_marks_undetermined_checks_as_neither_passes_nor_failures():
    text = render(vet("Carrier D", [_insurance(), check_authority(None)]))
    assert "UNDETERMINED checks are not passes and not failures" in text


# =====================================================================
# Double-brokering as a divergence
# =====================================================================

def test_a_bill_of_lading_naming_another_carrier_is_a_divergence():
    result = check_double_brokering("load-1", "Carrier A", "Carrier Z")
    assert result.diverges
    assert result.finding is not None
    assert BILL_OF_LADING_NAMES_A_DIFFERENT_CARRIER in result.finding
    assert "persistent directional gap" in result.finding


def test_an_uncaptured_bill_of_lading_is_one_claim_not_agreement():
    """The failure mode is reading a missing document as confirmation."""
    result = check_double_brokering("load-2", "Carrier A", None)
    assert not result.diverges
    assert result.finding is not None and "it is one claim" in result.finding


def test_matching_names_diverge_not_and_carry_no_finding():
    result = check_double_brokering("load-3", "Carrier A", "Carrier A")
    assert not result.diverges and result.finding is None
