"""The pre-registration is pinned, and the pin's limit is stated.

A prediction is only a prediction if it cannot be edited once the result
is known. This file pins the artifact's digest so that any later change
shows up as a TWO-file diff -- the artifact and this pin -- rather than a
one-file one.

WHAT THE PIN DOES NOT DO. It does not make editing impossible: an author
who changes the artifact can change the constant below in the same
commit, and the suite stays green. The real guarantee is the COMMIT
ORDER in git history -- this artifact lands before any second-source
adapter, extractor or fixture exists -- and the pin's job is to make a
retrospective edit require a deliberate, visible second act rather than a
quiet one. Stated here rather than left to be assumed, because a pin
described as tamper-proof would be exactly the proxy-for-its-target shape
this repository files.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "gpc_second_source_preregistration.yaml"
PREREG = loads(ARTIFACT.read_text())

#: Digest at the commit that recorded the predictions, BEFORE any
#: second-source code existed.
PINNED = "e22b42474b446a166baf7d2a8093f4793004a383c0fe9651db9a26680d0df72c"


def test_the_preregistration_has_not_been_edited_since_it_was_recorded():
    live = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    assert live == PINNED, (
        "the pre-registration has changed. If a prediction turned out wrong, the RESULT says so "
        "-- this file is not corrected to match. Changing it and this pin together is a "
        "deliberate act and should be argued for in the commit that does it."
    )


def test_every_prediction_states_whether_it_rests_on_measured_behaviour():
    """A prediction that quietly restates something already measured
    inflates the pre-registration's hit rate. Each must say which it is."""
    predictions = PREREG["predictions"]
    assert len(predictions) >= 3, "the work order requires at least three divergence properties"
    for name, body in predictions.items():
        assert "prediction" in body, f"{name} states no prediction"
        basis = body.get("basis", "")
        assert any(word in basis for word in ("OPEN", "MEASURED")), (
            f"{name} does not say whether its prediction rests on measured behaviour"
        )
    open_ones = [n for n, b in predictions.items() if b["basis"].startswith("OPEN")]
    assert open_ones, (
        "every prediction rests on behaviour already measured, which makes this a description "
        "rather than a pre-registration"
    )


def test_the_author_named_the_prediction_expected_to_be_wrong():
    """Recorded so that being wrong about it is visible rather than
    absorbed into a narrative afterwards."""
    assert "one_record_per_run" in PREREG["the_prediction_i_expect_to_be_wrong"]
    assert "conditions" in PREREG["the_clause_predicted_most_likely_to_fail"]


def test_the_permitted_outcome_is_failure():
    """Without this stated, the pressure is to widen a clause until the
    second source passes -- and every clause was derived from a
    measurement a widening would silently discard."""
    header = ARTIFACT.read_text()
    assert "THE PERMITTED OUTCOME IS FAILURE" in header
    assert "fixture contract" in header
    # Asserted on the VALUE, not the key. The first draft checked for the
    # word "success" and found it in the key name -- a check reading its
    # own index rather than its content.
    permitted = PREREG["what_would_make_this_phase_a_success_even_if_everything_fails"]
    assert "cannot be satisfied" in permitted
    assert "cheaper to learn now" in permitted


def test_the_guard_that_asserted_no_second_source_code_existed_is_retired():
    """RETIRED 2026-08-27, in the commit that built the second source --
    which is what it instructed.

    It asserted that no second-source module existed, so that the
    pre-registration's commit could be shown to precede the build rather
    than merely claim to. It fired the moment the build landed. Retiring
    it here rather than deleting it silently, and rather than leaving it
    passing over a condition that had stopped being checked.

    What it was protecting is the DIGEST, and that is unchanged: the pin
    above still matches, so the predictions were not edited once the
    results were known. This test now asserts the thing the retirement
    must not cost -- that the modules it was watching for do now exist, so
    a future reader can see the guard was retired because its condition
    genuinely changed and not because it was inconvenient."""
    built = [p.name for p in (
        REPO_ROOT / "daf" / "adapters" / "gpc_summary_export.py",
        REPO_ROOT / "daf" / "extractors" / "gpc_summary_export.py",
    ) if p.exists()]
    assert "gpc_summary_export.py" in built, (
        "the second source is gone, so this retirement no longer has a reason -- restore the "
        "original guard rather than leaving a retired one standing"
    )
    assert not (REPO_ROOT / "daf" / "extractors" / "gpc_summary_export.py").exists(), (
        "a second EXTRACTOR now exists; the contract test was that the shared one sufficed"
    )
