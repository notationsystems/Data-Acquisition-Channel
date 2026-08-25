"""`generation_depth_bounded`, corrected from a claim into a measurement.

The invariant said "derivation from derivation is bounded and the depth is
recorded" with `status: vacuously_enforced` and, as its evidence, that a
derivation CYCLE is unconstructible. That evidence is true and does not
support the rule: **acyclicity is not boundedness.** An unbounded acyclic
chain is precisely what a recursive estimator produces -- a Kalman filter
over N timesteps is N derivations deep if depth is read as iteration
count.

The generality probe never caught this because every property it
enumerated was a property of an OBSERVATION, so it had no way to falsify
anything about COMPUTATION. That is recorded as a probe limitation in
`architecture/_probes/generality.yaml`, which now carries a
`computation_properties` list and the first FAIL the probe has ever
returned.

This file enforces what is actually true, in three layers:

  1. the measured absence -- nothing computes, records, or bounds a depth;
  2. the narrower fact that IS enforceable today -- no shipped path can
     construct a derivation-from-derivation chain at all, so the unbounded
     case cannot yet arise here;
  3. the corrected semantics -- recursion count is not lineage depth --
     asserted against a real N-deep chain built by hand, so the
     distinction is measured rather than asserted in prose.

Nothing here weakens the rule. The rule is retained verbatim; the
*status* was corrected downward to match reality.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from evidence.types import make_derived_value, make_observation

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE = REPO_ROOT / "architecture"
INVARIANTS = loads((ARCHITECTURE / "invariants.yaml").read_text())
PROBE = loads((ARCHITECTURE / "_probes" / "generality.yaml").read_text())
VENDOR = REPO_ROOT / "vendor" / "scout-retrieval-agent"

AUTHORED = ("daf", "science", "boundary", "bridge", "epistemics", "assertion")


def _invariant(invariant_id):
    for entry in INVARIANTS["invariants"]:
        if entry["id"] == invariant_id:
            return entry
    raise AssertionError(f"no invariant {invariant_id!r}")


# ------------------------------------------------- 1. the measured absence


def test_no_depth_symbol_is_defined_anywhere():
    """The first clause of the correction, measured rather than asserted:
    no authored module and no vendored evidence module defines a
    depth/generation/lineage symbol."""
    targets = [REPO_ROOT / package for package in AUTHORED]
    targets += [VENDOR / "evidence"]

    found = []
    for root in targets:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.as_posix():
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    lowered = node.name.lower()
                    if any(token in lowered for token in ("generation_depth", "lineage_depth")):
                        found.append(f"{path.name}:{node.name}")
    assert found == [], f"a depth symbol now exists: {found} -- the invariant's status must be revisited"


def test_derived_value_has_no_depth_field():
    """The second clause: the rule says the depth "is recorded". It is
    not -- there is nowhere to record it."""
    from dataclasses import fields

    from evidence.types import DerivedValue

    names = tuple(field.name for field in fields(DerivedValue))
    assert names == ("id", "derived_from", "method", "content", "confidence", "derived_at")
    assert "depth" not in names


def test_the_invariant_declares_no_bound_value():
    entry = _invariant("generation_depth_bounded")
    assert "bound" not in entry, "a numeric bound now exists; enforce it rather than declaring it"
    assert entry["status"] == "represented_unenforced"


def test_ancestry_discards_the_level_at_which_each_node_was_reached():
    """`evidence.provenance.ancestry_of` is the nearest lineage machinery
    that exists, and it is a flat set union -- so even the information a
    depth could be computed FROM is dropped."""
    from dataclasses import fields

    from evidence.provenance import ProvenanceAncestry

    names = {field.name for field in fields(ProvenanceAncestry)}
    assert names == {"root_derived_value_id", "observation_ids", "derived_value_ids"}
    assert not any("depth" in name for name in names)


# --------------------------------- 2. what IS enforceable today, measured


def _observation(value):
    return make_observation(
        record_ids=("r1",),
        extraction_method="x",
        content={"property": "p", "value": value, "unit": "m"},
        confidence=1.0,
        extracted_at="2020-01-01T00:00:00Z",
    )


def test_no_shipped_path_constructs_a_derivation_from_a_derivation():
    """The narrower, honest claim the corrected evidence line makes: the
    unbounded case cannot arise here yet, because nothing in this
    repository ever derives from a derivation.

    Measured by AST over every authored package: `make_derived_value` is
    called nowhere outside tests and the storage round trip."""
    callers = []
    for package in AUTHORED:
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if "__pycache__" in path.as_posix():
                continue
            source = path.read_text()
            if "make_derived_value" not in source:
                continue
            # serialization reconstructs a persisted DerivedValue; it never
            # originates one, and it is the only permitted mention.
            if path.as_posix().endswith("daf/storage/serialization.py"):
                continue
            callers.append(path.relative_to(REPO_ROOT).as_posix())
    assert callers == [], f"a derivation path now exists in {callers}; the vacuity claim is dead"


def test_a_derivation_cycle_remains_unconstructible():
    """The one clause of the ORIGINAL evidence line that was true, kept
    and re-verified: content-addressed identity means two DerivedValues
    naming each other could never have either id computed."""
    observation = _observation(1.0)
    first = make_derived_value(
        derived_from=(observation.id,), method="m", content={"value": 2.0},
        confidence=1.0, derived_at="2020-01-01T00:00:00Z",
    )
    second = make_derived_value(
        derived_from=(first.id,), method="m", content={"value": 3.0},
        confidence=1.0, derived_at="2020-01-01T00:00:00Z",
    )
    assert second.derived_from == (first.id,)
    assert first.id != second.id
    # To close the cycle, `first` would have to name `second.id`, which is
    # a function of `first.id` -- unconstructible, not merely forbidden.
    assert observation.id not in (first.id, second.id)


# ------------------------------------- 3. the corrected semantic domain


def test_a_deep_chain_is_constructible_so_acyclicity_is_not_boundedness():
    """The precise defect, demonstrated: nothing stops an arbitrarily deep
    acyclic chain. This is what a recursive estimator would produce, and
    it is why the original evidence line did not support the rule."""
    current = _observation(0.0)
    chain = [current.id]
    for step in range(1, 51):
        derived = make_derived_value(
            derived_from=(chain[-1],), method="recursive_step",
            content={"value": float(step)}, confidence=1.0, derived_at="2020-01-01T00:00:00Z",
        )
        chain.append(derived.id)

    assert len(chain) == 51
    assert len(set(chain)) == 51, "every link is distinct -- the chain is acyclic and unbounded"


def test_recursion_count_is_not_evidence_lineage_depth():
    """The corrected semantics, asserted as the probe requires: N filter
    iterations over ONE measurement stream are ONE lineage step, not N.

    Modelled the way the corrected domain prescribes -- a recursive
    computation carries `stream_identity` and `initialization_provenance`
    and derives from the STREAM, not from its own previous iterate."""
    stream = tuple(_observation(float(i)).id for i in range(64))

    def recursive_state(iterations):
        return make_derived_value(
            derived_from=stream,
            method="recursive_estimator",
            content={
                "stream_identity": "noaa:8454000:water_level",
                "window_or_horizon": f"0:{iterations}",
                "initialization_provenance": "measured",
                "iterations": iterations,
            },
            confidence=1.0,
            derived_at="2020-01-01T00:00:00Z",
        )

    shallow, deep = recursive_state(2), recursive_state(100000)

    # Iteration count changes identity (it is a computationally relevant
    # parameter) but NOT the lineage: both derive from the same stream.
    # `make_derived_value` sorts `derived_from`, so compare against the
    # sorted form rather than the construction order.
    assert shallow.id != deep.id
    assert shallow.derived_from == deep.derived_from == tuple(sorted(stream))

    for state in (shallow, deep):
        assert set(state.derived_from) == set(stream), "lineage is the stream, never the iterate"
        assert state.content["initialization_provenance"] == "measured"


def test_initialization_from_a_computed_prior_inherits_that_lineage():
    """The other half of the corrected domain: a trajectory begun from a
    computed prior must say so, and its lineage runs through the prior."""
    stream = tuple(_observation(float(i)).id for i in range(8))
    prior = make_derived_value(
        derived_from=stream, method="recursive_estimator",
        content={"stream_identity": "s", "window_or_horizon": "0:8",
                 "initialization_provenance": "measured"},
        confidence=1.0, derived_at="2020-01-01T00:00:00Z",
    )
    continued = make_derived_value(
        derived_from=(prior.id,), method="recursive_estimator",
        content={"stream_identity": "s", "window_or_horizon": "8:16",
                 "initialization_provenance": f"computed({prior.id})"},
        confidence=1.0, derived_at="2020-01-01T00:00:00Z",
    )

    assert continued.derived_from == (prior.id,)
    assert continued.content["initialization_provenance"].startswith("computed(")
    assert prior.id in continued.content["initialization_provenance"], (
        "a computed initialization must name the prior it inherits lineage from"
    )
    assert continued.derived_from != tuple(sorted(stream)), (
        "a continued trajectory derives from its prior, not directly from the stream -- "
        "that is what makes the inherited lineage visible"
    )


# ------------------------------------------------ 4. the probe correction


def test_the_probe_now_covers_recursive_computation():
    assert PROBE["computation_properties"] == ["recursive_computation"]
    assert "recursive_computation" not in PROBE["observation_properties"], (
        "recursive_computation is a computation property; listing it as an observation "
        "property would be the category error the probe's own note warns about"
    )


def test_the_probe_records_the_failure_rather_than_a_pass():
    assert PROBE["result"]["recursive_computation"]["verdict"] == "FAIL"
    assert PROBE["outcome"]["failed"] == ["recursive_computation"]
    assert PROBE["outcome"]["core_invariants_modified"] == 0, (
        "a truthfulness repair to a status is not a core-invariant modification; if a core "
        "invariant ever is modified, this number must change and the probe must be re-run"
    )


def test_the_probe_is_still_paper_only():
    """The probe's status is load-bearing and this phase must not have
    quietly given it an implementation."""
    assert PROBE["status"] == "paper_only"


def test_the_rule_text_was_not_weakened():
    """The correction lowered the STATUS to match reality. Weakening the
    RULE to make recursion pass is what the brief forbids."""
    assert _invariant("generation_depth_bounded")["rule"] == (
        "derivation from derivation is bounded and the depth is recorded"
    )


def test_the_corrected_semantic_domain_is_recorded():
    entry = _invariant("generation_depth_bounded")
    domain = entry["corrected_semantic_domain"]
    assert "EVIDENCE LINEAGE" in domain
    assert "never computation iteration count" in domain
    for required in ("stream_identity", "window_or_horizon", "initialization_provenance"):
        assert required in domain


# ------------------------- 5. the meta-test that let this through, fixed


def test_every_invariant_naming_an_enforcement_test_file_has_one_that_runs():
    """THE VERIFICATION-SUBSTRATE DEFECT THAT HID THIS FOR 35 PHASES.

    `test_the_invariant_ledger_names_every_test_in_this_file_it_claims`
    (tests/test_epistemic_boundary.py) asserts only that the named set is
    non-empty and contains two hardcoded ids. It never checks that a given
    invariant corresponds to any test function, which is exactly why
    `generation_depth_bounded` could name an enforcement file containing
    nothing about it and stay green.

    Measuring it exposed that this is NOT a `generation_depth_bounded`
    problem -- 17 other invariants also name an enforcement file that
    never mentions them. Forcing all 17 to change belongs to a phase about
    them, not to this one, so this test does the disciplined thing: it
    LOCKS the current set so it can cannot grow, and asserts that
    `generation_depth_bounded` is no longer in it.

    Traceability here means the named file mentions the invariant id. That
    is a weak bar deliberately -- it is the bar the ledger's own claim of
    enforcement should already clear, and 18 entries did not."""
    untraceable = set()
    for entry in INVARIANTS["invariants"]:
        enforcement = entry.get("enforcement")
        if not enforcement:
            continue
        for named in (part.strip() for part in enforcement.split(",")):
            if not named.endswith(".py") or not named.startswith("tests/"):
                continue
            path = REPO_ROOT / named
            assert path.exists(), f"{entry['id']}: {named} does not exist"
            if entry["id"] not in path.read_text():
                untraceable.add(entry["id"])

    assert "generation_depth_bounded" not in untraceable, (
        "the invariant this phase corrected must be traceable to its named enforcement"
    )

    known_pre_existing = {
        "prediction_carries_uncertainty",
        "training_admissibility_declared",
        "acquisition_first_control_loop",
        "return_edge_is_exclusive",
        "execution_is_not_evidence",
        "execution_identity_is_separate",
        "rejection_rate_is_a_metric",
        "refusal_reachability_declared",
        "unclassified_backlog_is_a_metric",
        "failed_execution_retained",
        "doctrine_source_is_canonical",
        "doctrine_regeneration_is_deterministic",
        "generated_doctrine_matches_source",
        "doctrine_budget_enforced",
        "no_vendor_in_doctrine",
        "no_self_validation",
        "builder_check_lineage_recorded",
    }
    assert untraceable <= known_pre_existing, (
        "a NEW invariant now claims enforcement that names nothing: "
        f"{sorted(untraceable - known_pre_existing)}"
    )
    assert untraceable == known_pre_existing, (
        "an invariant became traceable -- remove it from known_pre_existing rather than "
        f"leaving the lock stale: {sorted(known_pre_existing - untraceable)}"
    )


@pytest.mark.parametrize("invariant_id", ["generation_depth_bounded", "no_circular_training"])
def test_the_two_vacuity_style_invariants_both_have_real_checks(invariant_id):
    """`no_circular_training` always had a real grep-based check;
    `generation_depth_bounded` was the only one in the ledger whose named
    enforcement contained nothing about it. Both are now traceable."""
    entry = _invariant(invariant_id)
    named = entry["enforcement"].split(",")[0].strip()
    assert invariant_id in (REPO_ROOT / named).read_text()
