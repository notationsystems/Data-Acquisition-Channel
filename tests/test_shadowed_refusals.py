"""The 25 pre-empted codes, each driven directly.

C.2's rule: expose the function or drive the predicate; do not add a
bypass to the product so a harness can reach a regime. Nothing here
touches the product.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.storage.frozen_mapping import FrozenMapping  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from science.admissibility import (no_context_free_property,  # noqa: E402
                                   quantity_is_typed)
from science.structured_uncertainty import uncertainty_corresponds_to_value  # noqa: E402
from science.table import leaf_is_a_quantity, observation_is_table_alignable  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "shadowed_refusals.yaml").read_text())

BASE = {"sample_id": "S1", "property": "mn", "value": 1.0, "unit": "g/mol",
        "uncertainty": 0.1, "uncertainty_kind": "stated", "method": "m",
        "conditions": FrozenMapping({"solvent": "THF"})}


def content(**overrides):
    merged = dict(BASE)
    merged.update(overrides)
    return merged


def without(*keys, **overrides):
    merged = dict(BASE)
    for key in keys:
        merged.pop(key, None)
    merged.update(overrides)
    return merged


TABLE, QTY, CTX, UNC = (observation_is_table_alignable, quantity_is_typed,
                        no_context_free_property, uncertainty_corresponds_to_value)

#: The 25 codes WO-4 measured as pre-empted, each with content that
#: exhibits its violation. Written against each predicate, not each name.
SHADOWED = [
    ("MISSING_SAMPLE_IDENTITY", TABLE, without("sample_id")),
    ("UNTYPED_SAMPLE_IDENTITY", TABLE, content(sample_id=5)),
    ("MISSING_VARIABLE_IDENTITY", TABLE, without("property")),
    ("UNTYPED_VARIABLE_IDENTITY", TABLE, content(property=3)),
    ("MISSING_ABSENCE_REASON", TABLE, content(value=None)),
    ("SENTINEL_ENCODED_ABSENCE", TABLE, content(value=float("nan"))),
    ("BOOLEAN_IS_NOT_A_QUANTITY", TABLE, content(value=True)),
    ("NUMERIC_LOOKING_STRING_CELL", TABLE, content(value="1.5")),
    # A BOOL leaf, not a string one: a categorical string leaf is admitted
    # on purpose, and planting one measures that decision instead.
    ("COMPOSITE_CELL_LEAF_IS_NOT_A_QUANTITY", TABLE, content(value=[1.0, True])),
    # Bytes, not a dict: a Mapping routes to the composite branch and
    # never reaches the type branch where this code lives.
    ("CELL_TYPE_IS_NOT_A_QUANTITY", TABLE, content(value=b"x")),
    ("MISSING_METHOD", CTX, without("method")),
    ("MISSING_CONDITIONS", CTX, content(conditions=FrozenMapping({}))),
    ("UNTYPED_QUANTITY", QTY, content(value="abc")),
    ("MISSING_UNIT", QTY, without("unit")),
    ("MISSING_UNCERTAINTY_KIND", QTY, without("uncertainty_kind")),
    ("NON_FINITE_QUANTITY", QTY, content(value=float("inf"))),
    ("NON_FINITE_UNCERTAINTY", QTY, content(uncertainty=float("inf"))),
    ("UNTYPED_UNCERTAINTY", QTY, content(uncertainty=True)),
    ("UNCERTAINTY_SHAPE_DOES_NOT_MATCH_VALUE", UNC,
     content(value=[1.0, 2.0], uncertainty=[[1.0, 0.0]], unit=["g", "g"])),
    ("SCALAR_UNCERTAINTY_ON_A_MULTIVARIATE_VALUE", UNC,
     content(value=[1.0, 2.0], uncertainty=0.1, unit=["g", "g"])),
    ("STRUCTURED_UNCERTAINTY_ON_A_SCALAR_VALUE", UNC,
     content(value=1.0, uncertainty=[[1.0, 0.0], [0.0, 1.0]])),
    ("UNCERTAINTY_LEAF_IS_NOT_A_MAGNITUDE", UNC,
     content(value=[1.0, 2.0], uncertainty=[[True, 0.0], [0.0, 1.0]], unit=["g", "g"])),
    ("UNITS_DO_NOT_MATCH_COMPONENTS", UNC,
     content(value=[1.0, 2.0], uncertainty=[[1.0, 0.0], [0.0, 1.0]], unit="g/mol")),
    ("UNTYPED_COMPONENT_UNIT", UNC,
     content(value=[1.0, 2.0], uncertainty=[[1.0, 0.0], [0.0, 1.0]], unit=[1, 2])),
    ("VALUE_LEAF_IS_NOT_A_QUANTITY", UNC,
     content(value=[1.0, True], uncertainty=[[1.0, 0.0], [0.0, 1.0]], unit=["g", "g"])),
]


@pytest.mark.parametrize("code,gate,body", SHADOWED, ids=[c for c, _, _ in SHADOWED])
def test_a_shadowed_code_fires_when_its_predicate_is_driven(code, gate, body):
    """FIRES_IF_REACHED. Named, never counted: the question is which code
    fired, not that one did."""
    assert code in gate(body).reasons, f"planted for {code}, got {list(gate(body).reasons)}"


def test_all_twenty_five_are_alive_and_none_is_retired():
    assert len(SHADOWED) == RECORD["result"]["codes_examined"] == 25
    assert RECORD["result"]["never_fires"] == 0
    assert len({code for code, _, _ in SHADOWED}) == 25, "a code is listed twice"


def test_a_categorical_string_leaf_is_admitted_on_purpose():
    """The decision three bad plants were measuring. Asserted so that if
    it is ever reversed, the plants above become wrong again and say so."""
    assert leaf_is_a_quantity("a") == ""
    assert leaf_is_a_quantity("1.5") == "NUMERIC_LOOKING_STRING_CELL"
    assert leaf_is_a_quantity(True) == "BOOLEAN_IS_NOT_A_QUANTITY"
    assert leaf_is_a_quantity(b"x") == "CELL_TYPE_IS_NOT_A_QUANTITY"

    # The plants that measured the decision instead of the code.
    assert observation_is_table_alignable(content(value=[1.0, "a"])).admissible
    assert not observation_is_table_alignable(content(value=[1.0, True])).admissible


def test_a_mapping_cell_never_reaches_the_type_branch():
    """The fourth bad plant. A dict routes to the composite branch, so
    CELL_TYPE_IS_NOT_A_QUANTITY was unreachable by that content whatever
    the code is called."""
    mapping_reasons = set(observation_is_table_alignable(content(value={"a": 1})).reasons)
    assert "CELL_TYPE_IS_NOT_A_QUANTITY" not in mapping_reasons
    assert "CELL_TYPE_IS_NOT_A_QUANTITY" in observation_is_table_alignable(
        content(value=b"x")).reasons


def test_the_record_states_the_bad_plants_rather_than_only_the_result():
    correction = RECORD["four_plants_were_wrong_before_any_code_was"]
    assert "designed from the code's NAME rather than from its PREDICATE" in correction["what_happened"]
    assert "measure why first" in correction["what_would_have_hidden_it"]
    assert "complementary" in RECORD["the_limit_of_this_measurement"]
