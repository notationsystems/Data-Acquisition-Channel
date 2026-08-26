"""Can DAF represent a MULTIVARIATE observation, or a STRUCTURED
uncertainty? Measured, and locked so the answer cannot drift.

These are the two capabilities the compute layer's Kalman requirement
depends on, and they are the rows that decide whether that workload is
buildable at all. Both answers are "no". They are not, however, the same
kind of no, and the difference is the finding:

    shape                       gate          identity        consumer
    --------------------------  ------------  --------------  -----------------
    scalar value + scalar u.    admissible    stable          groups OK
    VECTOR value (section 7)    REFUSED       stable          groups OK
    COVARIANCE u. (section 8)   admissible    stable          TypeError
    both (what Kalman needs)    REFUSED       stable          TypeError

Section 7 fails EARLY and LOUDLY: `quantity_is_typed` type-checks `value`
and refuses a non-scalar with a named code, so nothing downstream ever
sees it.

Section 8 fails LATE and SILENTLY: `quantity_is_typed` checks only that
`uncertainty` is not None when the kind is substantive. It never inspects
the value, so a covariance matrix is ADMITTED, receives a real and stable
`content_hash`, and would be persisted as a valid typed quantity. The
failure surfaces only when something tries to COMPARE it -- as
`TypeError: unhashable type: 'list'` in `materials.analysis` -- which is
the Phase 33 unhashable-container defect one level deeper, in a field
nobody has looked at it in.

WHY THIS MAKES THEM ONE EXTENSION AND NOT TWO. The tempting reading is
that these are independent gaps that could be closed independently. They
are not, and `test_admitting_a_vector_value_alone_would_widen_the_hole`
is the reason: relaxing section 7's type check on its own converts
section 8's loud gate refusal into the silent late TypeError, because a
vector value is a sequence and meets exactly the same unhashable-consumer
fate as a covariance. Fixing the visible half first makes the invisible
half worse. Whatever closes either must close both, which means one
decision about non-scalar quantities, not two.

CHARACTERIZATION, NOT POLICY -- the same discipline
`test_persistent_condition_lifecycle.py` establishes. Nothing here changes
production behaviour, no validator is added, no gate is relaxed. The gaps
are recorded in `architecture/nonscalar_quantity.yaml` and locked here.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from evidence.identity import content_hash
from materials.analysis import _comparison_context, _group_by_comparison_context

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from daf.storage.frozen_mapping import FrozenMapping, freeze_nested_mappings
from science.admissibility import (
    UNTYPED_QUANTITY,
    no_context_free_property,
    quantity_is_typed,
)

#: A fully-admissible scalar observation. `conditions` is a FrozenMapping
#: because a plain dict is itself unhashable (Phase 33/34) -- using one
#: here would make every consumer check below fail for the WRONG reason.
BASE = {
    "property": "water_level",
    "method": "CO-OPS 6-minute average",
    "unit": "m",
    "conditions": FrozenMapping({"datum": "MLLW"}),
    "uncertainty_kind": "stated",
}

VECTOR = [1.83, 2.01, 1.94]
COVARIANCE = [[0.004, 0.0], [0.0, 0.009]]


def _groups(content):
    return _group_by_comparison_context([(_comparison_context(content, "value"), 1.0)])


# ===================================================== the scalar baseline

def test_the_scalar_case_is_admissible_and_comparable():
    """The control. Every claim below is a departure from this row, so if
    this one breaks the others measure nothing."""
    content = {**BASE, "value": 1.83, "uncertainty": 0.004}
    assert no_context_free_property(content).admissible is True
    assert content_hash(dict(content))
    assert len(_groups(content)) == 1


# ============================================ section 7: multivariate value

@pytest.mark.parametrize("vector", [VECTOR, tuple(VECTOR), {"x": 1.83, "y": 2.01}])
def test_a_multivariate_value_is_refused_by_the_gate(vector):
    """`quantity_is_typed` requires `value` to be a real int/float. A
    measurement vector, in any container, is refused with a named code --
    list, tuple and per-variable mapping alike, so the refusal is about
    non-scalarness and not about one container type."""
    verdict = quantity_is_typed({**BASE, "value": vector, "uncertainty": 0.004})
    assert verdict.admissible is False
    assert UNTYPED_QUANTITY in verdict.reasons


def test_the_multivariate_refusal_is_early_and_therefore_harmless():
    """Loud and early: refused at the gate, so no downstream consumer is
    ever handed one. An honest absence."""
    content = {**BASE, "value": VECTOR, "uncertainty": 0.004}
    assert no_context_free_property(content).admissible is False
    assert len(_groups(content)) == 1, "the scalar uncertainty still groups fine"


# ======================================== section 8: structured uncertainty

def test_a_covariance_uncertainty_is_silently_admitted():
    """THE FINDING. `quantity_is_typed` never inspects `uncertainty`'s
    value -- only that it is not None when the kind is substantive. A 2x2
    covariance is therefore ADMITTED as a well-typed quantity."""
    content = {**BASE, "value": 1.83, "uncertainty": COVARIANCE}
    verdict = no_context_free_property(content)
    assert verdict.admissible is True, "measured: the gate does not refuse it"
    assert verdict.reasons == ()


def test_a_covariance_uncertainty_gets_a_real_and_stable_identity():
    """Worse than admitted: it is identity-stable, so such an Observation
    would be persisted with a genuine content_hash and look entirely
    healthy at rest."""
    content = {**BASE, "value": 1.83, "uncertainty": COVARIANCE}
    first = content_hash(dict(content))
    assert first and first == content_hash(dict(content))


def test_a_covariance_uncertainty_breaks_the_real_consumer():
    """...and fails only at comparison time, as the Phase 33 defect one
    level deeper: `materials.analysis` needs every content value natively
    hashable, and a nested list is not."""
    content = {**BASE, "value": 1.83, "uncertainty": COVARIANCE}
    with pytest.raises(TypeError, match="unhashable"):
        _groups(content)


def test_freeze_nested_mappings_does_not_rescue_a_sequence():
    """The Phase 34 repair is Mapping-shaped. A covariance is
    Sequence-shaped, so the existing read-side fix passes it straight
    through, still unhashable. There is no FrozenSequence counterpart."""
    frozen = freeze_nested_mappings({"uncertainty": COVARIANCE})
    assert isinstance(frozen["uncertainty"], list)
    with pytest.raises(TypeError, match="unhashable"):
        hash(frozen["uncertainty"])


def test_a_tuple_survives_construction_but_not_the_round_trip():
    """Why "just use a tuple" is not the answer: a tuple is hashable in
    memory, but JSON has one sequence type, so it reconstructs as a list
    on hydration and the hashability is silently lost. Exactly the
    same-process-versus-reopen asymmetry Phase 35 measured for Mappings."""
    assert hash(tuple(VECTOR))
    rehydrated = json.loads(json.dumps({"v": tuple(VECTOR)}))["v"]
    assert isinstance(rehydrated, list)
    with pytest.raises(TypeError, match="unhashable"):
        hash(rehydrated)


# =========================================== why they are ONE extension

def test_admitting_a_vector_value_alone_would_widen_the_hole():
    """The coupling argument, measured rather than asserted.

    Suppose section 7 were closed on its own by relaxing the type check so
    a vector value is admitted. That value is a sequence, so it then meets
    the SAME unhashable consumer that a covariance meets -- and the
    failure moves from a named refusal at the gate to a TypeError deep in
    analysis. Closing the visible half first makes the invisible half
    worse, so neither can be closed alone.

    Simulated here by checking the two properties that would then hold,
    without modifying the real gate."""
    content = {**BASE, "value": VECTOR, "uncertainty": 0.004}

    # today: refused, loudly, at the gate
    assert UNTYPED_QUANTITY in quantity_is_typed(content).reasons

    # a hypothetically-relaxed gate would hand this to the consumer, and
    # the consumer cannot hash a sequence-valued `value` any more than a
    # sequence-valued `uncertainty`.
    with pytest.raises(TypeError, match="unhashable"):
        hash(content["value"])

    # ...which is the identical failure mode section 8 already has.
    with pytest.raises(TypeError, match="unhashable"):
        hash(COVARIANCE)


# ================================ was the hole ever actually reached?

def test_no_extractor_emits_a_nonscalar_uncertainty():
    """Forensics, because the answer decides whether the fix is only
    forward. If a covariance-bearing Observation had ever been
    content-addressed and referenced, repair would have to reach back.

    Measured: exactly one extractor emits `uncertainty` at all, and it
    emits `sigma`, a scalar parsed by `_optional_float`."""
    extractors = pathlib.Path(__file__).resolve().parent.parent / "daf" / "extractors"
    emitters = [p.name for p in sorted(extractors.glob("*.py"))
                if 'content["uncertainty"]' in p.read_text()]
    assert emitters == ["noaa_water_level_measurements.py"], emitters
    source = (extractors / "noaa_water_level_measurements.py").read_text()
    assert 'content["uncertainty"] = sigma' in source
    assert "_optional_float" in source, "sigma is parsed as a scalar float, not passed through"


def test_no_committed_fixture_carries_a_nonscalar_uncertainty():
    """The other half of the forensic question: nothing already stored
    carries one either. Scanned across every committed JSON fixture."""
    root = pathlib.Path(__file__).resolve().parent.parent
    hits = []

    def walk(node, where):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "uncertainty" and value is not None and \
                        not isinstance(value, (int, float)) or \
                        (key == "uncertainty" and isinstance(value, bool)):
                    hits.append(f"{where}:{key}={value!r}")
                walk(value, where)
        elif isinstance(node, list):
            for item in node:
                walk(item, where)

    for path in sorted((root / "tests" / "fixtures").rglob("*.json")):
        try:
            walk(json.loads(path.read_text()), path.name)
        except ValueError:
            continue
    assert not hits, f"a non-scalar uncertainty is already committed: {hits}"


def test_but_the_pass_through_extractor_would_carry_one_verbatim():
    """UNREACHED IS NOT UNREACHABLE, and this is the difference.

    `graph_dataset` consumes `entities`/`relations` as structure and
    passes EVERY other key into Observation.content unmodified, by
    design. So a source record declaring a covariance would be carried
    through, admitted by the gate, and content-addressed -- the hole is
    closed today by what sources happen to send, not by any check.

    This is the same shape as the Phase 35 finding for `conditions`,
    where that extractor's verbatim pass-through produced a plain,
    unhashable dict. Same extractor, same mechanism, different field."""
    source = (pathlib.Path(__file__).resolve().parent.parent
              / "daf" / "extractors" / "graph_dataset.py").read_text()
    assert "passed through verbatim" in source or "unmodified" in source
    # and the gate would not stop it, which is the measured half
    content = {**BASE, "value": 1.83, "uncertainty": COVARIANCE}
    assert no_context_free_property(content).admissible is True


def test_both_gaps_share_one_constraint_surface():
    """Whatever represents a non-scalar quantity must satisfy all three
    consumers at once, which is what makes this one decision. Measured
    from architecture/condition_representation.yaml's own inventory."""
    for shape in (VECTOR, COVARIANCE):
        json.dumps(shape)                      # content_hash: OK
        with pytest.raises(TypeError):         # materials.analysis: NOT OK
            hash(shape)
    # and the Mapping half of the surface is already solved, which is the
    # precedent the sequence half does not yet have.
    assert hash(FrozenMapping({"a": 1}))
    assert json.dumps(FrozenMapping({"a": 1})) == '{"a": 1}'


def test_two_extractors_pass_arbitrary_content_through_verbatim():
    """The exposure is not bounded by what extractors currently EMIT,
    because two of them emit whatever they are given.

    `graph_dataset` consumes entities/relations as structure and passes
    every other key through; `local_dataset` passes the entire parsed JSON
    object through with no structural extraction at all -- broader still.
    So the §8 repair has to tighten this route, not only add covariance
    support, or the next unhashable shape arrives the same way. Recorded
    in architecture/nonscalar_quantity.yaml pass_through_path."""
    extractors = pathlib.Path(__file__).resolve().parent.parent / "daf" / "extractors"

    local = (extractors / "local_dataset.py").read_text()
    assert "content = json.loads(record.raw_content)" in local
    assert "content=content," in local, "local_dataset hands the parsed object straight to content"

    graph = (extractors / "graph_dataset.py").read_text()
    assert "verbatim" in graph or "unmodified" in graph

    # neither inspects a value's SHAPE on the way in
    for source, name in ((local, "local_dataset"), (graph, "graph_dataset")):
        assert "isinstance(value, (int, float))" not in source, (
            f"{name} appears to type-check content values; update this test if it now does")
