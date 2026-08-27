"""The cohort-identity probe, RUN -- against expectations recorded first.

architecture/_probes/cohort_identity_expectations.yaml was committed in
eeb1c36, before this file existed, and this file READS it rather than
restating it. A probe carrying its own expectations can have them adjusted
in the commit that makes them hold.

THE DISCIPLINE THIS PROBE EXISTS TO DEMONSTRATE. Confirming a gate was
REACHED is not confirming WHICH gate. Every case names the ids it expects,
so three outcomes are distinguishable where a refusal count would collapse
them to two:

    admitted, as predicted                     the prediction held
    refused with a PREDICTED id                the prediction held
    refused with an UNPREDICTED id             THE GATE WAS REACHED AND
                                               THE CLAIM IS UNSUPPORTED

The third is the one a probe reporting "refused, as expected" would hide,
and it is the same shape as the alias check that asserted answered ==
selected: a correct answer to the wrong question passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import daf  # noqa: F401
from epistemics._yaml import loads

from science.admissibility import no_context_free_property, quantity_is_typed
from science.structured_uncertainty import uncertainty_corresponds_to_value
from science.table import observation_is_table_alignable

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTATIONS = loads(
    (REPO_ROOT / "architecture" / "_probes"
     / "cohort_identity_expectations.yaml").read_text())
CASES = {case["name"]: case for case in EXPECTATIONS["cases"]}

BATCH = "PS-lot-4471"
CONDITIONS = {"solvent": "THF", "column_calibration": "polystyrene_standards"}


#: THE GATES GOVERN DIFFERENT CONTENT SHAPES, and the first version of
#: this probe ignored that -- it fed TABLE-shaped content to the PROPERTY
#: gates and collected MISSING_PROPERTY, MISSING_METHOD,
#: MISSING_UNCERTAINTY_KIND and UNTYPED_QUANTITY. Four of five cases
#: "failed the prediction", and none of those refusals had anything to do
#: with cohorts: they were refusals about the shape being wrong for the
#: gate being asked.
#:
#: THAT IS THE EXACT FAILURE THIS PROBE WAS BUILT TO DETECT, occurring in
#: the probe. Counting refusals would have concluded "the substrate
#: refuses polymer observations" -- a gate reached, and a claim entirely
#: unsupported. The named-id discipline is what made it legible, because
#: none of the four ids was a cohort id.
#:
#: So each case is now expressed in BOTH shapes and each gate sees only
#: the shape it governs. A gate applied to content it does not govern
#: produces refusals that are not evidence.
TABLE_GATES = (observation_is_table_alignable, uncertainty_corresponds_to_value)
PROPERTY_GATES = (quantity_is_typed, no_context_free_property)


def _table_shape(**overrides):
    content = {
        "sample_id": BATCH,
        "property": "number_average_molar_mass",
        "conditions": dict(CONDITIONS),
        "value": 104000.0,
        "unit": "g/mol",
    }
    content.update(overrides)
    return content


def _property_shape(**overrides):
    content = {
        "property": "number_average_molar_mass",
        "method": "gel_permeation_chromatography",
        "conditions": dict(CONDITIONS),
        "value": 104000.0,
        "unit": "g/mol",
        "uncertainty": 1200.0,
        "uncertainty_kind": "stated",
    }
    content.update(overrides)
    return content


def _all_gate_reasons(shapes):
    """Refusals from each gate over ONLY the shape it governs."""
    reasons = set()
    for gates, content in ((TABLE_GATES, shapes.get("table")),
                           (PROPERTY_GATES, shapes.get("property"))):
        if content is None:
            continue
        for gate in gates:
            verdict = gate(content)
            if not verdict.admissible:
                reasons |= set(verdict.reasons)
    return reasons


def _judge(case_name, content):
    """Compare against the recorded expectation, distinguishing a refusal
    by a PREDICTED gate from a refusal by an unpredicted one."""
    case = CASES[case_name]
    predicted_ids = set(case["expected_refusal_ids"])
    actual = _all_gate_reasons(content)

    if case["expected_admitted"]:
        assert not actual, (
            f"{case_name}: predicted ADMITTED, refused by {sorted(actual)}. "
            f"{case['what_a_refusal_would_mean']}")
    else:
        assert actual, f"{case_name}: predicted refusal {sorted(predicted_ids)}, admitted"
        unpredicted = actual - predicted_ids
        assert not unpredicted, (
            f"{case_name}: refused by {sorted(unpredicted)}, which the expectation did "
            f"not name. THE GATE WAS REACHED AND THE CLAIM IS UNSUPPORTED -- a refusal "
            f"is not evidence for the mechanism that was predicted to produce it.")
        assert predicted_ids <= actual, (
            f"{case_name}: predicted {sorted(predicted_ids)} but only {sorted(actual)} fired")


# --------------------------------------------------- the probe's own guard --

def test_the_expectations_predate_this_run():
    """The claim that makes every comparison below meaningful, checked
    against git rather than taken on the file's word."""
    import subprocess

    def added_in(relative):
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", relative],
                             cwd=str(REPO_ROOT), capture_output=True, text=True)
        return out.stdout.split()[-1] if out.stdout.strip() else None

    expectations = added_in("architecture/_probes/cohort_identity_expectations.yaml")
    run = added_in("tests/test_cohort_identity_probe.py")
    if not expectations or not run:
        pytest.skip("one of the two files is not yet committed")
    assert expectations != run, (
        "the expectations and the run were added in the SAME commit, so the "
        "predictions do not demonstrably predate the measurement")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", expectations, run],
                              cwd=str(REPO_ROOT), capture_output=True)
    assert ancestor.returncode == 0, "the run does not descend from the expectations"


def test_every_recorded_case_is_actually_run():
    """No case may be recorded and quietly skipped -- a probe that predicts
    five things and measures three reports on five."""
    run_here = {name for name in CASES if f"case_{name}" in globals()}
    assert run_here == set(CASES), (
        f"recorded but not run: {sorted(set(CASES) - run_here)}")


# ------------------------------------------------------------ the cases --

def case_a_population_as_a_referent():
    from evidence.types import make_referent
    referent = make_referent(natural_key=BATCH, kind="polymer_batch")
    assert referent.kind == "polymer_batch"
    return {}          # nothing to feed a content gate; the constructibility IS the case


def case_a_distribution_moment_as_a_scalar_measurement():
    return {"table": _table_shape(), "property": _property_shape()}


def case_the_full_distribution_as_the_value():
    # only the TABLE gate governs a composite value; quantity_is_typed
    # refuses every non-scalar by design, which is its own decision and
    # not a statement about cohorts
    return {"table": _table_shape(value=[9.8e4, 1.02e5, 1.06e5, 1.11e5],
                                  unit=["g/mol"] * 4)}


def case_pdi_as_a_ratio_with_no_lineage_to_its_moments():
    return {"table": _table_shape(property="polydispersity_index", value=1.05,
                                  unit="dimensionless"),
            "property": _property_shape(property="polydispersity_index", value=1.05,
                                        unit="dimensionless")}


def case_a_scalar_uncertainty_on_a_distribution_moment():
    return {"table": _table_shape(uncertainty=1200.0, uncertainty_kind="stated"),
            "property": _property_shape()}


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_planted_case_matches_its_recorded_expectation(name):
    content = globals()[f"case_{name}"]()
    if content:
        _judge(name, content)
    else:
        assert CASES[name]["expected_admitted"] is True


def test_no_gate_names_a_cohort_concept_at_all():
    """The survey the expectations were derived from, re-run here rather
    than trusted. If a code naming the concept appears later, the
    expectation's basis has changed and this fails."""
    import glob
    import re

    codes = set()
    for path in glob.glob(str(REPO_ROOT / "science" / "*.py")):
        codes |= set(re.findall(r'^[A-Z][A-Z_0-9]+ = "([A-Z_0-9]+)"',
                                Path(path).read_text(), re.M))
    assert len(codes) >= 40, f"only {len(codes)} refusal codes found; the survey has drifted"
    naming = {c for c in codes
              if re.search(r"COHORT|POPULATION|DISTRIB|BATCH|ENSEMBLE|AGGREGATE", c)}
    expected = EXPECTATIONS["refusal_vocabulary_measured_before_stating_expectations"]
    assert len(naming) == expected["codes_naming_a_cohort_concept"], (
        f"the vocabulary changed: {sorted(naming)} now name a cohort concept, where the "
        f"expectation recorded {expected['codes_naming_a_cohort_concept']}")
