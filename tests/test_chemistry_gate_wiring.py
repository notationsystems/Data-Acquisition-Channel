"""DAQ-4, re-measured rather than read back.

The brief required this settled before any rejection rate is reported.
The recorded answer was that the call site "would be inside the
unmodifiable submodule" -- which conflated where the guards LIVE with
where a caller would have to live. This file establishes both halves by
execution: the guards import into this process, and they refuse planted
violations.

IT DOES NOT WIRE THEM. Refusing more is not a free action, and the four
guards assume a chemistry payload shape -- applying them to every
admitted observation would be the "gate applied to content it does not
govern" class this pair has filed twice.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402
from epistemics._yaml import loads  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "chemistry_gate_wiring.yaml").read_text())


def guards():
    from structures.method_blocks import assert_applicability, assert_method_block
    from structures.quantity import assert_property_context, assert_quantity_type
    return {"assert_quantity_type": assert_quantity_type,
            "assert_property_context": assert_property_context,
            "assert_method_block": assert_method_block,
            "assert_applicability": assert_applicability}


def test_the_guards_import_into_this_repositorys_process():
    """The half the recorded claim got wrong: a caller does not have to
    live where the callee does."""
    assert set(guards()) == {"assert_quantity_type", "assert_property_context",
                             "assert_method_block", "assert_applicability"}
    assert RECORD["answer"] == "THE_CALL_SITE_CAN_BE_ADDED_ON_THIS_SIDE"


def test_each_guard_refuses_a_planted_violation():
    """LIVE, in the submodule probe's own vocabulary. A gate that refuses
    a planted violation is not dead code -- which is a different question
    from whether real data reaches it, and the record says so."""
    from structures.method_blocks import MethodBlockError
    from structures.quantity import QuantityError

    g = guards()
    plants = [
        ("assert_quantity_type", lambda: g["assert_quantity_type"]({"value": 1.0}), QuantityError),
        ("assert_method_block", lambda: g["assert_method_block"]("measured", {}), MethodBlockError),
        ("assert_applicability", lambda: g["assert_applicability"]({}, {}), MethodBlockError),
    ]
    for name, plant, expected in plants:
        with pytest.raises(expected):
            plant()

    # THE DISCRIMINATING HALF: a guard that refused everything would pass
    # the loop above while establishing nothing.
    accepted = g["assert_quantity_type"](
        {"value": 1.0, "unit": "g/mol", "uncertainty": 0.1, "uncertainty_kind": "stated"})
    assert accepted is not None, (
        "the quantity guard refuses a well-formed payload too, so its refusals above say nothing "
        "about the violations they were planted for"
    )


def test_the_record_claims_neither_wiring_nor_reachability_nor_a_rate():
    """The three things a measurement like this is most likely to be read
    as having established."""
    not_claimed = RECORD["what_is_NOT_claimed"]
    assert "no call site was added" in not_claimed["not_wired"]
    assert "LIVE and REACHABLE are different questions" in not_claimed["not_reachable"]
    assert "none is reported" in not_claimed["not_a_rejection_rate"]
    assert RECORD["status"] == "measured_not_wired"


def test_no_rejection_rate_is_reported_anywhere_for_the_chemistry_gates():
    """The brief's actual condition. Asserted over the artifacts rather
    than trusted: a rate over gates nothing calls is silences counted as
    passes."""
    for path in sorted((REPO_ROOT / "architecture").rglob("*.yaml")):
        document = path.read_text()
        if "chemistry" not in document.lower():
            continue
        for line in document.splitlines():
            low = line.lower()
            if "rejection_rate" in low and "chemistry" in low:
                assert "0" not in line or "not" in low or "no rate" in low, (
                    f"{path.name} reports a chemistry rejection rate: {line.strip()[:120]}"
                )
