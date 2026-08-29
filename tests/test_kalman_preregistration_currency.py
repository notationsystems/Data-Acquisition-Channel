"""The shared pre-registration's arithmetic, re-derived. Nothing edited."""

from __future__ import annotations

import hashlib
import math
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

#: This file NAMES the shared pre-registration in order to re-derive two
#: arithmetic identities. That is a currency check, not a binding: it
#: asserts nothing about the artifact's claims, thresholds or criteria.
#: Declared so the doctrine-coverage detector does not count naming as
#: binding -- see architecture/doctrine_coverage.yaml, whose own limit
#: this is.
DOES_NOT_BIND = ("kalman_validation_preregistration.yaml",)

SHARED = REPO_ROOT / "architecture" / "kalman_validation_preregistration.yaml"
PREREG = loads(SHARED.read_text())
RECORD = loads((REPO_ROOT / "architecture" / "kalman_preregistration_currency.yaml").read_text())
NUMBERS = PREREG["machine_readable"]


def test_the_shared_artifact_was_not_edited():
    """The whole point of Phase D. A correction here is a joint reissue."""
    scl = pathlib.Path("/home/user/scientific-compute-layer-scl-/architecture"
                       "/kalman_validation_preregistration.yaml")
    if not scl.exists():
        import pytest
        pytest.skip("counterparty not present; divergence cannot be measured here")
    assert hashlib.sha256(SHARED.read_bytes()).digest() == hashlib.sha256(scl.read_bytes()).digest(), (
        "the pre-registration has diverged across the pair; DAQ must not have edited it"
    )


def test_the_nis_bounds_reproduce_exactly_so_the_domain_is_not_empty():
    """Asserted BEFORE the discrepancy below. A currency check where
    nothing reproduces is measuring the recomputation."""
    k = NUMBERS["sigma_multiplier"]
    n = NUMBERS["sample_count_N"]
    m = NUMBERS["measurement_dimension_m"]
    half_width = k * math.sqrt(2.0 * m / n)
    assert NUMBERS["derived_nis_lower"] == m - half_width
    assert NUMBERS["derived_nis_upper"] == m + half_width


def test_one_derived_tolerance_is_one_ulp_from_its_own_formula():
    """The finding, stated at the size it is. Not material to any
    statistic, and reported because a derived number that does not
    reproduce from the inputs beside it is what a currency check is for."""
    stated = NUMBERS["derived_mean_and_whiteness_tolerance"]
    recomputed = NUMBERS["sigma_multiplier"] / math.sqrt(NUMBERS["sample_count_N"])
    assert stated != recomputed, (
        "the tolerance now reproduces exactly; this record is stale and should be retired "
        "rather than left describing a discrepancy that is gone"
    )
    assert abs(recomputed - stated) == math.ulp(stated), "the gap must be exactly one ulp"
    assert abs(recomputed - stated) < 1e-15, "and immaterial, which the record says plainly"


def test_no_landed_measurement_was_judged_against_these_thresholds():
    """The Phase D STOP condition, measured rather than assumed."""
    tokens = [repr(NUMBERS["derived_mean_and_whiteness_tolerance"]),
              repr(NUMBERS["derived_nis_lower"]), repr(NUMBERS["derived_nis_upper"])]
    citing = []
    for path in sorted(REPO_ROOT.rglob("*.yaml")) + sorted(REPO_ROOT.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts[0] in ("vendor", ".git") or path == SHARED:
            continue
        if path.name in ("kalman_preregistration_currency.yaml",
                         "test_kalman_preregistration_currency.py"):
            continue
        text = path.read_text(errors="ignore")
        if any(token.strip("'") in text for token in tokens):
            citing.append(str(relative))
    assert citing == [], (
        f"{citing} cites a pre-registration threshold, so a stale claim there WOULD change a "
        "landed measurement -- that is the STOP condition and it is no longer merely documentation"
    )


def test_the_workload_the_preregistration_binds_has_no_blocker_on_either_side():
    requirements = loads((REPO_ROOT / "architecture" / "exchange"
                          / "scl_requirements.yaml").read_text())
    rows = requirements["workloads"]["kalman_filter_linear"]["blocking_requirements"]
    assert {row["owner"] for row in rows} == {"daq"}, (
        "a compute-layer blocker has appeared for kalman_filter_linear; the record says there is "
        "none and needs re-measuring"
    )
    assert {row["status"] for row in rows} == {"SATISFIED"}


def test_this_record_does_not_claim_to_bind_the_preregistration():
    coverage = loads((REPO_ROOT / "architecture" / "doctrine_coverage.yaml").read_text())
    unbound = coverage["one_artifact_is_not_covered_for_currency"]["measured"]
    assert "kalman_validation_preregistration.yaml" in unbound, (
        "the pre-registration must still be recorded as unbound: checking two arithmetic "
        "identities is not asserting its claims"
    )
    # Asserted on the VALUE. This is the THIRD time in this session the
    # same author has written a check that reads its own index instead of
    # its content, and all three were in the same construction: a key
    # phrased as a negation, with the assertion looking for the negation
    # in the value it introduces.
    disclaimer = RECORD["what_this_file_is_not"]
    assert disclaimer.startswith("a binding.")
    assert "is not asserting its claims" in disclaimer
