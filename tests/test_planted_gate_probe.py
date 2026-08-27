"""A DELIBERATE FAILURE, planted to prove the conformance gate can go red
for the right reason.

The gate was red on sixty-one consecutive runs for a missing checker,
dying during collection so that Tests and Types never executed. It is
green now. Green is not evidence that it can be red at the TEST rather
than at collection, and name the test when it does.

THIS FILE IS EXPECTED TO BE REMOVED in the commit immediately after the
run that observes it. If it is still here, the probe was never completed.
"""

from __future__ import annotations


def test_a_planted_failure_the_gate_must_name():
    assert 1 == 2, (
        "PLANTED. If the conformance gate reports red and names this test, the gate carries "
        "information. If it reports red at collection, or reports green, it does not."
    )
