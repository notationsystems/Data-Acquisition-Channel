"""What the substrate would do with replicate GPC data, re-measured.

The polymer vertical named replicate GPC runs as the cheapest next
measurement, and the question put before acquiring was whether the ingest
surface is the state the data should arrive into -- since no content gate
runs at ingest.

THE GATES WERE NOT THE CONSTRAINT, and this file establishes that by
measurement rather than by assertion: five replicates pass every gate that
exists, so wiring them would have changed nothing. The constraint is one
layer on, in the analysis layer's grouping, and every claim the readiness
record makes about it is re-measured here against the real modules.

WHY IT IS A TEST AND NOT A NOTE. The findings are about VENDORED code
inside the unmodifiable core. If a submodule bump changes the grouping,
the comparison context or the statistic, these fail -- which is exactly
when the readiness record stops being true, and exactly the moment
`bent: zero` also has to be re-established. A note would go stale
silently; this does not.
"""

from __future__ import annotations

import dataclasses
import datetime
import pathlib
import statistics
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402
from epistemics._yaml import loads  # noqa: E402

from daf.storage.frozen_mapping import FrozenMapping  # noqa: E402
from evidence.types import make_observation  # noqa: E402
from materials.analysis import (ComparisonGroup, _comparison_context,  # noqa: E402
                                _group_by_comparison_context)
from science.table import observation_is_table_alignable  # noqa: E402

READINESS = loads((REPO_ROOT / "architecture" / "polymer_acquisition_readiness.yaml").read_text())
MEASURED = READINESS["what_the_substrate_does_with_replicates"]

WHEN = datetime.datetime(2026, 8, 26, tzinfo=datetime.timezone.utc)

#: Five runs on one batch. Real GPC replicates differ in the measured
#: number and in nothing else that is a scientific condition.
MN_VALUES = (103820.0, 104310.0, 103960.0, 104175.0, 104040.0)
MW_VALUES = (109050.0, 109590.0, 109180.0, 109420.0, 109270.0)


CONDITIONS = {"column_calibration": "polystyrene_standards", "solvent": "THF"}


def content(value, uncertainty=1200.0, variable="number_average_molar_mass",
            conditions=None):
    return {
        "sample_id": "PS-lot-4471",
        "variable": variable,
        "value": value,
        "unit": "g/mol",
        "uncertainty": uncertainty,
        "uncertainty_kind": "stated",
        "conditions": FrozenMapping(CONDITIONS) if conditions is None else conditions,
    }


def observation(index, value, **kwargs):
    return make_observation(record_ids=(f"gpc-run-{index}",),
                            extraction_method="gpc_report_v1",
                            content=content(value, **kwargs),
                            confidence=1.0, extracted_at=WHEN)


def groups_for(values, **kwargs):
    return _group_by_comparison_context(tuple(
        (_comparison_context(content(v, **kwargs), "value"), v) for v in values))


# --------------------------------------------- the gates were not the constraint


def test_every_replicate_passes_every_gate_that_exists():
    """So wiring the gates at ingest could not have been the answer either
    way. Measured before the rest of this file draws any conclusion."""
    observations = [observation(i, v) for i, v in enumerate(MN_VALUES)]
    assert len({o.id for o in observations}) == len(observations)
    for obs in observations:
        verdict = observation_is_table_alignable(obs.content)
        assert verdict.admissible and not list(verdict.reasons), (
            f"a replicate is now refused: {list(verdict.reasons)}. The readiness record's premise "
            "-- that the gates are not the constraint -- must be re-measured."
        )


def test_replicate_distinctness_rests_on_one_record_per_run():
    """The unstated extractor obligation, shown in both directions."""
    same_run_same_value = make_observation(
        record_ids=("gpc-run-0",), extraction_method="gpc_report_v1",
        content=content(MN_VALUES[0]), confidence=1.0, extracted_at=WHEN)
    assert same_run_same_value.id == observation(0, MN_VALUES[0]).id, (
        "a re-read of one run should be the same fact"
    )
    distinct_runs_same_value = (
        observation(0, 104000.0).id, observation(1, 104000.0).id)
    assert distinct_runs_same_value[0] != distinct_runs_same_value[1], (
        "two runs reporting the same number must remain two observations; if they merge, a "
        "replicate set silently loses members and the estimated variance is biased DOWNWARD"
    )
    assert "biased the estimated variance DOWNWARD" in MEASURED[
        "they_are_admitted_and_distinct"]["the_unstated_obligation"].replace("bias the", "biased the")


# ------------------------------------------------------------ the grouping layer


def test_replicates_group_as_one_when_content_matches():
    groups = groups_for(MN_VALUES)
    assert len(groups) == 1
    assert len(groups[0].values) == len(MN_VALUES)
    assert groups[0].disagreement is not None


def test_a_per_run_uncertainty_splits_the_group_into_singletons():
    """The finding that would bite a real instrument. `uncertainty` is part
    of the comparison context, so a per-run figure -- what a real GPC
    reports -- makes every replicate its own group."""
    groups = _group_by_comparison_context(tuple(
        (_comparison_context(content(v, uncertainty=1200.0 + i), "value"), v)
        for i, v in enumerate(MN_VALUES)))
    assert len(groups) == len(MN_VALUES), (
        "differing per-run uncertainty no longer splits the comparison group -- the vendored "
        "context rule changed, and the readiness record must be re-measured"
    )
    assert all(g.disagreement is None for g in groups), (
        "a singleton group must yield no disagreement statistic"
    )
    assert "uncertainty" in _comparison_context(content(1.0), "value"), (
        "uncertainty has left the comparison context; the finding no longer holds"
    )


def test_the_statistic_is_a_range_and_not_a_variance():
    groups = groups_for(MN_VALUES)
    disagreement = groups[0].disagreement
    spread = disagreement.maximum - disagreement.minimum
    assert disagreement.spread == pytest.approx(spread)
    assert spread == pytest.approx(490.0, abs=0.5)
    assert statistics.stdev(MN_VALUES) == pytest.approx(189.6, abs=0.5)
    assert spread > 2 * statistics.stdev(MN_VALUES), (
        "the recorded contrast between a range and a standard deviation no longer holds"
    )


def test_the_pairing_is_destroyed_which_is_what_ends_it():
    """THE DECISIVE ONE. A correlation is a statement about which Mn goes
    with which Mw, and nothing carries that into a group."""
    fields = {f.name for f in dataclasses.fields(ComparisonGroup)}
    assert fields == {"context", "values", "disagreement"}, (
        f"ComparisonGroup's shape changed to {fields}; if it now carries observation identity, "
        "rho may be recoverable from the projection and this record must be re-measured"
    )
    mn_group = groups_for(MN_VALUES)[0]
    mw_group = groups_for(MW_VALUES, variable="weight_average_molar_mass")[0]
    assert all(isinstance(v, float) for v in mn_group.values)
    assert all(isinstance(v, float) for v in mw_group.values), (
        "values are bare floats -- no run identity travels with them"
    )
    assert MEASURED["and_the_pairing_is_destroyed"]["the_decisive_finding"] is True


def test_the_pairing_survives_in_the_evidence_pool():
    """The other half, without which the finding overclaims: the pairing is
    lost in the PROJECTION, not in the evidence."""
    mn = [observation(i, v) for i, v in enumerate(MN_VALUES)]
    mw = [observation(i, v, variable="weight_average_molar_mass")
          for i, v in enumerate(MW_VALUES)]
    by_run = {}
    for obs in mn + mw:
        by_run.setdefault(obs.record_ids[0], []).append(obs.content["variable"])
    assert len(by_run) == len(MN_VALUES)
    assert all(len(v) == 2 for v in by_run.values()), (
        "each run must carry both moments, joinable on its Record -- this is what makes the "
        "finding `the projection loses it` rather than `the substrate cannot hold it`"
    )
    assert "survives IN THE EVIDENCE POOL" in MEASURED[
        "and_the_pairing_is_destroyed"]["what_would_still_hold_it"]


# ------------------------------------------------------------------ the record


def test_the_record_claims_no_acquisition_and_no_proposal():
    assert READINESS["status"] == "blocked_on_representation_not_on_data"
    disclaimers = READINESS["what_this_does_not_claim"]
    assert "no instrument" in disclaimers["not_an_acquisition"]
    assert "measured_not_proposed" in disclaimers["not_a_proposal"]
    assert "is a bug report" in disclaimers["not_a_defect_finding"]

    vertical = loads((REPO_ROOT / "architecture" / "polymer_vertical.yaml").read_text())
    assert vertical["status"] == "measured_not_proposed", (
        "this record must not have advanced the vertical's status"
    )


def test_only_one_precondition_is_irreversible_and_the_record_says_which():
    preconditions = READINESS["what_would_have_to_be_true_before_acquiring"]
    assert set(preconditions) == {"one", "two", "three", "four"}
    assert "unrecoverable if wrong" in preconditions["one"]
    assert preconditions["two"].endswith("SATISFIED."), "the consumer is built"
    assert "SATISFIED, by divergence stated rather than by suppression." in preconditions["three"]
    assert "SATISFIED for the first acquisition path" in preconditions["one"], (
        "the irreversible precondition is discharged by daf/adapters/gpc_report.py"
    )
    outstanding = READINESS["what_remains_outstanding"]
    assert "NONE OF THE FOUR" in outstanding
    assert "not the same as ready" in outstanding, (
        "four satisfied preconditions must not be readable as an acquisition; there is still no "
        "instrument, no polymer and no data"
    )
    assert "FABRICATED" in outstanding
    assert "cannot be repaired after the data exists" in READINESS["the_order_that_matters"]
    assert "discarding a measurement to make a check pass" in preconditions["three"], (
        "the tempting fix for the uncertainty split must be named and refused"
    )


def test_exactly_one_conditions_representation_satisfies_both_constraints():
    """FOUND BY THIS FILE FAILING. The first version of these tests used a
    tuple of pairs for `conditions` -- hashable, so the grouping accepts
    it -- and the table gate refused it with
    CONDITION_KEYS_ARE_NOT_IDENTIFIERS.

    The two layers pull in opposite directions: the grouping requires
    every content value to be natively hashable, and the table gate
    requires `conditions` to be a Mapping with identifier keys. A plain
    dict satisfies the gate and breaks the grouping; a tuple satisfies the
    grouping and is refused by the gate. Phase 34 built FrozenMapping for
    exactly this bind, so the GPC extractor has no choice to make -- but it
    does have a way to get it wrong, silently, in either direction.
    """
    plain = dict(CONDITIONS)
    tuples = tuple(sorted(plain.items()))
    frozen = FrozenMapping(plain)

    assert observation_is_table_alignable(content(1.0, conditions=plain)).admissible
    with pytest.raises(TypeError):
        hash(tuple(sorted(_comparison_context(content(1.0, conditions=plain), "value").items())))

    refusal = observation_is_table_alignable(content(1.0, conditions=tuples))
    assert not refusal.admissible
    assert "CONDITION_KEYS_ARE_NOT_IDENTIFIERS" in list(refusal.reasons)

    assert observation_is_table_alignable(content(1.0, conditions=frozen)).admissible
    hash(tuple(sorted(_comparison_context(content(1.0, conditions=frozen), "value").items())))

    named = READINESS["what_would_have_to_be_true_before_acquiring"]["four"]
    assert "FrozenMapping" in named


def test_the_irreversible_precondition_is_enforced_rather_than_merely_written():
    """The lesson this repository keeps relearning: a policy line in a
    document is not a gate."""
    gate = READINESS["the_irreversible_precondition_is_now_a_gate_rather_than_a_sentence"]
    assert "SILENT" in gate["what_was_wrong_with_leaving_it_as_a_sentence"]
    assert "EVERY_RUN_DIFFERS_IN" in gate["it_is_named_and_not_diagnosed"]
    assert "NOT flagged" in gate["the_discriminating_case"]
    assert "still irreversible" in gate["what_it_changes_about_precondition_one"], (
        "the gate must not be read as having discharged the precondition"
    )

    from science.replicate_pairing import EVERY_RUN_DIFFERS_IN
    assert EVERY_RUN_DIFFERS_IN == "EVERY_RUN_DIFFERS_IN"


def test_the_record_no_longer_names_the_wrong_layer_for_the_irreversible_one():
    """CORRECTED 2026-08-27, by measuring run_scout before building rather
    than by a failure. `the extractor emits one Record per RUN` named the
    layer that cannot discharge it: run_scout builds one Record per
    RawDocument and hands it TO the extractor, so the granularity is the
    adapter's. An author who read this record and wrote only an extractor
    would have violated the one unrepairable precondition while believing
    they had satisfied it."""
    correction = READINESS["the_precondition_named_the_wrong_layer"]
    assert "extractors do not emit Records" in correction["what_is_actually_the_case"]
    assert "ADAPTER" in correction["what_is_actually_the_case"]
    assert "daf/adapters/gpc_report.py" in correction["where_the_obligation_now_lives"]

    modes = correction["the_two_modes"]
    assert "CONFLICTING_VALUE_FOR_A_RUN" in modes["measured"], "the loud mode must be named"
    assert "nothing raises" in modes["why_the_second_is_the_serious_one"], (
        "the silent mode is the serious one and the record must say so"
    )

    # The correction is not merely written: the layer it names is real.
    import inspect

    import scout.pipeline

    source = inspect.getsource(scout.pipeline)
    assert "make_record(document_id=document.id, locator=raw_doc.locator" in source, (
        "if run_scout ever builds Records some other way, this correction needs re-measuring "
        "rather than re-reading"
    )
