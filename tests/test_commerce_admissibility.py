"""No fixture-derived result returns admissible — asserted, and planted."""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.admissibility import (FIXTURE_STAMPS, INADMISSIBLE_EVERY_INPUT_IS_FIXTURE,  # noqa: E402
                                    INADMISSIBLE_MIXED_INPUTS, INADMISSIBLE_NO_INPUTS,
                                    derived_from)
from commerce.events import RATE_QUOTED, LoadEvent, Source  # noqa: E402
from commerce.fixtures import freight  # noqa: E402


def _real(load="L-R1"):
    return LoadEvent(load, RATE_QUOTED, 100.0, "CAD",
                     Source("carrier_invoice", "asserted", "document", "2026-08-25",
                            recorded_by="op-1", artifact="inv-1", rung="manual"))


def test_a_result_from_the_small_fixture_is_inadmissible():
    result = derived_from(freight.events())
    assert not result.admissible
    assert INADMISSIBLE_EVERY_INPUT_IS_FIXTURE in result.because
    assert "claims nothing about any carrier" in result.because


def test_a_result_from_the_scale_fixture_is_inadmissible():
    """The generator stamps `representative_fixture`; both conventions in
    this tree are recognised."""
    import tools.make_fixture as make
    events, _ = make.generate()
    result = derived_from(events[:50])
    assert not result.admissible
    assert result.fixture_inputs == 50


def test_one_fabricated_row_poisons_a_real_result():
    """Weakest input wins. The fabricated row is inside the mean and
    cannot be subtracted back out; admissibility is not a proportion."""
    events = [_real(f"L-R{i}") for i in range(399)] + [freight.events()[0]]
    result = derived_from(events)
    assert not result.admissible
    assert INADMISSIBLE_MIXED_INPUTS in result.because
    assert result.real_inputs == 399 and result.fixture_inputs == 1
    assert "book in transition" in result.because


def test_a_result_from_only_real_events_is_admissible():
    """Vacuity guard: if nothing could ever be admissible the three tests
    above would prove nothing. This is the flip that happens per record
    the day a real load lands, with no code change."""
    result = derived_from([_real(f"L-R{i}") for i in range(10)])
    assert result.admissible
    assert result.real_inputs == 10
    assert "none fabricated" in result.sentence


def test_an_empty_derivation_is_not_admissible_by_vacuity():
    result = derived_from([])
    assert not result.admissible
    assert INADMISSIBLE_NO_INPUTS in result.because


def test_the_three_inadmissible_states_are_distinguishable():
    sentences = {
        derived_from(freight.events()[:5]).because,
        derived_from([_real(), freight.events()[0]]).because,
        derived_from([]).because,
    }
    assert len(sentences) == 3


def test_every_stamp_convention_in_the_tree_is_recognised():
    for stamp in ("fabricated_fixture", "representative_fixture", "fabricated_example"):
        assert stamp in FIXTURE_STAMPS
