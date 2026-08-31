"""PC-6 Parts C-F graded against the spec's own acceptance criteria.

Each criterion has a test named for it. The two that carry the most are
`test_no_tender_can_be_issued_against_a_carrier_that_is_not_cleared`
(structural, not conventional) and
`test_a_planted_source_outage_produces_undetermined` -- because
`undetermined` is the state a boolean collapses, and a state that is never
exercised is a state that does not work.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.authority import Actor, Disposal, Proposal, validate  # noqa: E402
from commerce.stores import Authority, Quantity  # noqa: E402
from commerce.tendering import issue_tender  # noqa: E402
from commerce.vetting import (AUTHORITY_GRANTED_AT, AUTHORITY_GRANTED_TOO_RECENTLY,  # noqa: E402
                              AUTHORITY_NOT_ACTIVE, AUTHORITY_STATUS, BLOCKED,
                              CARRIER_DOCUMENT_DISAGREES_WITH_THE_INSURER, CLEARED,
                              CONFIRMED_ONLY_BY_THE_CARRIER, COVERAGE_LAPSED_BEFORE_BOOKING,
                              COVERAGE_LAPSES_INSIDE_THE_MOVEMENT, ESTIMATED,
                              HISTORY_NOT_AVAILABLE_AT_THIS_RUNG, INSURANCE_COVERAGE,
                              NO_OBSERVATION_OF_THIS_KIND,
                              NO_USDOT_RECORD_AND_NO_PROVINCIAL_SOURCE, OOS_ORDER,
                              OBSERVATION_OLDER_THAN_ITS_REFRESH_INTERVAL, REPORTED,
                              RUNG_BULK_HISTORY, RUNG_COMMITTED_SNAPSHOT,
                              RUNG_OFFICIAL_SNAPSHOT, SELF_REPORTED,
                              NO_CHANNEL_ESTABLISHED_FOR_THIS_WINDOW,
                              RUNG_IS_EMPTY_FOR_THIS_JURISDICTION, SMS_PERCENTILE,
                              TENDER_AGAINST_A_CARRIER_THAT_IS_NOT_CLEARED,
                              TENDER_AGAINST_A_STALE_VERDICT, UNDETERMINED, Carrier,
                              TenderRefusal, VettingObservation, VettingProvenance,
                              authorise_tender, authority_active, coverage_divergence, decide,
                              insurance_current, jurisdiction_coverage, no_recent_reincarnation,
                              render)

CARRIER = Carrier("c-1", "Northern Freight Ltd", dot_number="1234567")
DOMESTIC = Carrier("c-2", "Transport Domestique Inc", cvor_number="CV-9")


def _prov(source_class=REPORTED, rung=RUNG_BULK_HISTORY, source_id="fmcsa:li"):
    return VettingProvenance(source_id=source_id, source_class=source_class, rung=rung,
                             retrieved_at="2026-08-31")


def _insurance(**over):
    base = dict(subject="c-1", kind=INSURANCE_COVERAGE, value=250_000.0, unit="CAD",
                period_start="2026-01-01", period_end="2026-12-31", known_at="2026-08-30",
                provenance=_prov(source_id="insurer:acme"))
    base.update(over)
    return VettingObservation(**base)


def _authority(**over):
    base = dict(subject="c-1", kind=AUTHORITY_STATUS, value=True, unit=None,
                period_start="2026-08-30", period_end=None, known_at="2026-08-30",
                provenance=_prov())
    base.update(over)
    return VettingObservation(**base)


def _granted(when="2020-03-01", rung=RUNG_BULK_HISTORY, known_at="2026-08-30"):
    return VettingObservation(subject="c-1", kind=AUTHORITY_GRANTED_AT, value=when, unit=None,
                              period_start=when, period_end=None, known_at=known_at,
                              provenance=_prov(rung=rung))


def _movement(**over):
    base = dict(required=100_000.0, currency="CAD", booking_date="2026-09-01",
                pickup_date="2026-09-03", delivery_date="2026-09-07", asof="2026-08-31")
    base.update(over)
    return base


# =====================================================================
# CRITERION 1 — no tender against a carrier that is not cleared,
# asserted structurally
# =====================================================================

def test_a_carrier_tender_is_constructed_in_exactly_one_place():
    """The invariant is not that issue_tender is careful. It is that there
    is nowhere else to go.

    An earlier version of this test scanned for `dispose(` and found a
    second door -- `ReviewQueue.take()`. That was a real finding and the
    fix was NOT to close that door: not every commitment is a carrier
    tender, and a quote to a shipper has no carrier to vet. The invariant
    is carried by a type instead, so an ordinary commitment stays possible
    and a carrier tender stays impossible outside the gate."""
    sites = []
    for path in sorted((REPO_ROOT / "commerce").rglob("*.py")):
        body = re.sub(r'\"\"\"(?:.|\n)*?\"\"\"', "", path.read_text())
        if re.search(r"CarrierTender\s*\(", body):
            sites.append(path.relative_to(REPO_ROOT).as_posix())
    assert sites == ["commerce/tendering.py"], (
        f"CarrierTender is constructed in {sites}. A second construction site makes the gate "
        "advisory."
    )


def test_capacity_cannot_be_booked_with_an_ordinary_commitment():
    """A caller holding a Commitment disposed of through the review queue
    has nothing to hand book()."""
    from commerce.tendering import BookingRefusal, book
    agent, other, human = (Actor("scout.a", True), Actor("val.b", True), Actor("ops@firm", False))
    proposal = Proposal(subject="tender:L-2", quantity=Quantity(1.0, "loads", "per_week"),
                        proposed_by=agent, evidence_refs=("n:1",),
                        decision_it_would_change="whether to tender")
    from commerce.authority import ReviewQueue
    queue = ReviewQueue()
    queue.propose(proposal)
    queue.record(validate(proposal, other, supported=True, reason="read"))
    commitment = queue.take(proposal, Disposal(
        disposer=human, authority=Authority("ops", "signing_delegation", "2026-01-01",
                                            "2026-12-31"),
        issued_at="2026-09-01", idempotency_key="L-2"))
    with pytest.raises(BookingRefusal) as caught:
        book(commitment)
    assert "Only a CarrierTender may book capacity" in caught.value.detail


def test_a_cleared_tender_books():
    from commerce.tendering import book
    cleared = decide(CARRIER, [insurance_current([_insurance()], **_movement()),
                               authority_active([_authority()], asof="2026-08-31"),
                               no_recent_reincarnation(
                                   [_granted()], asof="2026-08-31",
                                   exception_reason="operating since 2020; frozen-source gap "
                                                    "closed by a dated regulator printout")],
                     asof="2026-08-31")
    assert book(_tender(cleared)).carrier == "c-1"


def test_issue_tender_puts_the_vetting_gate_before_disposal():
    """Source order, checked. A gate that runs after disposal has already
    bound the firm."""
    body = (REPO_ROOT / "commerce" / "tendering.py").read_text()
    body = re.sub(r'^"""(?:.|\n)*?"""', "", body, count=1)
    gate = body.index("authorise_tender(")
    issue = body.index("dispose(proposal")
    assert gate < issue, "the vetting gate must run before dispose()"


def _tender(vetting):
    agent, other, human = (Actor("scout.a", True), Actor("val.b", True),
                           Actor("ops@firm", False))
    proposal = Proposal(subject="tender:L-1", quantity=Quantity(1.0, "loads", "per_week"),
                        proposed_by=agent, evidence_refs=("notice:1",),
                        decision_it_would_change="whether to tender")
    verdict = validate(proposal, other, supported=True, reason="read")
    disposal = Disposal(disposer=human, authority=Authority("ops", "signing_delegation",
                                                            "2026-01-01", "2026-12-31"),
                        issued_at="2026-09-01", idempotency_key="L-1")
    return issue_tender(vetting, proposal, verdict, disposal)


def test_a_blocked_carrier_cannot_be_tendered_even_by_a_human_with_authority():
    """The human's authority is over the commercial judgement, not over
    whether the carrier is insured."""
    blocked = decide(CARRIER, [insurance_current([_insurance(value=1.0)], **_movement())],
                     asof="2026-08-31")
    assert blocked.status == BLOCKED
    with pytest.raises(TenderRefusal) as caught:
        _tender(blocked)
    assert caught.value.code == TENDER_AGAINST_A_CARRIER_THAT_IS_NOT_CLEARED


def test_an_undetermined_carrier_cannot_be_tendered_either():
    undetermined = decide(CARRIER, [insurance_current([], **_movement())], asof="2026-08-31")
    assert undetermined.status == UNDETERMINED
    with pytest.raises(TenderRefusal):
        _tender(undetermined)


def test_a_cleared_carrier_can_be_tendered():
    cleared = decide(CARRIER, [insurance_current([_insurance()], **_movement()),
                               authority_active([_authority()], asof="2026-08-31"),
                               no_recent_reincarnation(
                                   [_granted()], asof="2026-08-31",
                                   exception_reason="operating since 2020; frozen-source gap "
                                                    "closed by a dated regulator printout")],
                     asof="2026-08-31")
    assert cleared.status == CLEARED
    assert _tender(cleared).commitment.subject == "tender:L-1"


def test_a_verdict_that_has_aged_out_is_not_a_verdict():
    cleared = decide(CARRIER, [authority_active([_authority()], asof="2026-08-31")],
                     asof="2026-08-31", valid_until="2026-08-31")
    with pytest.raises(TenderRefusal) as caught:
        _tender(cleared)
    assert caught.value.code == TENDER_AGAINST_A_STALE_VERDICT


# =====================================================================
# CRITERION 2 — undetermined is reachable, distinguishable, and a planted
# source outage produces it
# =====================================================================

def test_a_planted_source_outage_produces_undetermined():
    """The plant: every source down, so no observation exists. Fail-closed
    would blacklist a possibly-clean carrier; fail-open would tender the
    load. Neither is a fact about this carrier."""
    outage = decide(CARRIER, [insurance_current([], **_movement()),
                              authority_active([], asof="2026-08-31")], asof="2026-08-31")
    assert outage.status == UNDETERMINED
    assert outage.status not in (CLEARED, BLOCKED)
    assert set(outage.missing) == {"insurance_current", "authority_active"}
    for predicate in outage.undetermined:
        assert predicate.code == NO_OBSERVATION_OF_THIS_KIND
        assert "not evidence that" in predicate.detail or "not a finding that" in predicate.detail


def test_the_three_states_are_distinguishable_in_the_rendered_verdict():
    cleared = decide(CARRIER, [authority_active([_authority()], asof="2026-08-31")],
                     asof="2026-08-31")
    blocked = decide(CARRIER, [authority_active([_authority(value=False)], asof="2026-08-31")],
                     asof="2026-08-31")
    undetermined = decide(CARRIER, [authority_active([], asof="2026-08-31")], asof="2026-08-31")
    texts = {render(v) for v in (cleared, blocked, undetermined)}
    assert len(texts) == 3
    assert "UNDETERMINED is not a pass and not a failure" in render(undetermined)
    assert "UNDETERMINED is not a pass" not in render(blocked)


def test_a_stale_record_is_undetermined_rather_than_a_failure():
    """A vetting record older than its interval does not mean the carrier
    is bad. It means you do not currently know."""
    stale = insurance_current([_insurance(known_at="2026-06-01")], **_movement())
    assert stale.status == UNDETERMINED
    assert stale.code == OBSERVATION_OLDER_THAN_ITS_REFRESH_INTERVAL
    assert "does not mean the carrier is uninsured" in stale.detail


def test_a_carrier_with_no_predicates_evaluated_is_not_cleared():
    verdict = decide(CARRIER, [], asof="2026-08-31")
    assert verdict.status == UNDETERMINED
    assert verdict.empty_because is not None
    assert "opposite of one" in verdict.empty_because


def test_a_real_failure_outranks_an_undetermined_check():
    verdict = decide(CARRIER, [insurance_current([_insurance(value=1.0)], **_movement()),
                               authority_active([], asof="2026-08-31")], asof="2026-08-31")
    assert verdict.status == BLOCKED


# =====================================================================
# CRITERION 3 — a predicate lapsing between booking and pickup fires, and
# the verdict names which side of the window it lapsed on
# =====================================================================

def test_coverage_lapsing_between_booking_and_pickup_fires_and_names_the_side():
    result = insurance_current([_insurance(period_end="2026-09-02")], **_movement())
    assert result.status == BLOCKED
    assert result.code == COVERAGE_LAPSES_INSIDE_THE_MOVEMENT
    assert "before pickup" in result.detail
    assert "valid when the load was tendered and is not valid when the truck arrives" in result.detail


def test_coverage_lapsing_after_pickup_but_before_delivery_names_the_other_side():
    result = insurance_current([_insurance(period_end="2026-09-05")], **_movement())
    assert result.status == BLOCKED
    assert result.code == COVERAGE_LAPSES_INSIDE_THE_MOVEMENT
    assert "after pickup" in result.detail


def test_coverage_that_had_already_lapsed_at_booking_is_a_different_code():
    result = insurance_current([_insurance(period_end="2026-08-15")], **_movement())
    assert result.code == COVERAGE_LAPSED_BEFORE_BOOKING
    assert "already uninsured when it was tendered" in result.detail


def test_coverage_covering_the_whole_movement_clears():
    assert insurance_current([_insurance()], **_movement()).status == CLEARED


# =====================================================================
# CRITERION 4 — a carrier-supplied certificate disagreeing with the
# insurer produces a divergence, not an overwrite
# =====================================================================

def test_a_carrier_document_disagreeing_with_the_insurer_is_a_divergence():
    observations = [
        _insurance(value=1_000_000.0, provenance=_prov(SELF_REPORTED, source_id="carrier:doc")),
        _insurance(value=250_000.0, provenance=_prov(REPORTED, source_id="insurer:acme")),
    ]
    result = coverage_divergence(observations, asof="2026-08-31")
    assert result is not None
    assert result.code == CARRIER_DOCUMENT_DISAGREES_WITH_THE_INSURER
    assert "1000000" in result.detail.replace(",", "").replace(".0", "")
    assert "250000" in result.detail.replace(",", "").replace(".0", "")
    assert "rather than resolved by overwriting" in result.detail


def test_both_claims_survive_the_divergence():
    """An overwrite destroys the only signal a persistently-disagreeing
    carrier gives off."""
    observations = [
        _insurance(value=1_000_000.0, provenance=_prov(SELF_REPORTED, source_id="carrier:doc")),
        _insurance(value=250_000.0, provenance=_prov(REPORTED, source_id="insurer:acme")),
    ]
    result = coverage_divergence(observations, asof="2026-08-31")
    assert result is not None
    assert set(result.evidence) == {"carrier:doc", "insurer:acme"}


def test_agreeing_claims_produce_no_divergence():
    observations = [
        _insurance(provenance=_prov(SELF_REPORTED, source_id="carrier:doc")),
        _insurance(provenance=_prov(REPORTED, source_id="insurer:acme")),
    ]
    assert coverage_divergence(observations, asof="2026-08-31") is None


def test_a_carrier_supplied_certificate_alone_cannot_clear_insurance():
    result = insurance_current([_insurance(provenance=_prov(SELF_REPORTED))], **_movement())
    assert result.status == UNDETERMINED
    assert result.code == CONFIRMED_ONLY_BY_THE_CARRIER
    assert "cloned identity forwards a real document" in result.detail


# =====================================================================
# CRITERION 5 — a domestic-Canada carrier with no USDOT record returns
# undetermined, with the provincial recon named as the remedy
# =====================================================================

def test_the_routing_table_answers_per_predicate_and_window_not_per_rung():
    """The linear ladder was refuted. The evidence supports a routing table
    keyed on (predicate, jurisdiction, time window): the bulk rung answers
    a grant date BEFORE the horizon and nothing after it, while the
    snapshot rung answers score history and never a grant date."""
    from commerce.vetting import channel_for
    assert channel_for(RUNG_BULK_HISTORY, AUTHORITY_GRANTED_AT, "2026-04-01") is None
    assert channel_for(RUNG_BULK_HISTORY, AUTHORITY_GRANTED_AT,
                       "2026-08-31") == NO_CHANNEL_ESTABLISHED_FOR_THIS_WINDOW
    assert channel_for(RUNG_OFFICIAL_SNAPSHOT, SMS_PERCENTILE, "2026-08-31") is None
    assert channel_for(RUNG_OFFICIAL_SNAPSHOT, AUTHORITY_GRANTED_AT,
                       "2026-08-31") == HISTORY_NOT_AVAILABLE_AT_THIS_RUNG


def test_the_primary_rung_is_empty_by_construction_for_a_canadian_domestic_carrier():
    """Not unwired -- EMPTY. L&I indexes carriers by US docket, so a
    domestic Canadian carrier without one is absent by definition. A
    linear ladder cannot say that; it would report a fallback to a lower
    rung that is equally empty."""
    result = jurisdiction_coverage(DOMESTIC, domestic_only=True)
    assert result.code == RUNG_IS_EMPTY_FOR_THIS_JURISDICTION
    assert "EMPTY BY CONSTRUCTION" in result.detail


def test_the_canadian_remedy_flags_the_unresolved_caching_rights():
    """Quebec's own terms prohibit storing without prior authorisation,
    and the recon probe that measured that prohibition then recommended a
    daily snapshot-and-diff store. The remedy must not repeat it."""
    result = jurisdiction_coverage(DOMESTIC, domestic_only=True)
    assert result.remedy is not None
    assert "prohibit storing" in result.remedy
    assert "a decision for a person, not a build step" in result.remedy


def test_a_domestic_only_carrier_with_no_usdot_record_is_undetermined():
    """CORRECTED BY RECON on two counts. The remedy first said "complete
    the provincial recon"; it is complete for two provinces and its
    headline finding was the opposite of the hypothesis -- Ontario's CVOR
    abstract is NOT consent-gated. And there is no federal Canadian
    carrier registry at all, so this is not one adapter but one per
    province, of which two of thirteen are reconned."""
    result = jurisdiction_coverage(DOMESTIC, domestic_only=True)
    assert result.status == UNDETERMINED
    assert result.remedy is not None
    assert "NOT consent-gated" in result.remedy
    assert "NEGATIVE screen" in result.remedy
    assert "NO FEDERAL CANADIAN CARRIER REGISTRY EXISTS" in result.detail
    assert "one adapter per province" in result.detail


def test_a_cross_border_carrier_is_covered_by_the_federal_record_wherever_domiciled():
    """The gap is narrower than it first looks: any carrier hauling into
    the US holds USDOT authority."""
    result = jurisdiction_coverage(Carrier("c-3", "Cross Border Ltd", dot_number="99"),
                                   domestic_only=False)
    assert result.status == CLEARED
    assert "regardless of domicile" in result.detail


def test_a_cross_border_move_by_a_carrier_with_no_usdot_number_is_undetermined_not_exempt():
    result = jurisdiction_coverage(DOMESTIC, domestic_only=False)
    assert result.status == UNDETERMINED
    assert "the record is incomplete rather than that the carrier is exempt" in result.detail


def test_the_gap_closes_when_a_provincial_source_is_wired_up():
    """Vacuity guard: if this could never clear, the undetermined branch
    above would be unfalsifiable."""
    result = jurisdiction_coverage(DOMESTIC, domestic_only=True,
                                   provincial_source_available=True)
    assert result.status == CLEARED


# =====================================================================
# CRITERION 6 — every observation carries its rung, and a snapshot-served
# verdict states its age
# =====================================================================

def test_every_observation_carries_the_rung_that_served_it():
    for observation in (_insurance(), _authority(), _granted()):
        assert observation.provenance.rung in range(0, 5)


def test_a_verdict_states_the_age_of_its_oldest_evidence():
    verdict = decide(CARRIER, [insurance_current([_insurance(known_at="2026-08-20")],
                                                 **_movement()),
                               authority_active([_authority(known_at="2026-08-30")],
                                                asof="2026-08-31")], asof="2026-08-31")
    assert verdict.oldest_evidence_days == 11
    assert "oldest evidence: 11 days" in render(verdict)


def test_the_rendered_verdict_names_the_rung_for_each_predicate():
    verdict = decide(CARRIER, [authority_active([_authority()], asof="2026-08-31")],
                     asof="2026-08-31")
    assert "rung 2 bulk_history" in render(verdict)


def test_a_snapshot_served_verdict_is_identifiable_as_such():
    verdict = decide(CARRIER, [authority_active(
        [_authority(provenance=_prov(rung=RUNG_COMMITTED_SNAPSHOT))], asof="2026-08-31")],
        asof="2026-08-31")
    assert verdict.served_from_snapshot


# =====================================================================
# The predicate that needs history, and the rung that cannot serve it
# =====================================================================

def test_reincarnation_cannot_be_evaluated_from_a_snapshot_rung():
    """A current snapshot reports that authority EXISTS and never reports
    when it began. A grant date from a snapshot is the snapshot's own date
    wearing the date the authority started."""
    result = no_recent_reincarnation([_granted(rung=RUNG_OFFICIAL_SNAPSHOT)], asof="2026-08-31")
    assert result.status == UNDETERMINED
    assert result.code == HISTORY_NOT_AVAILABLE_AT_THIS_RUNG
    assert result.remedy is not None and "bulk/historical" in result.remedy


def test_reincarnation_with_no_grant_date_at_all_is_undetermined_not_passed():
    result = no_recent_reincarnation([], asof="2026-08-31")
    assert result.status == UNDETERMINED
    assert "unevaluated reincarnation check is exactly how a chameleon carrier passes" in result.detail


def test_a_recently_granted_authority_blocks_even_from_a_frozen_source():
    """Ordering, and it is deliberate. A grant date that IS recent is a
    positive finding and blocks whatever the source's currency: the
    observation is there. What a frozen source cannot support is the
    NEGATIVE — "granted long ago and nothing since" — because a revocation
    and re-grant after the freeze is invisible in it."""
    result = no_recent_reincarnation([_granted("2026-07-01")], asof="2026-08-31")
    assert result.status == BLOCKED
    assert result.code == AUTHORITY_GRANTED_TOO_RECENTLY
    assert "not itself wrongdoing" in result.detail


def test_an_explicit_exception_with_a_reason_clears_the_reincarnation_predicate():
    result = no_recent_reincarnation([_granted("2026-07-01")], asof="2026-08-31",
                                     exception_reason="known principal, prior carrier wound up")
    assert result.status == CLEARED


def test_history_is_declared_per_rung_and_kind_not_per_rung():
    """CORRECTED BY RECON. The first version declared history as a property
    of the rung alone. Measured, the SMS website (rung 3, "current
    snapshot only" in the brief) serves 189 monthly snapshots from Nov
    2010 to Jul 2026 -- and still carries no grant date anywhere.

    A single boolean per rung would have granted SMS the authority-grant
    question it cannot answer, which is the reincarnation check: the one a
    chameleon carrier passes when it goes unevaluated."""
    from commerce.vetting import HISTORY_BY_RUNG, rung_answers_history_for
    assert rung_answers_history_for(RUNG_OFFICIAL_SNAPSHOT, SMS_PERCENTILE), (
        "SMS carries score history; declaring rung 3 historyless is measurably wrong"
    )
    assert not rung_answers_history_for(RUNG_OFFICIAL_SNAPSHOT, AUTHORITY_GRANTED_AT), (
        "no probed snapshot surface carries a grant date; granting it one is the defect"
    )
    assert rung_answers_history_for(RUNG_BULK_HISTORY, AUTHORITY_GRANTED_AT)
    assert AUTHORITY_GRANTED_AT in HISTORY_BY_RUNG[RUNG_BULK_HISTORY]


def test_a_grant_date_from_a_frozen_dataset_is_undetermined_after_the_freeze():
    """MEASURED. The legacy FMCSA Licensing & Insurance datasets state
    "last refreshed on 05/14/2026 and will no longer be updated", verified
    in the rows rather than trusted from the description.

    The failure direction is what makes this urgent: a carrier that
    registered AFTER the freeze is absent from the dataset, and absent is
    exactly how a newly-reincarnated carrier appears. The frozen source
    fails silently in the one direction the predicate exists to catch."""
    result = no_recent_reincarnation([_granted("2020-03-01")], asof="2026-08-31")
    assert result.status == UNDETERMINED
    assert result.code == NO_CHANNEL_ESTABLISHED_FOR_THIS_WINDOW
    assert "fails silently in the direction that matters" in result.detail
    assert "6.7 percent" in result.detail, (
        "the successor's coverage must be on the record: every probe in the recon round assumed "
        "it closed the seam and the verifier measured zero rows for 12 of 12"
    )
    assert result.remedy is not None
    assert "Do not union the successor in" in result.remedy, (
        "the measured failure mode is a FALSE PASS: the union reads `reinstated, in force` for a "
        "carrier out of service for three days"
    )


def test_the_same_grant_date_asked_before_the_freeze_still_clears():
    """Vacuity guard: a frozen dataset does not stop being useful, it stops
    being CURRENT. It answers 2024 perfectly."""
    result = no_recent_reincarnation([_granted("2020-03-01", known_at="2026-04-01")],
                                     asof="2026-05-01")
    assert result.status == CLEARED


# =====================================================================
# Authority, out-of-service, and the record model itself
# =====================================================================

def test_an_open_out_of_service_order_blocks_and_names_the_history_question():
    oos = VettingObservation(subject="c-1", kind=OOS_ORDER, value=True, unit=None,
                             period_start="2026-08-01", period_end=None, known_at="2026-08-30",
                             provenance=_prov())
    result = authority_active([_authority(), oos], asof="2026-08-31")
    assert result.status == BLOCKED
    assert "no lift date" in result.detail
    assert result.remedy is not None and "recorded with its period_end rather than deleted" in result.remedy


def test_a_lifted_out_of_service_order_does_not_block():
    oos = VettingObservation(subject="c-1", kind=OOS_ORDER, value=True, unit=None,
                             period_start="2026-08-01", period_end="2026-08-10",
                             known_at="2026-08-30", provenance=_prov())
    assert authority_active([_authority(), oos], asof="2026-08-31").status == CLEARED


def test_the_carrier_entity_has_no_boolean_vetting_field():
    """`carrier.insured = True` cannot answer 'was it insured on the
    ninth', cannot be superseded without losing what it said before, and
    cannot carry which rung served it."""
    for field in Carrier.__dataclass_fields__:
        assert field not in {"insured", "authorised", "safe", "cleared", "vetted", "blocked"}


def test_an_observation_that_became_knowable_later_cannot_inform_an_earlier_decision():
    """The replay rule. A record that arrived on Friday must not inform a
    decision taken on Tuesday, or every post-mortem is retrospectively
    right."""
    future = _insurance(known_at="2026-09-15")
    result = insurance_current([future], **_movement())
    assert result.status == UNDETERMINED
    assert result.code == NO_OBSERVATION_OF_THIS_KIND


def test_an_unknown_observation_kind_is_refused():
    with pytest.raises(ValueError):
        VettingObservation(subject="c-1", kind="vibes", value=True, unit=None,
                           period_start="2026-08-01", period_end=None, known_at="2026-08-01",
                           provenance=_prov())
