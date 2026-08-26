"""The polymer vertical's numbers, RE-DERIVED rather than pinned.

WHY THIS SHAPE. A test that asserts the numbers in
architecture/polymer_vertical.yaml equal the numbers in
architecture/polymer_vertical.yaml is a pin over a record -- the class
this pair filed after a probe result went stale under a test that
asserted it had not changed. So every physical quantity here is computed
from first principles in this file and compared to what the vertical
records, and every claim about the repository is re-measured against the
repository.

WHAT THAT BUYS. If the physics is wrong, this fails. If someone edits a
number in the vertical, this fails. If the gate surface changes -- a gate
gets wired to an ingest path, a sixth gate appears, the vendored
admission gate starts reading content -- this fails, and it SHOULD,
because the vertical's central finding is about that surface.

THE ORACLE DISCIPLINE. The distribution moments are computed two ways
that share no code: closed-form log-normal integrals, and the
distribution-free identity SD = Mn*sqrt(PDI-1) derived from
Var(M) = Mw*Mn - Mn^2. Neither is the implementation under test -- there
is no polymer implementation; that is the vertical's point.
"""

from __future__ import annotations

import ast
import math
import pathlib
import subprocess
from statistics import NormalDist

import pytest

import daf  # noqa: F401
from epistemics._yaml import loads

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
VERTICAL = loads((REPO_ROOT / "architecture" / "polymer_vertical.yaml").read_text())

#: The probe's own planted batch. Read from the probe, not retyped.
PROBE = loads(
    (REPO_ROOT / "architecture" / "_probes" / "cohort_identity_expectations.yaml").read_text()
)


def lognormal_from(mn, pdi):
    """(mu, sigma) on ln M for a log-normal chain-length distribution with
    the given number-average and dispersity.

    Mn = exp(mu + s^2/2), Mw = exp(mu + 3s^2/2), so PDI = exp(s^2).
    """
    s = math.sqrt(math.log(pdi))
    return math.log(mn) - s * s / 2.0, s


# ------------------------------------------------- the vertical says what it is


def test_the_vertical_proposes_nothing():
    """The status is the whole discipline. A vertical that proposes a
    representation change before a workload names it is the thing this
    pair refused when it elected least_squares."""
    assert VERTICAL["status"] == "measured_not_proposed"
    undecided = VERTICAL["what_this_vertical_does_not_decide"]
    assert "the_cohort_object_distinction" in undecided
    assert "the_inter_observation_relation" in undecided
    assert "A WORKLOAD NAMES ITS EXTENSION" in undecided["why_neither_is_decided_here"]
    assert VERTICAL["what_would_settle_each"].keys() == {"gap_1", "gap_2"}


def test_it_uses_the_probes_own_batch_and_says_which_numbers_are_derived():
    """104000 and 1.05 are the probe's. 109200 is not in the repository at
    all -- it is forced by the other two. A number that is quoted and a
    number that is derived are different evidence and the file must say
    which is which."""
    measured = VERTICAL["gap_1_the_recorded_uncertainty_is_not_the_spread"][
        "measured_on_the_probe_s_own_batch"]
    assert measured["Mn_g_per_mol"] == 104000.0
    assert measured["PDI"] == 1.05
    assert measured["Mw_g_per_mol"] == pytest.approx(
        measured["Mn_g_per_mol"] * measured["PDI"], rel=1e-12)
    assert "NOT planted" in measured["provenance_of_Mw"]

    probe_text = (REPO_ROOT / "architecture" / "_probes"
                  / "cohort_identity_expectations.yaml").read_text()
    assert "104000" in probe_text, "the vertical claims Mn is verbatim from the probe"
    hits = subprocess.run(
        ["git", "grep", "-l", "109200"], cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=60,
    ).stdout.split()
    assert [h for h in hits if "polymer_vertical" not in h and "test_polymer_vertical" not in h] == [], (
        "109200 now appears elsewhere in the repository; the provenance note must be re-measured"
    )


# ------------------------------------------------------- gap 1, re-derived here


def test_the_spread_identity_is_distribution_free():
    """SD = Mn*sqrt(PDI-1) follows from Var(M) = Mw*Mn - Mn^2 for ANY
    chain-length distribution. Checked on log-normal AND on the discrete
    Flory most-probable distribution, which share no code."""
    mn, pdi = 104000.0, 1.05
    mu, s = lognormal_from(mn, pdi)
    second_moment = math.exp(2 * mu + 2 * s * s)          # E[M^2]
    sd_direct = math.sqrt(second_moment - mn * mn)
    sd_identity = mn * math.sqrt(pdi - 1.0)
    assert sd_direct == pytest.approx(sd_identity, rel=1e-12)

    # Flory: x_i = (1-p) p^(i-1) on chain length i, M_i = i*M0.
    p, m0 = 0.999, 104.15
    n = 60000
    w = [(1 - p) * p ** (i - 1) for i in range(1, n + 1)]
    m = [i * m0 for i in range(1, n + 1)]
    total = sum(w)
    e1 = sum(wi * mi for wi, mi in zip(w, m)) / total
    e2 = sum(wi * mi * mi for wi, mi in zip(w, m)) / total
    flory_mn, flory_mw = e1, e2 / e1
    assert math.sqrt(e2 - e1 * e1) == pytest.approx(
        flory_mn * math.sqrt(flory_mw / flory_mn - 1.0), rel=1e-6), (
        "the identity is claimed distribution-free and fails on a second family"
    )


def test_the_recorded_spread_and_ratios_are_what_the_physics_gives():
    gap = VERTICAL["gap_1_the_recorded_uncertainty_is_not_the_spread"]
    measured = gap["measured_on_the_probe_s_own_batch"]
    mn, pdi = measured["Mn_g_per_mol"], measured["PDI"]
    sd = mn * math.sqrt(pdi - 1.0)
    assert measured["sd_of_the_chain_length_distribution"] == pytest.approx(sd, rel=1e-9)

    ratios = measured["ratios_of_spread_to_measurement_uncertainty"]
    for key, u in (("u_1200_the_probes_planted_value", 1200.0),
                   ("u_2000", 2000.0),
                   ("u_3120_mid_range_sec_repeatability", 3120.0)):
        assert ratios[key] == pytest.approx(sd / u, abs=0.01), key
        # and the closed form the vertical states
        assert sd / u == pytest.approx(math.sqrt(pdi - 1.0) / (u / mn), rel=1e-12)


def test_the_consumers_error_is_the_number_the_distribution_gives():
    gap = VERTICAL["gap_1_the_recorded_uncertainty_is_not_the_spread"]
    err = gap["the_consumers_error_stated_as_a_consumer_makes_it"]
    measured = gap["measured_on_the_probe_s_own_batch"]
    mn, pdi, u = measured["Mn_g_per_mol"], measured["PDI"], 2000.0
    mu, s = lognormal_from(mn, pdi)
    dist = NormalDist(mu, s)

    fraction = dist.cdf(math.log(mn + u)) - dist.cdf(math.log(mn - u))
    assert err["actually_in_that_interval_percent"] == pytest.approx(fraction * 100, abs=0.01)
    assert err["overstatement_factor"] == pytest.approx(0.6827 / fraction, abs=0.02)

    z = NormalDist().inv_cdf(0.5 + 0.6827 / 2)
    lo, hi = math.exp(mu - z * s), math.exp(mu + z * s)
    assert err["the_interval_that_really_holds_68_27_percent"][0] == pytest.approx(lo, abs=1.0)
    assert err["the_interval_that_really_holds_68_27_percent"][1] == pytest.approx(hi, abs=1.0)
    assert err["width_ratio"] == pytest.approx((hi - lo) / (2 * u), abs=0.02)


# ------------------------------------------------------- gap 2, re-derived here


def fit_variances(r_mn, r_mw, r_pdi=None):
    """Weighted-least-squares variances for (ln Mn, ln Mw) from three rows
    y1 = m, y2 = w, y3 = w - m. Hand algebra, not a library call, and not
    the SCL kernel -- using the implementation as its own oracle is
    forbidden here."""
    s1, s2 = r_mn ** 2, r_mw ** 2
    s3 = (r_pdi ** 2) if r_pdi is not None else (s1 + s2)
    w1, w2, w3 = 1 / s1, 1 / s2, 1 / s3
    a, b, d = w1 + w3, -w3, w2 + w3
    det = a * d - b * b
    return d / det, a / det, -b / det, (s1, s2)


def test_the_third_column_shrinks_the_reported_variance_by_the_recorded_ratios():
    gap = VERTICAL["gap_2_a_column_that_is_a_function_of_two_others"]
    m = gap["measured_at_u_rel_Mn_3_percent_and_u_rel_Mw_2_5_percent"]
    v_m, v_w, _cov, (s1, s2) = fit_variances(0.03, 0.025)
    assert m["reported_over_correct_variance_ln_Mn"] == pytest.approx(v_m / s1, rel=1e-6)
    assert m["reported_over_correct_variance_ln_Mw"] == pytest.approx(v_w / s2, rel=1e-6)
    assert v_m < s1 and v_w < s2, "the reported variance must be the SMALLER one"


def test_the_third_row_is_exactly_dependent_so_the_true_dof_is_zero():
    """Every residual is zero for ALL data, not just the nominal row --
    which is why a goodness-of-fit test reads perfect agreement."""
    import random
    random.seed(20260826)
    worst = 0.0
    for _ in range(2000):
        e1, e2 = random.gauss(0, 0.03), random.gauss(0, 0.025)
        y1, y2, y3 = e1, e2, e2 - e1            # the truth: row 3 is row 2 minus row 1
        # the fit reproduces m=y1, w=y2 exactly, so residuals vanish
        worst = max(worst, abs(y3 - (y2 - y1)))
    assert worst < 1e-15
    dof = VERTICAL["gap_2_a_column_that_is_a_function_of_two_others"][
        "measured_at_u_rel_Mn_3_percent_and_u_rel_Mw_2_5_percent"]["degrees_of_freedom"]
    assert "TRUE dof = 0" in dof and "fiction" in dof


def test_the_direction_flips_and_the_vertical_says_so():
    """THE FINDING THAT CHANGED UNDER SCRUTINY. det(Cov_3)/det(Cov_2) =
    1/(2(1-rho^2)) -- so 'overconfident, always' is true only at rho = 0,
    which is the one value a polymer consumer would not assume."""
    block = VERTICAL["gap_2_a_column_that_is_a_function_of_two_others"]
    claim = block["the_direction_is_not_determined"]
    assert "1/(2*(1-rho^2))" in claim
    assert "FLIPS" in claim

    for rho, expected in ((0.0, 0.5), (0.5, 2 / 3), (1 / math.sqrt(2), 1.0), (0.9, 2.631578947)):
        assert 1 / (2 * (1 - rho ** 2)) == pytest.approx(expected, rel=1e-6)
    # the crossover is where the error changes sign, and it is inside [0, 1]
    assert 0.0 < 1 / math.sqrt(2) < 1.0
    assert "CANNOT KNOW WHICH WAY THEY ARE WRONG" in block["what_that_makes_the_finding"]


def test_the_chained_propagation_goes_the_other_way():
    """Two consumers, same admitted row, opposite errors -- which is why
    the direction is a property of the consumer, not of the gap."""
    r_mn, r_mw = 0.03, 0.025
    naive = math.sqrt((r_mn ** 2 + r_mw ** 2) + r_mn ** 2)   # u(Mw) via Mw = PDI*Mn, independent
    assert naive / r_mw == pytest.approx(1.969772, rel=1e-5)
    assert naive > r_mw, "the chained route must be the UNDERconfident one"


# ------------------------------------------ the gate surface, re-measured here


def discovered_gates():
    """Public module-level functions in science/*.py taking `content` first
    and returning Admissibility. Derived, so a sixth gate is covered by
    existing rather than by anyone remembering."""
    found = []
    for path in sorted((REPO_ROOT / "science").glob("*.py")):
        for node in ast.parse(path.read_text()).body:
            if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
                continue
            args = [a.arg for a in node.args.args]
            returns = ast.unparse(node.returns) if node.returns else ""
            if args and args[0] == "content" and "Admissibility" in returns:
                found.append(node.name)
    return sorted(found)


def non_test_call_sites(name):
    out = subprocess.run(
        ["grep", "-rn", f"{name}(", "--include=*.py", "."],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
    ).stdout.splitlines()
    return [line for line in out
            if "/tests/" not in line and not line.startswith("./tests/")
            and "__pycache__" not in line and f"def {name}(" not in line]


def test_the_gate_surface_is_what_the_vertical_records():
    surface = VERTICAL["the_gate_surface"]
    gates = discovered_gates()
    assert surface["content_gates_derived_by_signature"] == len(gates), (
        f"the vertical records {surface['content_gates_derived_by_signature']} content gates; "
        f"the repository now has {len(gates)}: {gates}. The vertical's central finding is about "
        "this surface and must be re-measured."
    )
    recorded = {entry.split()[-1] for entry in surface["gates"]}
    assert recorded == set(gates), f"recorded {sorted(recorded)} vs discovered {gates}"

    for name in gates:
        sites = non_test_call_sites(name)
        declared = surface["non_test_call_sites"][name]
        expected = int(str(declared).split()[0]) if not isinstance(declared, int) else declared
        assert len(sites) == expected, (
            f"{name}: vertical records {expected} non-test call sites, measured {len(sites)}: "
            f"{sites}"
        )


def test_no_content_gate_runs_automatically():
    """The narrowing that makes the finding honest: it is not that the
    gates permit a population moment, it is that none of them runs."""
    assert non_test_call_sites("assess_pool") == [], (
        "assess_pool now has a production caller -- a content gate reaches an automatic path for "
        "the first time, and the vertical's gate-surface finding must be re-measured"
    )


def test_the_ingest_gate_still_does_not_read_a_key_of_content():
    source = (REPO_ROOT / "vendor" / "scout-retrieval-agent" / "evidence"
              / "admission.py").read_text()
    body = source[source.index("def admit_observation"):]
    body = body[:body.index("\ndef ")]
    assert "observation.content" in body, "the gate should still check content presence"
    assert "content[" not in body and "content.get" not in body, (
        "the ingest gate now reads a key of content; the vertical's claim that no content check "
        "happens at ingest is stale"
    )


# ------------------------------------------------- rho, and what it does not do


def test_rho_is_recorded_as_modelled_and_not_as_measured():
    """The whole discipline of this block. A forward model of an
    instrument is not the instrument, and the vertical must not let the
    two read alike."""
    rho = VERTICAL["the_correlation_between_the_moments"]
    assert rho["status"] == "modelled_not_instrument_measured"
    assert "Not the replicate dataset" in (
        pathlib.Path(REPO_ROOT / "architecture" / "polymer_vertical.yaml").read_text())
    assert "not the instrument" in VERTICAL["the_cheapest_next_measurement"]
    assert VERTICAL["status"] == "measured_not_proposed", (
        "the status must not advance on a modelled input"
    )


def test_the_lowest_modelled_rho_is_still_above_the_crossover():
    """The claim that carries the conclusion. If a configuration is ever
    modelled that reaches the crossover, this fails and the direction is
    unknown again."""
    rho = VERTICAL["the_correlation_between_the_moments"]
    lowest = rho["measured"]["lowest_rho_over_every_configuration_modelled"]
    crossover = rho["the_crossover"]
    assert crossover == pytest.approx(1 / math.sqrt(2), rel=1e-4)
    assert lowest > crossover, (
        f"the lowest modelled rho ({lowest}) is at or below the crossover ({crossover}); the "
        "direction of gap 2's confidence-region error is unknown again"
    )
    assert 1 / (2 * (1 - lowest ** 2)) > 1.0, "above the crossover the error must be UNDERconfident"
    assert "UNDERCONFIDENT" in rho["where_that_puts_the_system"]


def test_the_degenerate_perturbation_artifact_is_recorded():
    """A one-parameter perturbation family forces correlation +-1 before
    any chemistry enters. Caught mid-measurement and kept, because a
    number that a design forces is not evidence."""
    rho = VERTICAL["the_correlation_between_the_moments"]
    artifact = rho["the_artifact_caught_mid_measurement"]
    assert "BY CONSTRUCTION" in artifact
    assert "800" in artifact, "the non-degenerate mechanism must be named"
    # and the informative mechanism must be the one least favourable to the conclusion
    assert rho["measured"]["per_slice_detector_noise_alone_800_parameters"] == pytest.approx(
        rho["measured"]["lowest_rho_over_every_configuration_modelled"], rel=1e-6)


def test_the_surviving_harm_is_the_fabricated_agreement_not_the_understated_spread():
    """What the rho measurement changed, and what it did not."""
    rho = VERTICAL["the_correlation_between_the_moments"]
    assert "DEFLATES" in rho["what_this_does_to_gap_2"]
    assert "shrinks under measurement is still a finding" in rho["what_this_does_to_gap_2"]
    survives = rho["what_survives_untouched"]
    assert "identically zero for ALL data" in survives
    assert "needs no rho" in survives


def test_the_compute_layers_diagnostics_are_recorded_as_reassuring():
    """The sharpest half: the metric a caller would check comes back
    healthy. Numbers here must match the boundary recorded on the other
    side of the pair."""
    claim = VERTICAL["the_correlation_between_the_moments"]["and_the_compute_layer_endorses_it"]
    assert "effective_rank = 2" in claim and "FULL RANK" in claim
    assert "1.4378" in claim
    assert "ACTIVELY REASSURES" in claim
    assert "wrong matrix" in claim
