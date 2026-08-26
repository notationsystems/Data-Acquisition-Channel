"""Phase 37: the aligned observation table, and the sentinel hole it closed.

WHAT THIS PHASE BUILT AND WHY IT IS ONE DELIVERABLE. The joint decision
record elected `least_squares` PAIRED with the DAQ extension that
unblocks it. The pairing is what makes it a decision rather than a wish,
so the extension and its named consuming workload land together. The
extension's two DAQ-owned requirements, quoted from the compute layer's
own exchange artifact, are `stable_sample_and_variable_identity` and
`explicit_missing_value_semantics`; `science/table.py` is the gate that
enforces them.

THE FOURTH INSTANCE OF THE SAME PATTERN. `absent` is now a
fourth-instance pattern in this project: `uncertainty_kind: absent`
(Phase 30), the Fourier metrics DAQ refuses to fabricate (Phase 36),
Δt-as-sentinel (Phase 36), and now missing table values. In every one of
them the rule is identical -- ABSENT MUST NOT BE ENCODABLE AS AN IN-RANGE
VALUE, NaN INCLUDED. NaN is the tempting encoding here precisely because
it is a float, and this file measures what that bought before it was
refused.

THE §7/§8 ASYMMETRY APPLIES HERE TOO. This is not the covariance
finding, but it is the same SHAPE: a partially-typed table admitted at
the gate and failing at a consumer later is a silent, late failure, and
a refusal at the gate is a loud, early one. So the gate checks the
table's ELEMENT TYPES, not merely the presence of its fields -- an int
sample id and the str form of the same number are different join keys,
and nothing downstream says so.

THE PASS-THROUGH ROUTES WERE THE LIVE RISK. A gate is enforceable only
on the paths that reach it. `local_dataset` passed the entire parsed
JSON object with no structural extraction; `graph_dataset` passed any
non-structural key verbatim. An aligned table arriving through either
bypassed whatever the extension enforced, so both are tightened here at
the seam they share -- see `daf/extractors/_passthrough.py`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from daf.extractors._passthrough import PassthroughRefusal, tighten_passthrough_content
from daf.extractors.graph_dataset import GraphDatasetExtractor
from daf.extractors.local_dataset import LocalDatasetExtractor
from daf.storage.filesystem_store import FilesystemEvidenceStore
from daf.storage.frozen_mapping import FrozenMapping
from evidence.identity import content_hash
from evidence.types import make_observation, make_record
from science import table
from science.admissibility import (
    NON_FINITE_QUANTITY,
    NON_FINITE_UNCERTAINTY,
    no_context_free_property,
    quantity_is_typed,
)
from science.table import observation_is_table_alignable

ALIGNED_CELL = {
    "sample_id": "specimen-07",
    "variable": "tensile_strength",
    "value": 78.4,
    "unit": "MPa",
}

ABSENT_CELL = {
    "sample_id": "specimen-07",
    "variable": "elongation_pct",
    "value_absence": table.BELOW_DETECTION,
    "unit": "percent",
}


def _typed_property(**overrides):
    content = {
        "property": "tensile_strength", "value": 78.4, "unit": "MPa",
        "method": "astm-d638", "uncertainty": 0.4, "uncertainty_kind": "stated",
        "conditions": FrozenMapping({"temperature_c": 23}),
    }
    content.update(overrides)
    return content


# ================================= 1. what NaN bought before it was refused
#
# Measured, not asserted from reading the code. Every one of these was
# true of this repository before this phase, which is why the refusal is
# at the gate rather than left to a downstream consumer.


def test_the_canonical_hash_of_a_nan_value_is_taken_over_invalid_strict_json():
    """`content_hash` uses `json.dumps`, whose default `allow_nan=True`
    emits a BARE `NaN` token. That is a Python extension, not JSON: no
    conformant reader in another language will accept it. So an
    Observation.id computed over such content identifies bytes that only
    Python can read back -- in a project whose whole identity story is
    content addressing across processes and languages."""
    serialized = json.dumps(
        {"property": "p", "unit": "m", "value": float("nan")},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    assert serialized == '{"property":"p","unit":"m","value":NaN}'

    with pytest.raises(ValueError):
        json.loads(serialized, parse_constant=_refuse)

    # ...and it hashes perfectly happily, which is exactly the problem.
    assert content_hash({"property": "p", "unit": "m", "value": float("nan")})


def _refuse(constant):
    raise ValueError(f"strict JSON has no {constant}")


def test_the_store_now_refuses_the_write_that_used_to_persist_a_literal_nan(tmp_path):
    """INVERTED, and the inversion is the writer repair landing.

    This began as a characterization test of what a NaN actually did:
    `FilesystemEvidenceStore` wrote the literal `NaN` to disk, so the
    stored file was not valid JSON, and `back.content["value"] !=
    back.content["value"]` came back True -- an equality check that
    would catch a corrupted round trip returning False for an INTACT
    one.

    With `allow_nan=False` at the writer there is no round trip to
    characterize: the write refuses. So the assertion becomes that the
    refusal happens and that nothing reaches disk, which is the property
    that actually matters -- a partially-written store would be worse
    than the literal it replaced."""
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    observation = make_observation(
        record_ids=("r1",), extraction_method="test",
        content={"property": "p", "unit": "m", "value": float("nan")},
        confidence=1.0, extracted_at="2020-01-01T00:00:00Z",
    )

    with pytest.raises(ValueError, match="not JSON compliant"):
        store.put_observation(observation)

    # Nothing partial survives the refusal, and no file on disk carries
    # the literal that used to be written there.
    for path in (tmp_path / "evidence").rglob("*"):
        # bytes, not text: the store's tree also holds non-UTF-8 blobs, and
        # a decode error here would mask the thing being checked.
        if path.is_file():
            assert b"NaN" not in path.read_bytes(), f"{path} still carries the literal"

    # The reflexivity break itself is unchanged -- it is a property of the
    # float, not of the store -- which is precisely why the value must
    # never be allowed to reach a place where something compares it.
    value = observation.content["value"]
    assert math.isnan(value) and value != value


# ============================== 2. the property gate refuses the sentinel


@pytest.mark.parametrize("sentinel", [float("nan"), float("inf"), float("-inf")])
def test_every_non_finite_quantity_is_now_refused(sentinel):
    """MEASURED BEFORE THE FIX: all three were ADMISSIBLE through the
    full gate. Every `isinstance(value, (int, float))` check in
    `science/admissibility.py` passed them, because NaN and the
    infinities ARE floats. The type check was never the wrong check --
    it was simply not sufficient, and finiteness is the missing half."""
    verdict = quantity_is_typed(_typed_property(value=sentinel))
    assert not verdict.admissible
    assert NON_FINITE_QUANTITY in verdict.reasons

    full = no_context_free_property(_typed_property(value=sentinel))
    assert not full.admissible and NON_FINITE_QUANTITY in full.reasons


@pytest.mark.parametrize("sentinel", [float("nan"), float("inf")])
def test_a_non_finite_uncertainty_is_refused_separately(sentinel):
    """A separate reason code because it is a separate claim. An
    infinite uncertainty is not "unknown" -- `uncertainty_kind: absent`
    is how this repository says unknown, and has been since Phase 30.
    Letting infinity mean it would be a fifth encoding of absence
    competing with the explicit one."""
    verdict = quantity_is_typed(_typed_property(uncertainty=sentinel))
    assert not verdict.admissible
    assert NON_FINITE_UNCERTAINTY in verdict.reasons


def test_finite_quantities_are_unaffected():
    """The refusal must not widen. Zero and negatives are ordinary
    measured values, not sentinels, and `0.0` in particular is the one
    most likely to be caught by a careless falsiness check."""
    for value in (78.4, 0, 0.0, -273.15, 10 ** 30):
        assert no_context_free_property(_typed_property(value=value)).admissible, value


def test_the_two_gates_agree_that_nothing_numeric_can_mean_missing():
    """`science.admissibility` and `science.table` are independent gates
    answering different questions, and this is the one rule they must
    not disagree about -- if either admitted a sentinel, the extension's
    guarantee would hold only on whichever path happened to run."""
    sentinel = float("nan")
    assert NON_FINITE_QUANTITY in quantity_is_typed(_typed_property(value=sentinel)).reasons
    assert table.SENTINEL_ENCODED_ABSENCE in observation_is_table_alignable(
        dict(ALIGNED_CELL, value=sentinel)
    ).reasons


# ================================== 3. identity: types, not mere presence


def test_a_fully_identified_cell_is_alignable():
    assert observation_is_table_alignable(ALIGNED_CELL).admissible


def test_an_explicitly_absent_cell_is_alignable():
    """Absence is not a defect in the table. A stated absence is a
    complete, alignable cell -- that is the entire point of making it
    structural rather than a value."""
    verdict = observation_is_table_alignable(ABSENT_CELL)
    assert verdict.admissible
    assert table.is_explicitly_absent(ABSENT_CELL)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"sample_id": None}, table.UNTYPED_SAMPLE_IDENTITY),
        ({"sample_id": 7}, table.UNTYPED_SAMPLE_IDENTITY),
        ({"sample_id": True}, table.UNTYPED_SAMPLE_IDENTITY),
        ({"sample_id": "   "}, table.UNTYPED_SAMPLE_IDENTITY),
        ({"variable": 3}, table.UNTYPED_VARIABLE_IDENTITY),
        ({"variable": ""}, table.UNTYPED_VARIABLE_IDENTITY),
    ],
)
def test_a_partially_typed_identity_is_refused_at_the_gate(overrides, expected):
    """THE §7/§8 ASYMMETRY, applied to this extension. A presence check
    would admit every one of these. The consumer failure they produce is
    silent and late: `7` and `"7"` are different join keys, so the table
    splits in two and the fit runs over half its rows with residuals
    that look entirely healthy.

    `True` is in this list deliberately -- `isinstance(True, int)` is
    True in Python, so a bool sneaks through any numeric-or-string check
    that does not exclude it explicitly."""
    verdict = observation_is_table_alignable(dict(ALIGNED_CELL, **overrides))
    assert not verdict.admissible and expected in verdict.reasons


@pytest.mark.parametrize("key", ["sample_id", "variable"])
def test_a_missing_identity_is_a_different_reason_from_an_untyped_one(key):
    """Two different facts about the source and they stay distinguishable:
    "this source does not identify its samples" is a modelling gap,
    "this source identifies them with integers" is an encoding one."""
    content = {k: v for k, v in ALIGNED_CELL.items() if k != key}
    expected = table.MISSING_SAMPLE_IDENTITY if key == "sample_id" else table.MISSING_VARIABLE_IDENTITY
    assert expected in observation_is_table_alignable(content).reasons


@pytest.mark.parametrize("positional", ["row_index", "position"])
def test_row_position_is_refused_by_name_rather_than_ignored(positional):
    """Quoted from the requirement: "Row position is NOT an acceptable
    identity here, because ordering is explicitly not required by this
    modality." Refused BY NAME so a source that supplies one learns why
    it does not count, instead of watching an otherwise well-formed
    record be rejected for a reason it cannot see."""
    verdict = observation_is_table_alignable(dict(ALIGNED_CELL, **{positional: 3}))
    assert not verdict.admissible
    assert table.POSITIONAL_IDENTITY_IS_NOT_IDENTITY in verdict.reasons


# ================================ 4. absence is structural, never a value


def test_a_cell_cannot_both_have_a_value_and_be_absent():
    """Not a merge conflict to resolve by precedence. It is a claim that
    the cell was simultaneously measured and not measured, and picking
    either side would invent an answer the source did not give."""
    verdict = observation_is_table_alignable(dict(ALIGNED_CELL, value_absence=table.NOT_MEASURED))
    assert table.VALUE_AND_ABSENCE_BOTH_PRESENT in verdict.reasons


def test_a_cell_with_neither_a_value_nor_a_stated_absence_is_refused():
    """Row-dropping seen from the other side. Quoted: "the residuals of
    a fit over a quietly smaller sample look entirely healthy". A
    consumer cannot distinguish a gap from a cell that was never part of
    the design, so the gap has to be stated."""
    content = {k: v for k, v in ALIGNED_CELL.items() if k != "value"}
    verdict = observation_is_table_alignable(content)
    assert table.MISSING_ABSENCE_REASON in verdict.reasons


@pytest.mark.parametrize("reason", table.ABSENCE_REASONS)
def test_every_absence_reason_in_the_vocabulary_is_accepted(reason):
    assert observation_is_table_alignable(dict(ABSENT_CELL, value_absence=reason)).admissible


@pytest.mark.parametrize("bad", ["", "missing", "n/a", 0, None, float("nan")])
def test_an_absence_reason_outside_the_vocabulary_is_refused(bad):
    """A closed vocabulary, like `uncertainty_kind` before it. An open
    free-text reason would let "n/a" and "missing" and "" accumulate as
    three names for one fact, which is how a vocabulary stops meaning
    anything."""
    verdict = observation_is_table_alignable(dict(ABSENT_CELL, value_absence=bad))
    assert table.UNKNOWN_ABSENCE_REASON in verdict.reasons


def test_the_absence_vocabulary_distinguishes_who_lost_the_value():
    """Each member states something different about the world, and the
    distinctions are the ones this repository has already committed to
    elsewhere: `withheld` is the source's choice,
    `lost_in_acquisition` is DAQ's own failure, `below_detection` is a
    real measurement outcome. Collapsing them would be the same mistake
    as collapsing `uncertainty_kind: absent` into a missing field."""
    assert len(set(table.ABSENCE_REASONS)) == len(table.ABSENCE_REASONS)
    assert {table.WITHHELD, table.LOST_IN_ACQUISITION} <= set(table.ABSENCE_REASONS)
    assert table.BELOW_DETECTION != table.NOT_MEASURED


def test_conditions_that_distinguish_samples_stay_recoverable():
    """The workload's THIRD DAQ-owned requirement, and it was nearly
    missed: the two BLOCKING requirements are the headline, but
    `least_squares.condition_requirements` names a third --
    "conditions_that_distinguish_samples_must_be_recoverable_as_
    predictors_or_strata".

    DAQ's part of it is narrow on purpose. Whether a condition becomes a
    predictor column or a stratum is a MODELLING assertion, and the same
    artifact says so ("the choice of design matrix / basis functions is
    a modelling assertion, not an observation"), so DAQ must not decide
    it. What DAQ owes is that the conditions are carried under stable
    identifiers a consumer can join on."""
    base = {"sample_id": "s1", "variable": "x", "value": 1.0}

    assert observation_is_table_alignable(base).admissible, "conditions are optional to THIS gate"
    assert observation_is_table_alignable(
        dict(base, conditions=FrozenMapping({"temperature_c": 23}))).admissible

    for bad in ("MLLW", 7, ["temperature_c"]):
        assert table.CONDITION_KEYS_ARE_NOT_IDENTIFIERS in observation_is_table_alignable(
            dict(base, conditions=bad)).reasons, bad
    assert table.CONDITION_KEYS_ARE_NOT_IDENTIFIERS in observation_is_table_alignable(
        dict(base, conditions={"": 1})).reasons


@pytest.mark.parametrize("shadow", ["sample_id", "variable", "value_absence"])
def test_a_condition_may_not_shadow_one_of_the_tables_own_columns(shadow):
    """The collision is silent, which is the only reason it is worth a
    reason code: lifted into a predictor, a condition named `variable`
    sits beside the identity column of the same name, and the consumer
    joins on one while reading the other. Refused rather than renamed --
    renaming a source's own vocabulary is not DAQ's to do."""
    content = {"sample_id": "s1", "variable": "x", "value": 1.0,
               "conditions": FrozenMapping({shadow: "anything"})}
    verdict = observation_is_table_alignable(content)
    assert not verdict.admissible
    assert table.CONDITION_KEY_SHADOWS_AN_IDENTITY in verdict.reasons


def test_the_gate_does_not_decide_predictor_versus_stratum():
    """The requirement says conditions must be RECOVERABLE as predictors
    or strata. It does not say which, and neither does this gate. A
    numeric condition and a categorical one are equally alignable here;
    choosing between them is the modelling assertion DAQ must not make."""
    numeric = {"sample_id": "s1", "variable": "x", "value": 1.0,
               "conditions": FrozenMapping({"temperature_c": 23})}
    categorical = {"sample_id": "s1", "variable": "x", "value": 1.0,
                   "conditions": FrozenMapping({"batch": "B7"})}
    assert observation_is_table_alignable(numeric).admissible
    assert observation_is_table_alignable(categorical).admissible

    # Checked against the module's DEFINED NAMES rather than its text --
    # the docstring quotes the requirement, which itself contains the word
    # "predictors", and a substring check on prose would fail on the quote
    # it is supposed to be preserving.
    import ast
    source = (Path(__file__).resolve().parent.parent / "science" / "table.py").read_text()
    defined = {
        node.name for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    } | {
        node.id for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    for modelling_word in ("predictor", "design_matrix", "stratum", "strata", "column"):
        offenders = [name for name in defined if modelling_word in name.lower()]
        assert not offenders, (
            f"science/table.py defines {offenders} -- the gate is deciding a modelling question")


def test_the_quoted_requirements_are_verbatim_from_the_exchange_artifact():
    """A paraphrase of a counterparty's requirement is DAQ's ACCOUNT of
    it, and the whole point of the exchange protocol is that it is not.
    Both the gate's docstring and the architecture record quote these;
    this checks the quotes against the artifact byte for byte, so a drift
    on either side is caught rather than discovered by a consumer."""
    from epistemics._yaml import loads

    root = Path(__file__).resolve().parent.parent
    artifact = loads((root / "architecture" / "exchange" / "scl_requirements.yaml").read_text())
    least_squares = artifact["workloads"]["least_squares"]

    stated = {row["requirement"]: row["statement"]
              for row in least_squares["blocking_requirements"] if row["owner"] == "daq"}
    assert set(stated) == {"stable_sample_and_variable_identity", "explicit_missing_value_semantics"}

    gate_docstring = (root / "science" / "table.py").read_text()
    record = (root / "architecture" / "aligned_observation_table.yaml").read_text()
    for requirement, statement in stated.items():
        # The gate docstring wraps its quote, so compare on collapsed
        # whitespace; the YAML record carries it on one line.
        assert " ".join(statement.split()) in " ".join(gate_docstring.split()), requirement
        assert statement in record, requirement

    # The third requirement, which is not in blocking_requirements and was
    # nearly missed for exactly that reason.
    assert least_squares["condition_requirements"] in record


def test_the_table_gate_does_not_subsume_the_property_gate():
    """They answer different questions and neither implies the other.
    Stated as a test because a future reader is likely to assume one
    replaces the other and drop a call."""
    alignable_but_untyped = {"sample_id": "s1", "variable": "v", "value": 1.0}
    assert observation_is_table_alignable(alignable_but_untyped).admissible
    assert not no_context_free_property(alignable_but_untyped).admissible

    typed_but_unalignable = _typed_property()
    assert no_context_free_property(typed_but_unalignable).admissible
    assert not observation_is_table_alignable(typed_but_unalignable).admissible


# ============================ 5. the pass-through routes, actually tightened
#
# A gate is enforceable only on the paths that reach it. These two
# extractors were the paths that did not.


def _extract_local(payload):
    record = make_record(document_id="d", locator="l", raw_content=json.dumps(payload))
    return LocalDatasetExtractor().extract(record)[0]


def _extract_graph(payload):
    body = dict(payload)
    body.setdefault("entities", [{"label": "formulation-f1", "kind": "formulation"}])
    record = make_record(document_id="d", locator="l", raw_content=json.dumps(body))
    return GraphDatasetExtractor().extract(record)[0]


@pytest.mark.parametrize("extract", [_extract_local, _extract_graph], ids=["local", "graph"])
def test_a_pass_through_route_no_longer_carries_a_sentinel(extract):
    """`json.dumps` EMITS bare `NaN` and `json.loads` ACCEPTS it, both by
    default, so a source file containing a sentinel travelled this route
    end to end without one error. Refused at extraction now -- loud and
    early, at the boundary that read it."""
    with pytest.raises(PassthroughRefusal, match="non-finite"):
        extract(dict(ALIGNED_CELL, value=float("nan")))


@pytest.mark.parametrize("extract", [_extract_local, _extract_graph], ids=["local", "graph"])
def test_the_refusal_reaches_a_sentinel_nested_anywhere(extract):
    """Not just the top level. The requirement is about the value a
    consumer reads, and a consumer reads nested structure too."""
    with pytest.raises(PassthroughRefusal, match=r"conditions\.strain_rate_per_s"):
        extract(dict(ALIGNED_CELL, conditions={"strain_rate_per_s": float("inf")}))

    with pytest.raises(PassthroughRefusal, match=r"series\[2\]"):
        extract(dict(ALIGNED_CELL, series=[1.0, 2.0, float("nan")]))


@pytest.mark.parametrize("extract", [_extract_local, _extract_graph], ids=["local", "graph"])
def test_the_refusal_names_the_record_and_the_path(extract):
    """An extractor refusal that does not say WHERE sends the operator
    to grep a dataset by hand."""
    with pytest.raises(PassthroughRefusal) as caught:
        extract(dict(ALIGNED_CELL, conditions={"temperature_c": float("nan")}))
    message = str(caught.value)
    assert "conditions.temperature_c" in message
    assert "value_absence" in message, "the refusal must name the honest alternative"


@pytest.mark.parametrize("extract", [_extract_local, _extract_graph], ids=["local", "graph"])
def test_a_dict_valued_entry_arrives_frozen_from_either_route(extract):
    """The Phase 35 write-side asymmetry, closed at the shared seam
    rather than per-source. Both routes, because fixing one and not the
    other is what produced the asymmetry in the first place."""
    candidate = extract(dict(ALIGNED_CELL, conditions={"temperature_c": 23}))
    assert isinstance(candidate.content["conditions"], FrozenMapping)
    assert hash(candidate.content["conditions"])


@pytest.mark.parametrize("extract", [_extract_local, _extract_graph], ids=["local", "graph"])
def test_nested_mappings_are_frozen_all_the_way_down(extract):
    candidate = extract(dict(ALIGNED_CELL, conditions={"ambient": {"temperature_c": 23}}))
    inner = candidate.content["conditions"]["ambient"]
    assert isinstance(inner, FrozenMapping)
    assert hash(candidate.content["conditions"])


@pytest.mark.parametrize("extract", [_extract_local, _extract_graph], ids=["local", "graph"])
def test_everything_else_still_passes_through_verbatim(extract):
    """The tightening must not turn a generic transport into a typed
    one. No key added, renamed, dropped or interpreted -- including keys
    this repository has never seen, which is the whole reason these two
    extractors exist."""
    payload = dict(
        ALIGNED_CELL,
        value_absence=table.WITHHELD,          # refused by the TABLE gate, not here
        some_unknown_key=["a", {"b": 1}, None],
        row_index=4,
        unicode_key="ångström",
    )
    content = dict(extract(payload).content)
    content.pop("id", None)
    assert set(content) == set(payload) - {"id"}
    assert content["some_unknown_key"][0] == "a"
    assert content["unicode_key"] == "ångström"


def test_the_tightened_content_still_hashes_identically_to_the_plain_form():
    """`FrozenMapping` is a `dict` subclass, so `json.dumps` serializes
    it identically. Stated as a test because if this ever stopped being
    true, every Observation.id in the store would move -- silently, and
    only for records that happened to carry a nested mapping."""
    plain = {"sample_id": "s1", "conditions": {"b": 2, "a": 1}}
    tightened = tighten_passthrough_content(plain, "r1")
    assert content_hash(tightened) == content_hash(plain)
    assert isinstance(tightened["conditions"], FrozenMapping)


def test_tightening_is_idempotent():
    once = tighten_passthrough_content({"conditions": {"a": {"b": 1}}}, "r1")
    twice = tighten_passthrough_content(once, "r1")
    assert once == twice and content_hash(once) == content_hash(twice)


def test_booleans_and_strings_are_not_mistaken_for_numbers():
    """`isinstance(True, int)` is True, and a careless finiteness check
    on a bool raises rather than passing it through."""
    content = tighten_passthrough_content({"flag": True, "text": "inf", "n": 0}, "r1")
    assert content == {"flag": True, "text": "inf", "n": 0}


# ================================== 6. the extension end to end, on a table


def test_an_aligned_table_survives_acquisition_and_a_reopen(tmp_path):
    """The deliverable, exercised as the workload will use it: several
    cells, one of them explicitly absent, joined by identity rather than
    by position -- and the join keys must be the same objects after a
    process boundary, since that is where a sample id silently changing
    type would show up."""
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    cells = [
        {"sample_id": "s1", "variable": "x", "value": 1.0},
        {"sample_id": "s1", "variable": "y", "value": 2.0},
        {"sample_id": "s2", "variable": "x", "value": 3.0},
        {"sample_id": "s2", "variable": "y", "value_absence": table.BELOW_DETECTION},
    ]
    for index, cell in enumerate(cells):
        assert observation_is_table_alignable(cell).admissible, cell
        store.put_observation(make_observation(
            record_ids=(f"r{index}",), extraction_method="test",
            content=tighten_passthrough_content(cell, f"r{index}"),
            confidence=1.0, extracted_at="2020-01-01T00:00:00Z",
        ))

    reopened = FilesystemEvidenceStore(tmp_path / "evidence")
    recovered = [observation.content for observation in reopened.all_observations()]
    assert len(recovered) == 4

    keys = {(content["sample_id"], content["variable"]) for content in recovered}
    assert keys == {("s1", "x"), ("s1", "y"), ("s2", "x"), ("s2", "y")}
    for content in recovered:
        assert isinstance(content["sample_id"], str) and isinstance(content["variable"], str)
        assert observation_is_table_alignable(content).admissible

    absent = [c for c in recovered if table.is_explicitly_absent(c)]
    assert len(absent) == 1, "the absent cell is still a cell, not a dropped row"
    assert absent[0]["value_absence"] == table.BELOW_DETECTION


def test_the_absent_cell_is_never_a_number_at_any_point_in_the_lifecycle(tmp_path):
    """The rule stated as a lifecycle property rather than a gate check:
    at no boundary -- in the extractor, in memory, on disk, after a
    reopen -- does the absent cell hold a value in the numeric range."""
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    observation = make_observation(
        record_ids=("r1",), extraction_method="test",
        content={"sample_id": "s1", "variable": "y", "value_absence": table.BELOW_DETECTION},
        confidence=1.0, extracted_at="2020-01-01T00:00:00Z",
    )
    store.put_observation(observation)

    on_disk = json.loads(
        next(p for p in (tmp_path / "evidence").rglob("*.json")
             if observation.id in p.read_text()).read_text()
    )
    serialized = json.dumps(on_disk)
    assert "NaN" not in serialized and "Infinity" not in serialized

    for content in (observation.content, store.get_observation(observation.id).content):
        assert "value" not in content
        assert content["value_absence"] == table.BELOW_DETECTION


# ============================== 7. the invariants this file claims to enforce
#
# `architecture/invariants.yaml` names THIS file as the enforcement for two
# invariants. Phase 36 measured that 18 entries in that ledger named an
# enforcement file that never mentions them, and locked the set so it cannot
# grow. These two are therefore traced explicitly rather than assumed.


def _invariant(invariant_id):
    from epistemics._yaml import loads
    doc = loads((Path(__file__).resolve().parent.parent / "architecture" / "invariants.yaml").read_text())
    return next(entry for entry in doc["invariants"] if entry["id"] == invariant_id)


def test_absence_is_never_an_in_range_value_is_enforced_as_the_ledger_claims():
    entry = _invariant("absence_is_never_an_in_range_value")
    assert entry["status"] == "enforced"
    assert Path(__file__).name in entry["enforcement"]

    # Each of the three named mechanisms, exercised.
    assert NON_FINITE_QUANTITY in quantity_is_typed(_typed_property(value=float("nan"))).reasons
    assert NON_FINITE_UNCERTAINTY in quantity_is_typed(_typed_property(uncertainty=float("inf"))).reasons
    assert table.SENTINEL_ENCODED_ABSENCE in observation_is_table_alignable(
        dict(ALIGNED_CELL, value=float("-inf"))).reasons
    with pytest.raises(PassthroughRefusal):
        tighten_passthrough_content({"deep": {"v": float("nan")}}, "r1")

    # The stated limitation is honest: the seam covers the two generic
    # transports, not every extractor author. Asserted so the claim in the
    # ledger cannot quietly widen into one this file does not support.
    assert "not every author" in entry["limitation"]


def test_table_identity_is_typed_not_positional_is_only_partially_enforced():
    """`partially_enforced` is the honest status and the test says why:
    the gate exists and refuses, but nothing compels a caller to consult
    it -- exactly like `quantity_is_typed` and `no_context_free_property`
    before it. Overstating this as `enforced` is the failure mode this
    assertion exists to prevent."""
    entry = _invariant("table_identity_is_typed_not_positional")
    assert entry["status"] == "partially_enforced"
    assert Path(__file__).name in entry["enforcement"]
    assert "not wired into any admission path" in entry["gap"]
    assert entry["named_consuming_workload"].startswith("least_squares")

    assert not observation_is_table_alignable(dict(ALIGNED_CELL, sample_id=7)).admissible
    assert not observation_is_table_alignable(dict(ALIGNED_CELL, row_index=0)).admissible


def test_the_extension_record_names_a_consuming_workload():
    """The pairing is what made this a decision rather than a wish, so
    the record has to carry the consumer, not just the capability."""
    from epistemics._yaml import loads
    record = loads(
        (Path(__file__).resolve().parent.parent / "architecture" / "aligned_observation_table.yaml").read_text()
    )
    assert record["status"] == "built"
    assert record["named_consuming_workload"]["id"] == "least_squares"
    assert record["named_consuming_workload"]["requirements_still_open"] == []

    # And it does NOT claim Kalman, which is the conflated-extension error
    # this project already made once and corrected.
    assert "Kalman is NOT" in record["named_consuming_workload"]["note"]
    assert "next DECISION" in record["deliberately_not_done"]["covariance_extension"]


# ============ 8. the writer repair: identity over non-JSON is the larger half
#
# Sentinel-encoded absence was the stated concern and the gate closes it.
# But a NaN reaching content stacked THREE distinct failures, and only one
# of them was about absence:
#
#   1. an identity minted over a document no conformant parser will read
#      back -- `Observation.id` computed over bytes containing a bare
#      `NaN` token, which is a Python extension and not JSON;
#   2. a persisted artifact outside the format it claims to be in;
#   3. a value that breaks REFLEXIVITY, so any dedup, cache or comparison
#      keyed on it misbehaves silently rather than raising.
#
# (2) and (3) are not absence problems at all. The repair for them is the
# one this repository already applies to its canonical YAML emitter:
# CANONICAL AT THE WRITER, refuse the ambiguous form. A reader taught to
# tolerate NaN would relocate the problem rather than remove it.


def test_the_store_refuses_to_write_a_non_finite_rather_than_persisting_it():
    """`json.dumps` defaults to `allow_nan=True`, which emits bare
    `NaN`/`Infinity`. Measured before this was set: the store wrote that
    literal and the file was not valid JSON. Now the write refuses."""
    import json
    with pytest.raises(ValueError, match="not JSON compliant"):
        json.dumps({"v": float("nan")}, allow_nan=False)

    source = (Path(__file__).resolve().parent.parent
              / "daf" / "storage" / "filesystem_store.py").read_text()
    assert "allow_nan=False" in source
    assert "json.dumps(payload, sort_keys=True, indent=2)" not in source, (
        "the store's writer dropped allow_nan=False -- it will silently emit invalid JSON again")


def test_every_daf_owned_json_writer_sets_allow_nan_false():
    """One writer fixed is one writer fixed. The rule is a boundary
    property, so it is checked at every DAF-owned `json.dumps`, and a new
    one added without it fails here rather than at whichever consumer
    first reads the file back."""
    import re
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in sorted((root / "daf").rglob("*.py")):
        for match in re.finditer(r"json\.dumps\([^()]*(?:\([^()]*\)[^()]*)*\)", path.read_text()):
            if "allow_nan=False" not in match.group(0):
                offenders.append(f"{path.relative_to(root)}: {match.group(0)[:60]}")
    assert offenders == [], (
        "these writers emit bare NaN/Infinity by default, producing files that claim to be "
        f"JSON and are not: {offenders}")


def test_content_hash_is_vendored_so_the_repair_is_bounded_and_says_so():
    """HONEST LIMIT. `evidence.identity.content_hash` lives in the
    vendored substrate, which is never modified, and it calls
    `json.dumps` with the permissive default. So DAQ cannot make ID
    MINTING itself refuse a non-finite -- an Observation constructed
    directly in memory with a NaN still gets an id over invalid JSON.

    What DAQ can and does do is ensure nothing non-finite reaches that
    point through any route it owns: both gates refuse it, both
    pass-through extractors refuse it, and every DAF-owned writer refuses
    it. The residue is stated rather than papered over."""
    import evidence.identity as identity
    assert "vendor/scout-retrieval-agent" in identity.__file__, (
        "content_hash is no longer vendored -- if it became DAF-owned, the writer repair should "
        "be applied there too and this test replaced")

    # The residue, demonstrated rather than asserted in prose.
    assert content_hash({"v": float("nan")}), "minting still succeeds; only the routes are closed"


def test_the_three_failures_are_distinct_and_only_one_is_about_absence():
    """Stated as a test because collapsing them is the easy mistake: the
    absence rule alone would not have caught (1) or (3)."""
    import json
    value = float("nan")

    # 1. identity over non-JSON
    serialized = json.dumps({"v": value}, sort_keys=True, separators=(",", ":"))
    assert serialized == '{"v":NaN}'
    with pytest.raises(ValueError):
        json.loads(serialized, parse_constant=_refuse)

    # 3. reflexivity broken -- nothing to do with whether the cell is absent
    assert value != value
    assert len({value, value}) == 2 or value is value, (
        "set membership uses identity before equality, which is exactly why this misbehaves "
        "silently rather than raising")


# ================================ 9. the bool class, and what a covariance gets
#
# `isinstance(True, int)` is True, so a bool passes every numeric check
# that does not exclude it by name. Measured: a bool was refused as a
# QUANTITY but admitted as an UNCERTAINTY and admitted as a TABLE CELL.


def test_a_bool_uncertainty_was_admissible_and_now_is_not():
    from science.admissibility import UNTYPED_UNCERTAINTY
    for value in (True, False):
        verdict = quantity_is_typed(_typed_property(uncertainty=value))
        assert not verdict.admissible
        assert UNTYPED_UNCERTAINTY in verdict.reasons
    assert quantity_is_typed(_typed_property(uncertainty=0.1)).admissible


def test_a_bool_table_cell_was_admissible_and_now_is_not():
    """The downstream harm is silent, which is what makes it worth a
    reason code rather than a coercion: `sum([True, True, False])` is 2,
    so a bool column quietly becomes a count nobody asserted."""
    verdict = observation_is_table_alignable(dict(ALIGNED_CELL, value=True))
    assert not verdict.admissible
    assert table.BOOLEAN_IS_NOT_A_QUANTITY in verdict.reasons
    assert sum([True, True, False]) == 2, "the silent reinterpretation this refuses"


def test_refusing_a_bool_is_the_modelling_boundary_not_only_a_type_check():
    """If the source means an indicator, encoding it as 0/1 is a design
    matrix decision -- and the requirements artifact says the choice of
    design matrix is a modelling assertion, not an observation. Letting
    `True` arrive where a number is read makes that choice silently."""
    from epistemics._yaml import loads
    root = Path(__file__).resolve().parent.parent
    artifact = loads((root / "architecture" / "exchange" / "scl_requirements.yaml").read_text())
    assert any("modelling assertion" in str(p)
               for p in artifact["workloads"]["least_squares"]["model_parameters"])

    # Genuine numeric zero and one are unaffected -- the refusal is about
    # the TYPE, not the magnitude.
    for value in (0, 1, 0.0, 1.0):
        assert observation_is_table_alignable(dict(ALIGNED_CELL, value=value)).admissible


def test_the_bool_surface_is_recorded_as_inherited_by_the_covariance_work():
    """A covariance is a matrix of cells and inherits this surface
    directly: a bool in a covariance passes a positive-semidefiniteness
    check while meaning nothing. Recorded against the covariance
    extension rather than left to be rediscovered there."""
    from epistemics._yaml import loads
    root = Path(__file__).resolve().parent.parent
    record = loads((root / "architecture" / "aligned_observation_table.yaml").read_text())
    inherited = record["deliberately_not_done"]["covariance_inherits_the_bool_surface"]
    assert "positive-semidefinite" in inherited or "PSD" in inherited
    assert "matrix of cells" in inherited.lower()


def test_emitted_json_is_json_is_enforced_as_the_ledger_claims():
    entry = _invariant("emitted_json_is_json")
    assert entry["status"] == "enforced"
    assert Path(__file__).name in entry["enforcement"]
    assert "fourth instance" in entry["it_is_the_fourth_instance_of_one_rule"].lower() or \
        "Clause 2" in entry["it_is_the_fourth_instance_of_one_rule"]
    assert "relocates the problem" in entry["the_rule"]
    assert "vendored" in entry["bounded_limitation"]


def test_a_bool_is_not_a_quantity_is_enforced_as_the_ledger_claims():
    from science.admissibility import UNTYPED_UNCERTAINTY
    entry = _invariant("a_bool_is_not_a_quantity")
    assert entry["status"] == "enforced"
    assert Path(__file__).name in entry["enforcement"]
    assert "positive-semidefinite" in entry["inherited_by"]

    # All three positions the ledger claims, exercised.
    assert not quantity_is_typed(_typed_property(value=True)).admissible
    assert UNTYPED_UNCERTAINTY in quantity_is_typed(_typed_property(uncertainty=True)).reasons
    assert table.BOOLEAN_IS_NOT_A_QUANTITY in observation_is_table_alignable(
        dict(ALIGNED_CELL, value=True)).reasons
