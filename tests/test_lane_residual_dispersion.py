"""Three measurements of commerce/residuals.py, re-taken here.

The record they belong to states numbers. If those numbers were prose
they would be bound to nothing, so each is recomputed against the live
module. A finding that stops being true fails here rather than sitting in
a YAML file describing a module that has moved on.

NOTHING IS REPAIRED BY THIS FILE. It measures and it does not decide: the
estimator choice belongs to the session that built the module, whose PC-0
gate is open by its own record.
"""

from __future__ import annotations

import inspect
import math
import pathlib
import statistics as st
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce import residuals as R  # noqa: E402
from epistemics._yaml import loads  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "lane_residual_dispersion.yaml").read_text())
FINDINGS = RECORD["findings"]


def test_the_spread_is_the_population_statistic_and_not_the_sample_one():
    """Finding 1, re-measured.

    Fails in the state where the divisor becomes n - 1 -- at which point
    the module computes the estimator its vocabulary implies and this
    record is the thing to retire.
    """
    values = [1.0, 2.0, 3.0, 4.0, 10.0]
    residual = R._summarise("k", "p", "b", "u", values)
    mean = st.mean(values)
    population = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    sample = st.stdev(values)

    assert residual.spread == pytest_approx(population), (
        "the spread is no longer the population SD; the finding needs re-measuring"
    )
    assert residual.spread != pytest_approx(sample)
    assert f"{population:.6f}" in FINDINGS[
        "the_module_says_estimate_and_computes_a_description"]["what_was_measured"]


def test_the_understatement_at_the_floor_is_the_number_the_record_states():
    understatement = 100 * (1 - math.sqrt((R.MIN_TRIALS - 1) / R.MIN_TRIALS))
    stated = FINDINGS["the_module_says_estimate_and_computes_a_description"]["the_number"]
    assert f"{understatement:.2f}%" in stated, (
        f"the floor is {R.MIN_TRIALS}, so the understatement is {understatement:.2f}% "
        f"and the record says {stated!r}"
    )


def test_the_module_uses_the_word_estimate_without_saying_which_one():
    """The finding is not that the divisor is wrong; it is that a reader
    cannot tell which statistic they have.

    Fails in the state where the module states its choice -- which is one
    of the two ways to close this, and the cheaper one.
    """
    source = inspect.getsource(R)
    assert source.count("estimate") >= 4, "the estimation vocabulary has gone; re-measure"
    for stated in ("population standard deviation", "sample standard deviation",
                   "divisor n", "unbiased"):
        assert stated not in source, (
            f"the module now names its estimator ({stated!r}); this finding is closed"
        )


def test_five_clustered_loads_and_five_dispersed_ones_are_indistinguishable():
    """Finding 2, and the discriminating case is the pair.

    Fails in the state where the module consults occasion rather than
    count -- LoadEvent already carries `known_at`, so the information
    exists and is not read.
    """
    clustered = [2.00, 2.01, 2.00, 2.02, 2.01]        # one week, one carrier
    dispersed = [1.60, 2.40, 1.90, 2.30, 2.05]        # five months

    a = R._summarise("lane", "by_lane", "rate", "usd_per_mile", clustered)
    b = R._summarise("lane", "by_lane", "rate", "usd_per_mile", dispersed)

    assert a.n == b.n == R.MIN_TRIALS
    assert a.estimated and b.estimated, "both cross the floor"
    assert a.refusal is None and b.refusal is None, "neither is refused"
    assert b.spread / a.spread > 30, (
        "the two spreads no longer differ by the factor the record measured"
    )
    # The Residual carries nothing that separates them.
    assert a.partition == b.partition and a.basis == b.basis and a.unit == b.unit


def test_the_grouping_reads_month_and_never_reads_known_at():
    """The information needed to tell a cluster from a spread is in the
    store. The claim is that the grouping does not consult it."""
    source = inspect.getsource(R)
    assert "month_of" in source
    assert "known_at" not in source, (
        "the residual grouping now reads known_at; the clustering finding is stale"
    )


def test_the_unreachable_branch_is_still_unreachable():
    """Finding 3. Asserted structurally rather than by reading the line:
    the floor gate precedes it and the function has one caller."""
    source = inspect.getsource(R._summarise)
    assert "if n > 1 else 0.0" in source
    assert "if n < MIN_TRIALS:" in source
    assert R.MIN_TRIALS > 1, (
        "the floor no longer exceeds 1, so the branch became reachable and the "
        "finding is wrong"
    )
    module_source = inspect.getsource(R)
    assert module_source.count("_summarise(") == 2, (
        "_summarise gained a caller; whether the branch is reachable has to be re-argued"
    )


def test_the_record_declines_to_resolve_another_sessions_decision():
    assert RECORD["status"] == "measured_and_not_repaired"
    assert "handed over" in RECORD["what_this_record_does_not_do"]
    assert "PC-0 gate is open" in RECORD["what_this_record_does_not_do"]


def test_the_cross_domain_instance_is_the_one_the_anchor_arc_found():
    """The claim that this is a substrate property rather than a freight
    quirk rests on the same defect appearing in the chemistry corpus. That
    record is in this tree and is checked, not cited."""
    fourth = loads((REPO_ROOT / "architecture" / "fourth_anchor_result.yaml").read_text())
    p4 = fourth["predictions_scored"]["p4_duplicate_injections_are_not_replicate_runs"]
    assert "IDENTICAL to section 12" in p4["what_was_measured"]
    assert "threefold" in p4["the_harm_in_numbers"] or "three" in p4["the_harm_in_numbers"]


def pytest_approx(value: float):
    import pytest
    return pytest.approx(value, rel=1e-12)
