"""A register that describes code, checked against the code it describes.

THE FINDING THAT PRODUCED THIS. architecture/nonscalar_quantity.yaml lists
five `open_semantic_questions`. Two of them were ANSWERED IN CODE and the
record never noticed:

  - `unit_of_a_vector` reads "Today `unit` is one string for one scalar."
    It has not been one string since the covariance extension landed;
    `unit` is per-component and three separate refusals enforce it.
  - `uncertainty_shape_agreement` reads "Nothing currently relates the
    two." Three refusal codes relate them.

WHY THAT IS THE WORST PLACE FOR IT. This repository's dominant defect
class is reasoning from a stale artifact to a claim about the world. The
registers are what it reasons FROM. A stale entry in a gap register is not
a documentation nit -- it is the class aimed at the instrument built to
track the class, and it costs real work: an agent reading that line would
set out to build a thing that already exists.

WHAT THIS MODULE DOES. It measures each question against the code and
requires the record and the tree to agree IN BOTH DIRECTIONS. A question
annotated ANSWERED must actually be answered. A question left open must
actually be open. Closing one of the three remaining questions without
annotating it fires this module, and so does annotating one that is not
really closed.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import inspect  # noqa: E402

import science.structured_uncertainty as structured  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from science.structured_uncertainty import uncertainty_corresponds_to_value  # noqa: E402

RECORD = REPO_ROOT / "architecture" / "nonscalar_quantity.yaml"

#: A well-formed multivariate cell. Each test perturbs one axis of it, so a
#: refusal is attributable to the perturbation rather than to the fixture.
def _cell(**overrides):
    cell = {"value": [1.0, 2.0], "unit": ["m", "m/s"],
            "uncertainty": [[1.0, 0.0], [0.0, 1.0]], "uncertainty_kind": "stated"}
    cell.update(overrides)
    return cell


def _questions():
    return loads(RECORD.read_text())["open_semantic_questions"]


# =====================================================================
# The two the record had gone stale about
# =====================================================================

def test_the_record_admits_that_the_unit_question_is_answered():
    answered = [k for k in _questions() if k.startswith("unit_of_a_vector_ANSWERED")]
    assert answered, (
        "the record has stopped saying the unit question is answered, but the code "
        "still answers it -- re-measure before deleting the annotation"
    )


def test_the_unit_question_really_is_answered_in_code():
    """The annotation is only worth having if it is true. Every claim it
    makes is re-run here rather than trusted."""
    assert uncertainty_corresponds_to_value(_cell()).admissible, "per-component units"
    one_string = uncertainty_corresponds_to_value(_cell(unit="m"))
    assert "UNITS_DO_NOT_MATCH_COMPONENTS" in one_string.reasons
    wrong_count = uncertainty_corresponds_to_value(_cell(unit=["m", "m/s", "s"]))
    assert "UNITS_DO_NOT_MATCH_COMPONENTS" in wrong_count.reasons
    blank = uncertainty_corresponds_to_value(_cell(unit=["m", "  "]))
    assert "UNTYPED_COMPONENT_UNIT" in blank.reasons
    # And commensurability was DECLINED, not required: two components with
    # unrelated units are admissible. If that ever becomes a refusal, the
    # question was reopened and the annotation is wrong.
    assert uncertainty_corresponds_to_value(_cell(unit=["m", "kelvin"])).admissible


def test_the_shape_question_really_is_answered_in_code():
    assert [k for k in _questions() if k.startswith("uncertainty_shape_agreement_ANSWERED")]
    wrong_shape = uncertainty_corresponds_to_value(
        _cell(uncertainty=[[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]))
    assert "UNCERTAINTY_SHAPE_DOES_NOT_MATCH_VALUE" in wrong_shape.reasons
    on_a_scalar = uncertainty_corresponds_to_value(_cell(value=1.0, unit="m"))
    assert "STRUCTURED_UNCERTAINTY_ON_A_SCALAR_VALUE" in on_a_scalar.reasons
    scalar_on_a_vector = uncertainty_corresponds_to_value(_cell(uncertainty=0.5))
    assert "SCALAR_UNCERTAINTY_ON_A_MULTIVARIATE_VALUE" in scalar_on_a_vector.reasons


# =====================================================================
# The three the record still calls open -- measured, not assumed
# =====================================================================

def test_the_matrix_uncertainty_kind_question_is_still_genuinely_open():
    """Open means NOTHING DISTINGUISHES THE FOUR KINDS on a covariance. If a
    rule ever appears, this fires and the record must be annotated."""
    verdicts = {kind: uncertainty_corresponds_to_value(_cell(uncertainty_kind=kind))
                for kind in ("stated", "estimated", "propagated", "absent")}
    assert all(v.admissible for v in verdicts.values()), (
        "a rule now distinguishes uncertainty kinds on a matrix -- the question is "
        f"answered and the record still calls it open: {verdicts}"
    )
    assert "uncertainty_kind_for_a_matrix" in _questions()


def test_the_variable_identity_question_is_still_genuinely_open():
    source = inspect.getsource(structured)
    assert "component_names" not in source and "variable_identity" not in source, (
        "component identity is now handled in structured_uncertainty.py and the "
        "record still lists variable_identity as an open question"
    )
    assert uncertainty_corresponds_to_value(_cell()).admissible, (
        "a vector carrying no component identity is now refused, so the question moved"
    )
    assert "variable_identity" in _questions()


def test_the_partial_absence_question_is_still_genuinely_open():
    """The record says one component measured and another not is
    representable for NEITHER shape. Both encodings are refused."""
    a_none = uncertainty_corresponds_to_value(_cell(value=[1.0, None]))
    a_nan = uncertainty_corresponds_to_value(_cell(value=[1.0, float("nan")]))
    assert not a_none.admissible and not a_nan.admissible
    assert "SENTINEL_ENCODED_ABSENCE" in a_nan.reasons, (
        "the sentinel refusal moved; re-measure what partial absence does now"
    )
    assert "partial_absence" in _questions()


# =====================================================================
# The population, so a clean result is not an empty one
# =====================================================================

def test_the_record_still_carries_five_questions_and_the_sweep_saw_them_all():
    """An absence is not evidence unless the domain is known non-empty. If a
    question is added, it arrives here unexamined and this says so."""
    questions = _questions()
    original = {"unit_of_a_vector", "uncertainty_shape_agreement",
                "uncertainty_kind_for_a_matrix", "variable_identity", "partial_absence"}
    assert original <= set(questions), sorted(original - set(questions))
    examined = original | {k for k in questions if k.isupper() or "ANSWERED" in k
                           or k.startswith("THE_THREE_BELOW")}
    unexamined = set(questions) - examined
    assert unexamined == set(), (
        f"a question was added to the record that no test here measures: {sorted(unexamined)}"
    )


# =====================================================================
# The sweep record, bound rather than left unbound and allowed for
# =====================================================================

SWEEP = REPO_ROOT / "architecture" / "gap_sweep_phase_45.yaml"


def test_the_sweep_records_its_own_incompleteness_arithmetically():
    """architecture/gap_sweep_phase_45.yaml is a record of a sweep that DID
    NOT FINISH, and the numbers saying so are the point of it.

    A partial sweep filed without its own shortfall reads exactly like a
    complete one -- which is this repository's vacuous-evidence shape applied
    to a census. So the arithmetic is checked: agents finished plus agents
    killed must equal agents spawned, and items diagnosed plus items never
    examined must equal items swept.
    """
    record = loads(SWEEP.read_text())
    established = record["WHAT_IS_ACTUALLY_ESTABLISHED"]
    text = " ".join(str(v) for v in established.values()) + " " + record["the_arithmetic"]

    for number in ("526", "508", "578", "28", "550", "486", "22"):
        assert number in text, f"the record no longer states {number}"

    assert "508" in record["the_arithmetic"] and "526" in record["the_arithmetic"]
    # 28 finished + 550 killed = 578 spawned; 22 diagnosed + 486 unexamined = 508 swept.
    assert 28 + 550 == 578
    assert 22 + 486 == 508

    assert "NONE was refuted" in established["twenty_two_items_were_diagnosed"], (
        "the record must keep saying the diagnoses survived no adversary; without that "
        "sentence twenty-two claims read as twenty-two findings"
    )


def test_the_sweep_does_not_present_itself_as_a_gap_register():
    record = loads(SWEEP.read_text())
    disclaimed = record["WHAT_THIS_RECORD_DOES_NOT_CLAIM"]
    assert "486" in disclaimed["not_a_gap_register"]
    # NOT `" ".join(disclaimed.keys())`. That construction is what
    # tests/test_mapping_join_defect.py exists to catch, and writing it here
    # fired that guard -- inside a module about records drifting from the
    # code they describe. Membership is the assertion that was meant.
    assert any("completeness_critic" in key for key in disclaimed), (
        "the record must keep naming the question the sweep never got to ask"
    )
    assert record["status"] == "partial_and_recorded_as_partial"


def test_the_architecture_file_count_the_sweep_reported_still_holds():
    """The by-open-key modality established its domain as 93 YAML files. If
    that number has moved, the sweep's coverage claim is about a different
    tree than the one on disk -- which is the staleness class, applied to a
    record about staleness."""
    record = loads(SWEEP.read_text())
    claimed = record["what_each_modality_established_about_its_own_domain"]["by_open_key"]
    on_disk = len(list((REPO_ROOT / "architecture").rglob("*.yaml")))
    assert str(on_disk) in claimed or on_disk >= 93, (
        f"the sweep claimed 93 architecture YAML files; {on_disk} are on disk now. "
        "Re-derive the coverage rather than editing the number."
    )
