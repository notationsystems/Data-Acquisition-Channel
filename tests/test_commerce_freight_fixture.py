"""The freight fixture, and whether the machinery catches what was planted.

A fixture that merely filled tables would prove the tables fill. This one
is six planted defects, and each test below asserts the corresponding
machinery finds it. Where it does not, that is the finding.

INADMISSIBLE BY CONSTRUCTION. Every row is fabricated and says so inside
its own content. Copper ran twenty-odd rounds this way with every result
correctly marked, and the gate flipped when a real source landed. A
fixture licenses work on the machinery and licenses no claim about the
world; these tests check the label as carefully as the analytics.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce import residuals as R  # noqa: E402
from commerce.carrier import (BILL_OF_LADING_NAMES_A_DIFFERENT_CARRIER,  # noqa: E402
                              check_double_brokering)
from commerce.facility import AMBIGUOUS, Facility, available_normalizer, resolve  # noqa: E402
from commerce.fixtures import freight  # noqa: E402
from commerce.vetting import (BLOCKED, CLEARED, COVERAGE_LAPSES_INSIDE_THE_MOVEMENT,  # noqa: E402
                              INSURANCE_COVERAGE, REPORTED, RUNG_BULK_HISTORY,
                              VettingObservation, VettingProvenance, insurance_current)

LOADS = freight.loads()
EVENTS = freight.events()
CARRIER_OF = {l.load: l.tendered_to for l in LOADS}
LANE_OF = {l.load: (l.origin, l.destination) for l in LOADS}
MONTH_OF = {l.load: l.month for l in LOADS}
RECEIVER_OF = {l.load: l.destination for l in LOADS}


# =====================================================================
# The label, checked before the analytics
# =====================================================================

def test_every_event_declares_itself_fabricated_inside_its_own_content():
    """A label that lives in a filename is lost on the first copy."""
    for event in EVENTS:
        assert event.source.artifact == freight.PROVENANCE
        assert freight.PROVENANCE in event.source.source_id


def test_the_fixture_states_its_own_inadmissibility():
    label = freight.label()
    assert label["provenance"] == "fabricated_fixture"
    assert "INADMISSIBLE" in label["admissibility"]
    assert "licenses NO claim about any carrier" in label["admissibility"]


# =====================================================================
# PLANT 1 — seasonal detention on a repeated lane
# =====================================================================

def test_the_season_partition_finds_a_signal_the_annual_figure_hides():
    """The lane runs one day long in winter and on time otherwise. The
    ANNUAL mean describes neither mode and would price every load the
    same."""
    seasonal = R.by_lane_season(EVENTS, LANE_OF, MONTH_OF)
    winter = seasonal.get("fac-a->fac-b:winter")
    summer = seasonal.get("fac-a->fac-b:non_winter")
    assert winter is not None and summer is not None
    assert winter.estimated and summer.estimated, "the plant must clear the min-trials floor"
    assert winter.mean == 1.0 and winter.spread == 0.0
    assert summer.mean == 0.0

    annual = R.by_lane(EVENTS, LANE_OF).get("fac-a->fac-b")
    assert annual is not None and annual.mean is not None
    assert 0.3 < annual.mean < 0.5, "the annual figure sits between the two modes"
    assert annual.spread is not None and annual.spread > 0.4, (
        "and its spread is the tell: a lane with one mode does not scatter like this"
    )


def test_the_fixture_was_widened_because_the_first_version_could_not_fire():
    """SELF-CORRECTION, kept. The lane originally ran one load a month
    across eight months, putting three loads in winter — below the
    min-trials floor the residual model correctly enforces. The analytics
    refused to estimate, which was right, and the plant proved nothing."""
    seasonal = R.by_lane_season(EVENTS, LANE_OF, MONTH_OF)
    winter = seasonal.get("fac-a->fac-b:winter")
    assert winter is not None and winter.n >= R.MIN_TRIALS
    source = (REPO_ROOT / "commerce" / "fixtures" / "freight.py").read_text()
    assert "BELOW the min-trials floor" in " ".join(source.split())


# =====================================================================
# PLANT 2 — one carrier invoices above its quote, persistently
# =====================================================================

def test_the_over_invoicing_carrier_is_found_and_is_attributable_to_the_carrier():
    """A gap on one lane across carriers is a lane fact. The same gap
    following a carrier is a carrier fact, and the clean comparison set on
    the same lane is what separates them."""
    result = R.by_carrier(EVENTS, CARRIER_OF)
    over = result.get("carrier-overbills")
    clean = result.get("carrier-clean")
    assert over is not None and clean is not None
    assert over.estimated and clean.estimated
    assert over.mean is not None and over.mean > 100.0
    assert clean.mean == 0.0, "the comparison set must be clean or the plant is unattributable"


def test_a_carrier_below_the_floor_reports_its_count_and_no_estimate():
    """A mean over three loads is a number and not an estimate."""
    result = R.by_carrier(EVENTS, CARRIER_OF)
    thin = result.get("carrier-lapses")
    assert thin is not None
    assert not thin.estimated and thin.mean is None
    assert thin.n < R.MIN_TRIALS
    assert thin.refusal is not None and "not an estimate" in thin.refusal


# =====================================================================
# PLANT 3 — a receiver that slips its appointment
# =====================================================================

def test_the_slipping_receiver_is_found_and_the_others_are_clean():
    """Modelled on the RECEIVER rather than the driver: it generalises
    across carriers, has more observations, and carries none of the
    exposure of a person-level score."""
    result = R.appointment_slippage(EVENTS, RECEIVER_OF)
    slipping = result.get(freight.SLIPPING_RECEIVER)
    assert slipping is not None and slipping.estimated
    assert slipping.mean is not None and slipping.mean > 0.5
    others = [r for r in result.estimated if r.key != freight.SLIPPING_RECEIVER]
    assert others, "a vacuity guard: with no clean receiver the plant is unattributable"
    for other in others:
        assert other.mean == 0.0


# =====================================================================
# PLANT 4 — two facilities that are the same place
# =====================================================================

def test_the_duplicate_facility_is_surfaced_and_never_merged():
    name, normalize = available_normalizer()
    register = [Facility("fac-a", freight.FACILITIES["fac-a"],
                         normalize(freight.FACILITIES["fac-a"]), name)]
    result = resolve(freight.FACILITIES["fac-a-dup"], register)
    assert result.status == AMBIGUOUS
    assert result.facility is None, "a near match must never resolve to a facility"
    assert [c.facility_id for c in result.candidates] == ["fac-a"]
    assert "Surfaced, not merged" in result.detail


def test_an_unrelated_facility_does_not_match():
    """Vacuity guard: if everything matched, the plant above would prove
    nothing about the normalizer."""
    name, normalize = available_normalizer()
    register = [Facility("fac-a", freight.FACILITIES["fac-a"],
                         normalize(freight.FACILITIES["fac-a"]), name)]
    result = resolve(freight.FACILITIES["fac-b"], register)
    assert result.status != AMBIGUOUS


# =====================================================================
# PLANT 5 — insurance lapsing between pickup and delivery
# =====================================================================

def _coverage() -> VettingObservation:
    start, end = freight.insurance_window()["carrier-lapses"]
    return VettingObservation(
        subject="carrier-lapses", kind=INSURANCE_COVERAGE, value=250_000.0, unit="CAD",
        period_start=start, period_end=end, known_at="2026-08-01",
        provenance=VettingProvenance("insurer:fixture", REPORTED, RUNG_BULK_HISTORY,
                                     "2026-08-01"))


def test_coverage_lapsing_between_pickup_and_delivery_blocks():
    result = insurance_current([_coverage()], required=100_000.0, currency="CAD",
                               booking_date="2026-08-05", pickup_date="2026-08-06",
                               delivery_date="2026-08-07", asof="2026-08-05")
    assert result.status == BLOCKED
    assert result.code == COVERAGE_LAPSES_INSIDE_THE_MOVEMENT
    assert "after pickup" in result.detail


def test_the_same_certificate_clears_a_same_day_load():
    """THE DISCRIMINATING PAIR. A point-in-time check at booking passes on
    this exact certificate. Only a check over the whole period does not,
    which is the entire reason `covers()` takes one."""
    result = insurance_current([_coverage()], required=100_000.0, currency="CAD",
                               booking_date="2026-08-05", pickup_date="2026-08-05",
                               delivery_date="2026-08-05", asof="2026-08-05")
    assert result.status == CLEARED


def test_the_lapse_date_was_moved_because_the_first_version_took_the_easy_branch():
    """SELF-CORRECTION, kept. Coverage originally ended three weeks before
    booking, so the predicate returned COVERAGE_LAPSED_BEFORE_BOOKING — a
    real refusal and the easy one. A plant that fires on the easy branch
    does not exercise the hard one."""
    source = (REPO_ROOT / "commerce" / "fixtures" / "freight.py").read_text()
    assert "does not exercise the hard one" in " ".join(source.split())


# =====================================================================
# PLANT 6 — a bill of lading naming a carrier that was never tendered
# =====================================================================

def test_the_double_brokering_signature_is_found():
    signatures = [check_double_brokering(l.load, l.tendered_to, l.bill_of_lading_carrier)
                  for l in LOADS]
    diverging = [s for s in signatures if s.diverges]
    assert len(diverging) == 1, "exactly one load was planted"
    assert diverging[0].movement == "L-E00"
    assert diverging[0].finding is not None
    assert BILL_OF_LADING_NAMES_A_DIFFERENT_CARRIER in diverging[0].finding


def test_every_other_load_agrees_so_the_signal_is_not_noise():
    agreeing = [check_double_brokering(l.load, l.tendered_to, l.bill_of_lading_carrier)
                for l in LOADS if l.load != "L-E00"]
    assert agreeing and all(not s.diverges for s in agreeing)
    assert all(s.finding is None for s in agreeing)


# =====================================================================
# Accounting over the whole fixture
# =====================================================================

def test_a_live_unsettled_load_is_excluded_rather_than_counted_as_zero():
    """PLANT 7, ADDED AFTER A PLANT WENT UNCAUGHT. Making `_paired` treat
    an unsettled promise as a zero residual left the whole suite green,
    because every other load in the fixture settles. A real guard with no
    discriminating case is a guard that has never run.

    L-F00 is quoted at 9,999 and never invoiced. Counted as zero it would
    drag the clean carrier's mean far negative; excluded, the mean holds."""
    live = [l for l in LOADS if l.load == "L-F00"][0]
    kinds = {e.kind for e in live.events}
    assert R.RATE_QUOTED in kinds and R.SETTLES[R.RATE_QUOTED] not in kinds

    clean = R.by_carrier(EVENTS, CARRIER_OF).get("carrier-clean")
    assert clean is not None and clean.mean == 0.0, (
        "an unsettled 9,999 quote counted as zero would move this mean; it must not appear"
    )
    settled = {e.load for e in EVENTS if e.kind == R.SETTLES[R.RATE_QUOTED]}
    assert "L-F00" not in settled
    assert clean.n == len([l for l in LOADS
                           if l.tendered_to == "carrier-clean" and l.load in settled])


def test_every_other_load_carries_both_halves_of_every_pair_it_declares():
    for load in LOADS:
        if load.load == "L-F00":
            continue
        kinds = {e.kind for e in load.events}
        for promise, settlement in R.SETTLES.items():
            if promise in kinds:
                assert settlement in kinds, f"{load.load} promises {promise} and never settles it"


def test_the_residual_partitions_disagree_which_is_the_point():
    """`by_carrier` and `by_lane` answer different questions. Reporting one
    without naming the partition is how the two get confused."""
    carrier = R.by_carrier(EVENTS, CARRIER_OF)
    lane = R.by_lane(EVENTS, LANE_OF, promise=R.RATE_QUOTED)
    assert carrier.partition != lane.partition
    over = carrier.get("carrier-overbills")
    assert over is not None and over.mean is not None and over.mean > 100.0
    # The same money gap, seen by lane, is diluted by the clean carrier on it.
    by_that_lane = lane.get("fac-a->fac-c")
    assert by_that_lane is not None and by_that_lane.mean is not None
    assert by_that_lane.mean < over.mean, (
        "the lane view must dilute the carrier signal, or the two partitions are redundant"
    )
