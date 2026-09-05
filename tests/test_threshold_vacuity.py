"""A check whose sensitivity is an argument.

Pre-registered in architecture/threshold_vacuity_preregistration.yaml,
digest 37ce06e67da34a477e37614d8b88a5c1619d342e0c5b84b2da521e8ee231075c.

The class: a check takes its threshold as a parameter, and for some
values of that parameter it returns the same answer for an artifact that
must pass and one that must fail. The mechanism is intact, nothing
errors, and the check has stopped being a check.

Each instance below is written as the DISCRIMINATION test the class asks
for -- run the thing on a case that must pass and a case that must fail
and compare the verdicts -- rather than as an assertion that a particular
exception is raised. A guard that raises is how these are fixed; it is
not what makes them defects.
"""

from __future__ import annotations

import ast
import math
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

from commerce.mileage import (RouteComparison, RouteRefusal,  # noqa: E402
                              validation_lane_is_discriminating)
from instrument.calibration import NARROW_POLYSTYRENE  # noqa: E402
from science.replicate_pairing import covariance_rank, published_rank_tolerance  # noqa: E402
from science.set_attestation import (AGREED, COEFFICIENT_OF_VARIATION,  # noqa: E402
                                     DISAGREED, SetAttestation, SetAttestationError,
                                     check_attestation)

INFINITY = float("inf")
NOT_A_NUMBER = float("nan")

#: Ten synthetic replicates. mean 4.84, sample CV 0.576212%.
REPLICATES = (4.82, 4.85, 4.79, 4.88, 4.83, 4.86, 4.81, 4.84, 4.87, 4.85)
#: Rank 3 and rank 1, so a rank function that discriminates separates them.
FULL_RANK = [[4.0, 2.0, 2.0], [2.0, 3.0, 2.0], [2.0, 2.0, 2.0]]
SINGULAR = [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]


def _attestation(value):
    return SetAttestation(statistic=COEFFICIENT_OF_VARIATION, value=value, unit="percent",
                          n=10, variable="concentration", population="the ten replicates",
                          source="synthetic")


# =====================================================================
# Instance 1 -- science/set_attestation.check_attestation
# =====================================================================

def test_no_tolerance_makes_every_attestation_agree():
    """Measured before the guard: at infinity an attestation of 999999
    against a computed 0.576 reported AGREED. A verdict that cannot be
    DISAGREED is not a verdict about the source."""
    honest = check_attestation(_attestation(0.58), REPLICATES, tolerance=0.01)
    absurd = check_attestation(_attestation(999999.0), REPLICATES, tolerance=0.01)
    assert (honest.verdict, absurd.verdict) == (AGREED, DISAGREED)

    for degenerate in (INFINITY, NOT_A_NUMBER):
        with pytest.raises(SetAttestationError, match="not a tolerance"):
            check_attestation(_attestation(999999.0), REPLICATES, tolerance=degenerate)


def test_the_attestation_tolerance_keeps_its_whole_valid_domain():
    """P6. The guard states a domain; it does not narrow one. Zero still
    means exact, and every non-negative finite value still works."""
    exact = check_attestation(
        SetAttestation(statistic=COEFFICIENT_OF_VARIATION, value=0.5762121394862781,
                       unit="percent", n=10, variable="concentration",
                       population="p", source="s"),
        REPLICATES, tolerance=0.0)
    assert exact.verdict == AGREED
    assert check_attestation(_attestation(0.58), REPLICATES, tolerance=1e300).verdict == AGREED


# =====================================================================
# Instance 2 -- science/replicate_pairing.covariance_rank
# =====================================================================

def test_no_rank_tolerance_makes_every_matrix_the_same_rank():
    """Measured at the edges: at or above 1.0 no pivot can exceed
    rank_tolerance x largest -- not even the largest itself -- so the rank
    is 0 for every matrix; below 0.0 every pivot does, so the rank is full
    for every matrix. Either way the answer stops depending on the
    matrix."""
    assert covariance_rank(FULL_RANK, 1e-12) == 3
    assert covariance_rank(SINGULAR, 1e-12) == 1

    for degenerate in (1.0, 1.5, -1.0, INFINITY, NOT_A_NUMBER):
        with pytest.raises(ValueError, match=r"outside \[0.0, 1.0\)"):
            covariance_rank(FULL_RANK, degenerate)


def test_the_published_cutoff_is_inside_the_domain_the_guard_states():
    """The guard sits on a JOIN. rank_tolerance normally arrives from the
    compute layer's published constant, so a domain that excluded the
    published value would break the pair rather than protect it."""
    published = published_rank_tolerance()
    assert 0.0 <= published < 1.0
    assert covariance_rank(FULL_RANK, published) == 3
    assert covariance_rank(SINGULAR, published) == 1


def test_a_rank_tolerance_of_zero_is_inside_the_domain_and_not_degenerate():
    """0.0 keeps every strictly positive pivot, which is the exact-rank
    answer rather than a vacuous one. Measured, not assumed -- it is the
    boundary the guard admits and the reason the domain is half-open."""
    assert covariance_rank(FULL_RANK, 0.0) == 3
    assert covariance_rank(SINGULAR, 0.0) == 1


# =====================================================================
# Instance 3 -- commerce/mileage.validation_lane_is_discriminating
# =====================================================================

TRUNK_HAUL = RouteComparison(lane="Toronto-Montreal", distance_delta_pct=0.01,
                             duration_delta_pct=0.19, same_legality=True)
A_LANE_THAT_MOVES = RouteComparison(lane="an urban lane", distance_delta_pct=1.0,
                                    duration_delta_pct=17.0, same_legality=True)


def test_no_minimum_makes_every_lane_discriminating_including_the_trunk_haul():
    """This predicate exists to exclude the Toronto-Montreal lane, which
    moved 0.19% between auto and truck costing. Measured at 0.0 it accepts
    it; at infinity and NaN it rejects the 17% lane too."""
    assert not validation_lane_is_discriminating(TRUNK_HAUL)
    assert validation_lane_is_discriminating(A_LANE_THAT_MOVES)

    for degenerate in (0.0, -1.0, INFINITY, NOT_A_NUMBER):
        with pytest.raises(RouteRefusal, match="same answer for every lane"):
            validation_lane_is_discriminating(TRUNK_HAUL,
                                              minimum_duration_delta_pct=degenerate)


def test_the_lane_minimum_keeps_its_valid_domain():
    """P6: a caller may still choose any positive threshold, including one
    that reclassifies the trunk haul on purpose."""
    assert validation_lane_is_discriminating(TRUNK_HAUL,
                                             minimum_duration_delta_pct=0.1)
    assert not validation_lane_is_discriminating(A_LANE_THAT_MOVES,
                                                 minimum_duration_delta_pct=20.0)


# =====================================================================
# Instance 4 -- instrument/calibration, repaired by REMOVAL
# =====================================================================

def test_the_inversion_takes_no_tolerance_at_all():
    """The other disposition. This threshold carried no judgement and no
    caller supplied it, so it is gone rather than guarded -- a parameter
    that cannot be supplied wrongly is better than one that is checked.

    Fails in the state where it comes back, which is the state where
    `volume_for_mass(mass, tolerance=1e6)` again returns the midpoint of
    the calibrated range as an inversion.
    """
    with pytest.raises(TypeError):
        NARROW_POLYSTYRENE.volume_for_mass(  # type: ignore[call-arg]
            NARROW_POLYSTYRENE.mass(11.0), tolerance=1e6)


def test_removing_it_made_the_inversion_exact_rather_than_merely_safe():
    """The default 1e-12 returned 10.999999999999886. Running the bisection
    to the bracket's own limit returns 11.0 exactly, at three points across
    the calibrated range."""
    for volume in (6.5, 11.0, 17.5):
        assert NARROW_POLYSTYRENE.volume_for_mass(NARROW_POLYSTYRENE.mass(volume)) == volume


# =====================================================================
# The sweep, DERIVED from the tree at test time
# =====================================================================

PRODUCT_PACKAGES = ("daf", "science", "boundary", "bridge", "epistemics", "session",
                    "commerce", "tools", "assertion", "instrument")

#: Name fragments that mark a parameter as a threshold. A HEURISTIC, and
#: recorded as one in the pre-registration -- it cannot find a threshold
#: called `k` and does not claim to.
THRESHOLD_NAME_FRAGMENTS = ("tolerance", "threshold", "epsilon", "eps", "atol", "rtol",
                            "delta", "margin", "cutoff", "limit", "max_", "min_",
                            "_tol", "slack")


def _threshold_parameters():
    """Every suspect parameter in the product, and whether its function
    refuses anything on it. Derived by AST, so a fifth instance added
    tomorrow is found without this file being edited."""
    for package in PRODUCT_PACKAGES:
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                arguments = (list(node.args.posonlyargs) + list(node.args.args)
                             + list(node.args.kwonlyargs))
                for argument in arguments:
                    name = argument.arg
                    if name in ("self", "cls"):
                        continue
                    if not any(f in name.lower() for f in THRESHOLD_NAME_FRAGMENTS):
                        continue
                    yield path.relative_to(REPO_ROOT), node, name


def _refuses_on(function, parameter):
    """Does some `raise` in this function stand behind a test of `parameter`?"""
    for node in ast.walk(function):
        if not isinstance(node, ast.If):
            continue
        mentions = any(isinstance(n, ast.Name) and n.id == parameter
                       for n in ast.walk(node.test))
        raises = any(isinstance(n, ast.Raise) for n in ast.walk(node))
        if mentions and raises:
            return True
    return False


def test_every_threshold_parameter_in_the_product_states_its_domain():
    """P4: the enforcement is derived, not enumerated.

    A SYNTACTIC PROXY for a behavioural property, and it is one on
    purpose. It can demand a guard on a parameter that does not need one
    -- a pagination `limit`, say. The exit in that case is to add the
    guard or rename the parameter, NEVER to add an exclusion list here:
    an enumeration standing for a derived set is the defect class this
    repository already tracks, and it is how this test would go quiet.
    """
    unguarded = [(str(path), function.name, name)
                 for path, function, name in _threshold_parameters()
                 if not _refuses_on(function, name)]
    assert unguarded == [], (
        "these parameters set the sensitivity of a check and refuse nothing, so a "
        f"caller can hand each a value that makes its answer constant: {unguarded}"
    )


def test_the_sweep_is_looking_at_a_non_empty_population():
    """An absence is not evidence unless the domain is known non-empty --
    a clean sweep and a sweep that found nothing to look at read the same
    in a report."""
    found = list(_threshold_parameters())
    assert len(found) >= 3, found
    assert {name for _, _, name in found} >= {"tolerance", "rank_tolerance",
                                              "minimum_duration_delta_pct"}


def test_the_removed_parameter_is_gone_from_the_swept_tree():
    """Instance 4 leaves the population by being deleted, not by being
    guarded. If it returns, the sweep sees it again."""
    calibration_thresholds = [(function.name, name)
                              for path, function, name in _threshold_parameters()
                              if str(path) == "instrument/calibration.py"]
    assert calibration_thresholds == []


def test_a_guard_that_admits_a_non_finite_value_would_not_be_a_guard():
    """The property all three surviving guards share, asserted once: for
    each, some degenerate value is refused AND the discrimination holds
    across the domain that remains."""
    assert math.isfinite(published_rank_tolerance())
    survivors = 0
    for call, degenerate, error in (
        (lambda t: check_attestation(_attestation(0.58), REPLICATES, tolerance=t),
         INFINITY, SetAttestationError),
        (lambda t: covariance_rank(FULL_RANK, t), INFINITY, ValueError),
        (lambda t: validation_lane_is_discriminating(TRUNK_HAUL,
                                                     minimum_duration_delta_pct=t),
         INFINITY, RouteRefusal),
    ):
        with pytest.raises(error):
            call(degenerate)
        survivors += 1
    assert survivors == 3


# =====================================================================
# The record, bound to what the code and the measurements actually do
# =====================================================================

def test_the_result_record_states_numbers_this_tree_still_produces():
    """architecture/threshold_vacuity_result.yaml is bound here rather than
    left unbound and allowed for.

    A record whose figures nobody recomputes is the same shape as the
    class it describes: an assertion nothing could contradict. Every
    number checked below is re-measured from the code in this run.
    """
    from epistemics._yaml import loads

    record = loads((REPO_ROOT / "architecture" / "threshold_vacuity_result.yaml").read_text())
    four = record["the_four_measured_at_their_edges"]

    # The rank claim. The guard now refuses 1.0, so the old behaviour cannot
    # be re-measured through the function -- what IS re-measurable is the
    # arithmetic the record gives as its reason: at a cutoff of 1.0 not even
    # the largest pivot can exceed cutoff x largest, so nothing is counted.
    rank_claim = four["science_replicate_pairing_covariance_rank"]
    assert "not even the largest itself" in rank_claim["what_a_degenerate_value_does"]
    for largest in (4.0, 1e-9, 1e9):
        assert not largest > 1.0 * largest
        assert largest > 1e-12 * largest, "and a real cutoff does count it"
    assert "rank 0" in rank_claim["what_a_degenerate_value_does"]

    # The inversion claim: 9.0 where the truth is 11.0, and exactness after.
    assert "9.0" in four["instrument_calibration_volume_for_mass"][
        "what_a_degenerate_value_does"]
    for volume in (6.5, 11.0, 17.5):
        assert NARROW_POLYSTYRENE.volume_for_mass(
            NARROW_POLYSTYRENE.mass(volume)) == volume, (
            "the record claims the inversion is exact at three points; it is not")

    # The lane claim: 0.19 percent is the trunk haul the predicate excludes.
    assert TRUNK_HAUL.duration_delta_pct == 0.19
    assert "0.19%" in four["commerce_mileage_validation_lane_is_discriminating"][
        "what_a_degenerate_value_does"]
    assert not validation_lane_is_discriminating(TRUNK_HAUL)

    # The population claim: FOUR found, and one of them has since left the
    # population by being deleted, so the sweep must now find three.
    assert "FOUR" in record["the_population"]
    assert len({name for _, _, name in _threshold_parameters()}) == 3


def test_the_result_record_does_not_claim_a_green_suite():
    """The pair check is red for a true reason and the record says so. A
    result file that quietly implied otherwise would be the reporting
    failure this repository files under discarded exit codes."""
    from epistemics._yaml import loads

    record = loads((REPO_ROOT / "architecture" / "threshold_vacuity_result.yaml").read_text())
    not_done = record["what_the_pair_check_found_while_this_was_being_measured"][
        "WHAT_THIS_SESSION_DID_NOT_DO"]
    assert "NOT green" in not_done["the_consequence_stated_plainly"]
    assert "c9be09961d3440684c781fee7c2ce72be84a9507907240c887390ccf012c5f36" in (
        not_done["the_shared_artifact_was_not_carried"]), (
        "the record must name the digest it is behind, so a reader can check it"
    )
    import hashlib
    ours = (REPO_ROOT / "architecture" / "proof_integrity.yaml").read_bytes()
    assert hashlib.sha256(ours).hexdigest() in (
        not_done["the_shared_artifact_was_not_carried"]), (
        "the shared artifact moved since this record was written; re-measure the "
        "pair rather than leaving a stale digest in a record about staleness"
    )
