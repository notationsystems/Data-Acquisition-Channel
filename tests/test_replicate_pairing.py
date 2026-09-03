"""The pairing-preserving consumer, validated against a KNOWN correlation.

THE ORACLE DISCIPLINE MATTERS MORE HERE THAN USUAL. The thing under test
computes a correlation, and the only way to know it is right is to feed it
data whose correlation was fixed before the consumer saw it. So the
replicates are drawn from a bivariate normal with rho set by hand, and the
consumer is required to recover that rho -- never to agree with itself,
and never checked against `materials.analysis`, which is the projection
this module exists because of.

NO INSTRUMENT AND NO DATA ARE NEEDED, which was the point of building it
now: synthetic replicates exercise every path. When a real GPC report
arrives, the consumer and the extractor contract already exist and the one
irreversible precondition -- one Record per run -- is the only thing that
had to be right at acquisition time.
"""

from __future__ import annotations

import ast
import datetime
import math
import pathlib
import random
import statistics
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.storage.frozen_mapping import FrozenMapping  # noqa: E402
from evidence.types import make_observation  # noqa: E402
from science.replicate_pairing import (AMBIGUOUS_RUN_IDENTITY,  # noqa: E402
                                       EVERY_RUN_DIFFERS_IN,
                                       CONFLICTING_VALUE_FOR_A_RUN,
                                       DEGENERATE_VARIABLE,
                                       RAGGED_REPLICATE_SET,
                                       RANK_DEFICIENT_COVARIANCE,
                                       TOO_FEW_RUNS_FOR_A_COVARIANCE,
                                       covariance_of, pair_replicates,
                                       published_rank_tolerance,
                                       sample_covariance)
from epistemics import _yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

WHEN = datetime.datetime(2026, 8, 26, tzinfo=datetime.timezone.utc)
CONDITIONS = FrozenMapping({"column_calibration": "polystyrene_standards", "solvent": "THF"})


def observation(run, variable, value, uncertainty=1200.0, conditions=CONDITIONS,
                sample="PS-lot-4471", record_ids=None):
    return make_observation(
        record_ids=(f"gpc-run-{run}",) if record_ids is None else record_ids,
        extraction_method="gpc_report_v1",
        content={"sample_id": sample, "property": variable, "value": value,
                 "unit": "g/mol", "uncertainty": uncertainty,
                 "uncertainty_kind": "stated", "conditions": conditions},
        confidence=1.0, extracted_at=WHEN)


def correlated_runs(n, rho, seed=20260826):
    """Bivariate normal (ln Mn, ln Mw) with the correlation FIXED HERE.

    Drawn by the Cholesky construction rather than by any repository code,
    so the truth the consumer is measured against is independent of it.
    """
    rng = random.Random(seed)
    mn0, mw0 = math.log(104000.0), math.log(109200.0)
    s_mn, s_mw = 0.03, 0.025
    runs = []
    for _ in range(n):
        z1, z2 = rng.gauss(0, 1), rng.gauss(0, 1)
        e1 = z1
        e2 = rho * z1 + math.sqrt(1 - rho * rho) * z2
        runs.append((math.exp(mn0 + s_mn * e1), math.exp(mw0 + s_mw * e2)))
    return runs


def observations_for(runs, **kwargs):
    out = []
    for index, (mn, mw) in enumerate(runs):
        out.append(observation(index, "number_average_molar_mass", mn, **kwargs))
        out.append(observation(index, "weight_average_molar_mass", mw, **kwargs))
    return out


# ------------------------------------------------------------- the pairing


def test_the_pairing_the_projection_could_not_express():
    runs = correlated_runs(5, 0.9)
    pairing = pair_replicates(observations_for(runs))
    assert len(pairing.sets) == 1 and not pairing.refusals
    replicates = pairing.sets[0]
    assert len(replicates.run_ids) == 5
    assert replicates.variables == ("number_average_molar_mass",
                                    "weight_average_molar_mass")

    pairs = replicates.paired("number_average_molar_mass", "weight_average_molar_mass")
    assert len(pairs) == 5
    for (mn, mw), (expected_mn, expected_mw) in zip(pairs, runs):
        assert mn == pytest.approx(expected_mn)
        assert mw == pytest.approx(expected_mw), (
            "the i-th Mn is paired with the wrong Mw -- the one thing this module exists to do"
        )


def test_the_run_identity_never_enters_the_comparison_context():
    """The Phase 16/17 rule, applied. If the Record leaked into the
    context, every run would be its own set and nothing would pair."""
    pairing = pair_replicates(observations_for(correlated_runs(5, 0.5)))
    assert len(pairing.sets) == 1, (
        f"{len(pairing.sets)} sets from one batch -- something run-unique reached the context"
    )
    context_keys = {key for key, _ in pairing.sets[0].context}
    assert "value" not in context_keys and "property" not in context_keys
    assert not any("run" in key for key in context_keys)


def test_a_per_run_uncertainty_does_not_split_the_set():
    """The deliberate divergence from the vendored grouping, which splits
    on exactly this and turns a replicate set into singletons."""
    runs = correlated_runs(5, 0.8)
    observations = []
    for index, (mn, mw) in enumerate(runs):
        observations.append(observation(index, "number_average_molar_mass", mn,
                                        uncertainty=1200.0 + index))
        observations.append(observation(index, "weight_average_molar_mass", mw,
                                        uncertainty=1100.0 + index))
    pairing = pair_replicates(observations)
    assert len(pairing.sets) == 1, "a per-run uncertainty split the set"

    # and nothing was discarded to achieve that
    cells = [cell for row in pairing.sets[0].rows for cell in row]
    assert {c.uncertainty for c in cells} == {1200.0 + i for i in range(5)} | {
        1100.0 + i for i in range(5)}, "the per-run figures must travel with their values"
    assert all(c.uncertainty_kind == "stated" for c in cells)


def test_a_genuine_condition_still_splits_the_set():
    """The discriminating case. If nothing split it, the context would be
    doing no work and the test above would be meaningless."""
    runs = correlated_runs(4, 0.5)
    other = FrozenMapping({"column_calibration": "narrow_pmma", "solvent": "THF"})
    observations = observations_for(runs) + observations_for(
        correlated_runs(4, 0.5, seed=7), conditions=other)
    pairing = pair_replicates(observations)
    assert len(pairing.sets) == 2, (
        "a different calibration is a different quantity and must not be pooled"
    )


# --------------------------------------------------- the correlation recovered


@pytest.mark.parametrize("rho", [-0.6, 0.0, 0.5, 0.9, 0.99])
def test_the_recovered_correlation_matches_the_one_it_was_drawn_with(rho):
    """The oracle is the generating process, not the module."""
    runs = correlated_runs(4000, rho, seed=hash(str(rho)) % 100000)
    results = covariance_of(observations_for(runs))
    assert len(results) == 1
    covariance = results[0].covariance
    assert covariance is not None and covariance.n_runs == 4000

    recovered = covariance.rho("number_average_molar_mass", "weight_average_molar_mass")
    assert recovered == pytest.approx(rho, abs=0.05), (
        f"drawn with rho={rho}, recovered {recovered}"
    )
    assert covariance.correlation[0][0] == pytest.approx(1.0)
    assert covariance.rho("weight_average_molar_mass",
                          "number_average_molar_mass") == pytest.approx(recovered)


def test_the_covariance_matches_an_independent_computation():
    """Not the module checking itself: the same numbers by a different route."""
    runs = correlated_runs(200, 0.7, seed=99)
    replicates = pair_replicates(observations_for(runs)).sets[0]
    covariance = sample_covariance(replicates)

    mn = [m for m, _ in runs]
    mw = [w for _, w in runs]
    assert covariance.means[0] == pytest.approx(statistics.fmean(mn))
    assert covariance.covariance[0][0] == pytest.approx(statistics.variance(mn))
    assert covariance.covariance[1][1] == pytest.approx(statistics.variance(mw))
    assert covariance.correlation[0][1] == pytest.approx(
        statistics.correlation(mn, mw), abs=1e-12)


def test_it_is_the_pairing_that_carries_the_answer():
    """THE POINT, shown by destroying only the pairing. Same values, same
    marginals, order of one column shuffled -- which is exactly what the
    projection's bare tuples leave available -- and the correlation is
    gone."""
    runs = correlated_runs(500, 0.9, seed=5)
    real = covariance_of(observations_for(runs))[0].covariance.rho(
        "number_average_molar_mass", "weight_average_molar_mass")

    rng = random.Random(1)
    shuffled = [w for _, w in runs]
    rng.shuffle(shuffled)
    scrambled = list(zip([m for m, _ in runs], shuffled))
    lost = covariance_of(observations_for(scrambled))[0].covariance.rho(
        "number_average_molar_mass", "weight_average_molar_mass")

    assert real == pytest.approx(0.9, abs=0.05)
    assert abs(lost) < 0.15, f"shuffling one column left rho at {lost}"
    assert abs(real - lost) > 0.5, (
        "the same values in a different pairing must give a different answer, or the pairing is "
        "not what carries it"
    )


# ------------------------------------------------------------- the refusals


def test_an_observation_naming_several_records_has_no_row():
    bad = observation(0, "number_average_molar_mass", 104000.0,
                      record_ids=("gpc-run-0", "gpc-run-1"))
    pairing = pair_replicates([bad])
    assert any(code == AMBIGUOUS_RUN_IDENTITY for code, _ in pairing.refusals)
    assert not pairing.sets


def test_the_same_variable_twice_on_one_run_is_refused():
    observations = [observation(0, "number_average_molar_mass", 104000.0),
                    observation(0, "number_average_molar_mass", 104900.0)]
    pairing = pair_replicates(observations)
    assert any(code == CONFLICTING_VALUE_FOR_A_RUN for code, _ in pairing.refusals), (
        "two answers to one question must not be silently reduced to one"
    )


def test_a_ragged_set_is_refused_rather_than_trimmed():
    """Dropping the short run would bias the covariance; dropping the
    variable would discard a measurement. Neither is this module's call."""
    runs = correlated_runs(3, 0.5)
    observations = observations_for(runs)
    observations = [o for o in observations
                    if not (o.record_ids[0] == "gpc-run-2"
                            and o.content["property"] == "weight_average_molar_mass")]
    pairing = pair_replicates(observations)
    assert any(code == RAGGED_REPLICATE_SET for code, _ in pairing.refusals)
    assert not pairing.sets


def test_one_run_is_not_a_sample_and_the_reason_is_given():
    results = covariance_of(observations_for(correlated_runs(1, 0.5)))
    assert len(results) == 1
    assert results[0].covariance is None
    assert TOO_FEW_RUNS_FOR_A_COVARIANCE in results[0].reasons, (
        "'there is no covariance' without 'because one run is not a sample' is the silence this "
        "repository keeps finding"
    )


def test_a_variable_that_did_not_move_is_named_not_guessed():
    runs = [(104000.0, w) for _, w in correlated_runs(5, 0.5)]
    results = covariance_of(observations_for(runs))
    covariance = results[0].covariance
    assert covariance.rho("number_average_molar_mass",
                          "weight_average_molar_mass") is None, (
        "a correlation against a zero-variance column is 0/0, not 0"
    )
    assert DEGENERATE_VARIABLE in results[0].reasons


def test_no_refusal_code_is_declared_and_unused():
    """The shape this project has filed repeatedly: a constant that names
    a condition nothing raises."""
    import re
    source = (REPO_ROOT / "science" / "replicate_pairing.py").read_text()
    declared = set(re.findall(r"^([A-Z][A-Z_]+) = \"", source, re.M))
    assert declared, "no refusal codes found"
    for code in declared:
        uses = len(re.findall(rf"(?<![\w\"]){code}(?![\w\"])", source))
        assert uses >= 2, f"{code} is declared and never raised"


# ------------------------------------- the irreversible precondition, as a gate


def observations_with(runs, extra=None, conditions=CONDITIONS):
    out = []
    for index, (mn, mw) in enumerate(runs):
        for variable, value in (("number_average_molar_mass", mn),
                                ("weight_average_molar_mass", mw)):
            content_extra = extra(index) if extra else {}
            obs = make_observation(
                record_ids=(f"gpc-run-{index}",), extraction_method="gpc_report_v1",
                content={"sample_id": "PS-lot-4471", "property": variable, "value": value,
                         "unit": "g/mol", "uncertainty": 1200.0,
                         "uncertainty_kind": "stated", "conditions": conditions,
                         **content_extra},
                confidence=1.0, extracted_at=WHEN)
            out.append(obs)
    return out


def test_a_run_identifier_in_content_is_named_not_silent():
    """THE DEFECT THIS FILE'S FIRST VERSION SHIPPED. A run id in content
    gives every observation its own context, so five runs become five
    singleton sets each reporting TOO_FEW_RUNS_FOR_A_COVARIANCE -- exactly
    what a genuine one-run pool reports. The failure the irreversible
    precondition exists to prevent produced NO refusal at all."""
    runs = correlated_runs(5, 0.9)
    pairing = pair_replicates(
        observations_with(runs, extra=lambda i: {"run_id": f"gpc-run-{i}"}))
    assert (EVERY_RUN_DIFFERS_IN, "run_id") in pairing.refusals, (
        "a run identifier in content must be named; silence here is unrecoverable later"
    )
    assert len(pairing.sets) == 5, "the sets are still singletons -- the refusal is the signal"


def test_the_honoured_contract_raises_nothing():
    pairing = pair_replicates(observations_with(correlated_runs(5, 0.9)))
    assert not pairing.refusals
    assert len(pairing.sets) == 1


def test_a_condition_that_really_changed_every_run_is_named_too():
    """And correctly. If temperature genuinely differs on every run these
    are NOT REPLICATES, and pooling them would be wrong. The module names
    the observable and does not decide which of the two it is."""
    runs = correlated_runs(5, 0.9)
    pairing = pair_replicates(
        observations_with(runs, extra=lambda i: {"temperature_C": 30.0 + i}))
    assert (EVERY_RUN_DIFFERS_IN, "temperature_C") in pairing.refusals


def test_a_real_condition_with_repeated_levels_is_not_flagged():
    """THE DISCRIMINATING CASE. Without it the check could be nothing more
    than 'complain whenever there is more than one set'."""
    runs = correlated_runs(6, 0.9)
    pairing = pair_replicates(
        observations_with(runs, extra=lambda i: {"temperature_C": 30.0 + (i % 2)}))
    assert not pairing.refusals, (
        f"a two-level condition was flagged: {pairing.refusals}. It splits the pool into two "
        "genuine groups, which is correct behaviour, not a leaked locator."
    )
    assert len(pairing.sets) == 2
    assert all(len(s.run_ids) == 3 for s in pairing.sets)


def test_the_code_does_not_claim_which_of_the_two_it_found():
    """Naming it RUN_ID_IN_CONTENT would assert the locator case and be
    wrong whenever the condition case holds -- the overclaim this project
    has filed before."""
    import re
    source = (REPO_ROOT / "science" / "replicate_pairing.py").read_text()

    # Check the DECLARED CODES, not the raw text. A first version asserted
    # the string "RUN_ID_IN_CONTENT" was absent from the file and failed on
    # the docstring that explains why the name was rejected -- which is the
    # documentation working, not a violation. A check that punishes its own
    # rationale is checking the wrong thing.
    declared = set(re.findall(r"^([A-Z][A-Z_]+) = \"", source, re.M))
    assert EVERY_RUN_DIFFERS_IN in declared
    # EXACT names, not substrings. The version before this asked whether
    # any code CONTAINS "RUN_ID" and caught AMBIGUOUS_RUN_IDENTITY, which
    # contains it and means something else entirely -- the aggregate/
    # substring class filed as the 22nd instance in
    # architecture/proof_integrity.yaml, recurring one commit after it was
    # written down, in a test written by the person who wrote it down.
    assert "RUN_ID_IN_CONTENT" not in declared, (
        f"a code names the locator case as though it were established: {sorted(declared)}"
    )
    assert "NOT REPLICATES" in source and "acquisition locator leaked" in source, (
        "both readings must stay recorded, or the code reads as diagnosing one of them"
    )


# ------------------------------------------- the covariance offered onward

def _polymer_observations(runs):
    """The three quantities a GPC report actually carries, where the third
    IS a function of the first two. In logs the relation is exact, and the
    fit is done in logs.

    This is not a contrived case. Any instrument that prints a derived
    quantity beside its inputs produces it, and this one is the row the
    polymer vertical is built on."""
    out = []
    for index, (mn, mw) in enumerate(runs):
        out.extend([
            observation(index, "number_average_molar_mass", math.log(mn)),
            observation(index, "weight_average_molar_mass", math.log(mw)),
            observation(index, "dispersity", math.log(mw / mn),
                        uncertainty=0.01),
        ])
    return out


def test_the_tolerance_is_read_from_the_counterpartys_artifact_not_typed_here():
    """The join, asserted as a join. If this module carried its own copy of
    1e-12, the two would stop agreeing the moment the compute layer moved
    its default, silently, because nothing compares a number in this file
    to a number in that header."""
    published = _yaml.loads(
        (REPO_ROOT / "architecture" / "exchange" / "scl_requirements.yaml").read_text()
    )["published_constants"]["least_squares_rank_tolerance_default"]
    assert published_rank_tolerance() == float(published)
    # Over the SYNTAX TREE, not the text. The first version of this check
    # searched the function's source for the literal and fired on its own
    # DOCSTRING, which names the value while explaining why it must not be
    # written down -- the proxy-for-target shape recorded in
    # architecture/proof_integrity.yaml, in a check written to protect a
    # join. A float in prose is not a float in code, and only one of them
    # can disagree with the counterparty.
    tree = ast.parse((REPO_ROOT / "science" / "replicate_pairing.py").read_text())
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "published_rank_tolerance"
    )
    literals = [
        node.value for node in ast.walk(function)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]
    assert not literals, (
        f"the tolerance is typed into the module that is supposed to read it: {literals}"
    )


def test_a_module_with_no_published_tolerance_refuses_rather_than_defaulting(tmp_path,
                                                                             monkeypatch):
    """The absence path, which is the one that would have been a default.

    A cutoff quietly standing in for the counterparty's is the same defect
    as copying it, with the extra property that nobody could see it had
    happened -- so the module raises."""
    import science.replicate_pairing as module

    empty = tmp_path / "architecture" / "exchange"
    empty.mkdir(parents=True)
    (empty / "scl_requirements.yaml").write_text('artifact: "scl_requirements"\n')
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)
    with pytest.raises(LookupError) as caught:
        module.published_rank_tolerance()
    assert "does not invent one" in str(caught.value)


def test_a_derived_third_variable_is_reported_rank_deficient():
    """THE ROW THE COMPUTE LAYER ASKED THIS LAYER TO ANSWER.

    Its blocking requirement says a covariance offered for whitening must
    be positive definite by the operation's own cutoff. This measures that
    the deficiency is DETECTED and NAMED rather than handed onward, where
    the compute layer measured what happens to it: over 2000 sets of this
    situation a plain Cholesky accepted 828 and refused 1172, the outcome
    decided by rounding."""
    runs = correlated_runs(6, 0.7)
    pairing = pair_replicates(_polymer_observations(runs))
    assert len(pairing.sets) == 1
    result = sample_covariance(pairing.sets[0])
    assert result is not None
    assert len(result.variables) == 3
    assert result.effective_rank == 2, (
        f"three variables, one an exact function of the other two, and the "
        f"covariance is reported at rank {result.effective_rank}"
    )
    assert RANK_DEFICIENT_COVARIANCE in result.reasons
    assert result.rank_tolerance == published_rank_tolerance()


def test_the_same_three_variables_measured_independently_are_full_rank():
    """THE CONTROL. Without it the check would be measuring `three
    variables from six runs` rather than `a variable that is a function of
    two others`, and every conclusion would be misattributed.

    The only change is that the third quantity is drawn rather than
    derived. Nothing else moves."""
    runs = correlated_runs(6, 0.7)
    rng = random.Random(4471)
    out = []
    for index, (mn, mw) in enumerate(runs):
        out.extend([
            observation(index, "number_average_molar_mass", math.log(mn)),
            observation(index, "weight_average_molar_mass", math.log(mw)),
            observation(index, "dispersity", rng.gauss(0.9, 0.05), uncertainty=0.01),
        ])
    result = sample_covariance(pair_replicates(out).sets[0])
    assert result is not None
    assert result.effective_rank == 3
    assert RANK_DEFICIENT_COVARIANCE not in result.reasons


def test_more_runs_do_not_repair_it():
    """A caller who responds to a deficient covariance by collecting more
    replicates is treating the wrong cause. The relation is between the
    VARIABLES; the number of runs has nothing to do with it."""
    for count in (4, 8, 20):
        pairing = pair_replicates(_polymer_observations(correlated_runs(count, 0.7)))
        result = sample_covariance(pairing.sets[0])
        assert result.effective_rank == 2, f"{count} runs gave rank {result.effective_rank}"
        assert RANK_DEFICIENT_COVARIANCE in result.reasons


def test_the_deficiency_does_not_suppress_the_correlations_that_are_real():
    """A refusal that threw the whole covariance away would lose the
    measurement the vertical exists for. rho between Mn and Mw is still
    recoverable; what is reported is that ONE DIRECTION carries no
    variance, not that the set is unusable."""
    runs = correlated_runs(40, 0.9)
    result = sample_covariance(pair_replicates(_polymer_observations(runs)).sets[0])
    assert RANK_DEFICIENT_COVARIANCE in result.reasons
    rho = result.rho("number_average_molar_mass", "weight_average_molar_mass")
    assert rho is not None and 0.75 < rho < 0.99, rho
