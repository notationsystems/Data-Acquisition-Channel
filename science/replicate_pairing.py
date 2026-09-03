"""Replicate sets, with the run-to-value pairing preserved.

WHY THIS EXISTS. architecture/polymer_acquisition_readiness.yaml measured
that `materials.analysis._group_by_comparison_context` -- the projection
this repository already had -- returns `ComparisonGroup(context, values,
disagreement)` where `values` is a bare tuple of floats. No observation
id, no Record, no run identity travels with a value. So the Mn group and
the Mw group are two independent tuples and nothing pairs the i-th Mn with
the i-th Mw.

A CORRELATION IS EXACTLY A STATEMENT ABOUT THAT PAIRING. The polymer
vertical's open question is rho = corr(ln Mn, ln Mw), which decides the
SIGN of the error a consumer makes on a row carrying a derived-at-source
quantity beside its inputs. It cannot be computed from the projection.

IT IS A MISSING CONSUMER, NOT A MISSING CAPABILITY, and that distinction
is what makes this module small. The raw Observations are content
addressed, retained, and each names its Record. The pairing survives in
the evidence pool and is lost only in the projection. So this reads
Observations and never touches `materials.analysis`.

--------------------------------------------------------------------
WHAT IS A ROW, A COLUMN, A GROUP -- and why, since getting these wrong is
how the projection lost the pairing in the first place. The vendored
Phase 16/17 argument is the right one and is applied here rather than
re-derived:

    THE RECORD IS THE ROW.       An acquisition locator. It identifies
                                 WHICH RUN produced a number and must
                                 never enter the comparison context --
                                 a field unique to each record makes
                                 every observation its own single-member
                                 group and nothing is comparable.
    THE VARIABLE IS THE COLUMN.  Mn and Mw on one run are two columns of
                                 one row, not two members of one group.
    CONDITIONS ARE THE GROUP.    A scientific conditioning variable
                                 belongs in the context: a measurement
                                 under a different calibration is a
                                 measurement of a different quantity.

WHERE THIS DELIBERATELY DIVERGES FROM THE VENDORED GROUPING, stated
rather than done quietly. `_comparison_context` keeps every content key
except `property` and the value key -- which includes `uncertainty`.
Measured: five replicates whose per-run uncertainty differs by 1 g/mol
split into five singleton groups. Here `uncertainty` and
`uncertainty_kind` are CARRIED PER CELL and are not grouping keys,
because a per-run uncertainty is a property OF THE RUN and not a
condition the run was performed under. Nothing is discarded -- the
figures travel with their values -- which is the difference between this
and suppressing them to keep a group intact.

--------------------------------------------------------------------
WHAT IT REFUSES, and why each refusal is a refusal rather than a
silent repair:

    AMBIGUOUS_RUN_IDENTITY        an observation naming zero or several
                                  Records has no single row to occupy,
                                  and picking one would invent a fact
    CONFLICTING_VALUE_FOR_A_RUN   the same variable twice on one Record
                                  is two answers to one question
    RAGGED_REPLICATE_SET          a run missing a variable other runs
                                  carry cannot be paired; dropping it
                                  silently would bias the covariance and
                                  dropping the variable would discard a
                                  measurement
    TOO_FEW_RUNS_FOR_A_COVARIANCE fewer than two runs is not a small
                                  sample, it is no sample -- the same
                                  rule `_disagreement` already applies

DEGENERATE_VARIABLE is reported alongside a covariance rather than
refusing it: a variable that did not move across runs has zero variance,
so its correlations are undefined (0/0) rather than wrong. The set is
still paired and the other correlations are still real.

--------------------------------------------------------------------
EVERY_RUN_DIFFERS_IN, AND WHY IT IS NOT CALLED "RUN ID IN CONTENT".

The polymer acquisition's one irreversible precondition is that each GPC
run carries its own Record with the run identifier OUT of content. Get it
wrong and there is no repair: which run produced which number cannot be
reconstructed afterwards.

MEASURED, on the first version of this module: getting it wrong was
SILENT. A run identifier in content gives every observation its own
comparison context, so five runs become five singleton sets, each
reporting TOO_FEW_RUNS_FOR_A_COVARIANCE -- indistinguishable from a pool
that genuinely holds one run. The exact failure the precondition exists
to prevent produced no refusal at all. A contract that fails silently is
a sentence in a document, which is the shape this repository keeps
finding.

THE DETECTION IS PHASE 16'S OWN RULE, RUN FORWARD: "a field unique to
each record makes every observation its own single-member group." So drop
each context key in turn and see whether the groups merge. If they do,
and that key's values are in bijection with the runs, it is the key
splitting them.

IT IS NAMED AND NOT DIAGNOSED, deliberately. Two different things produce
it and this module cannot tell them apart:

    an acquisition locator leaked into content -- the precondition
        violated, and the data is unusable for a covariance
    a genuine condition that really did change every run -- in which case
        these are NOT REPLICATES, and pooling them would be wrong

Both are things the caller must be told, and neither is this module's
call to make. Calling the code RUN_ID_IN_CONTENT would assert the first
and be wrong whenever the second holds -- the same overclaim this project
has filed before. What is certain is the observable, and the observable
is what it is named after.
"""

from __future__ import annotations

import math
import pathlib
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from epistemics import _yaml

#: This repository's root, from this file's location -- so the published
#: constant is read from the tree the module is running in rather than
#: from a configured path.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: An observation that names no single Record has no row to occupy.
AMBIGUOUS_RUN_IDENTITY = "AMBIGUOUS_RUN_IDENTITY"
#: The same variable measured twice on one run.
CONFLICTING_VALUE_FOR_A_RUN = "CONFLICTING_VALUE_FOR_A_RUN"
#: Runs that do not all carry the same variables cannot be paired.
RAGGED_REPLICATE_SET = "RAGGED_REPLICATE_SET"
#: A covariance needs at least two runs.
TOO_FEW_RUNS_FOR_A_COVARIANCE = "TOO_FEW_RUNS_FOR_A_COVARIANCE"
#: A variable with zero sample variance: correlations against it are 0/0.
DEGENERATE_VARIABLE = "DEGENERATE_VARIABLE"
#: The covariance is SINGULAR -- some direction in variable space carries no
#: variance at all, because the variables are not independent measurements.
#:
#: WHY THIS IS NOT A DETAIL, and why it is reported rather than left to the
#: consumer to trip over. A covariance is handed onward to be WHITENED: the
#: compute layer's least_squares takes only a diagonal, so a caller with a
#: correlated problem factors Sigma = L L^T and fits the whitened system,
#: which is exactly the generalized least-squares estimate -- for a
#: POSITIVE DEFINITE Sigma.
#:
#: A sample covariance over variables carrying an exact linear relation is
#: positive SEMI-definite by construction, and the compute layer measured
#: what happens then: over 2000 five-run replicate sets of one physical
#: situation, a plain Cholesky accepted 828 and refused 1172. The outcome
#: is decided by where the last pivot lands relative to zero. Two times in
#: five it succeeds and the deficient row of the whitened problem is made
#: entirely of rounding noise, small enough to look harmless because
#: numerator and denominator vanish together.
#:
#: The polymer row is exactly this case and it is not exotic: a GPC report
#: carries Mn, Mw and a dispersity that IS Mw/Mn, so in logs the third
#: variable is identically the second minus the first. Any instrument that
#: reports a derived quantity beside its inputs produces it.
#:
#: THE COMPUTE LAYER'S REQUIREMENT, QUOTED VERBATIM from
#: architecture/exchange/scl_requirements.yaml, workloads.least_squares,
#: blocking_requirements. Verbatim rather than summarised because a
#: paraphrase is where a softened obligation gets in, and because
#: tests/test_aligned_observation_table.py checks that every requirement
#: this repository is told about is written down here word for word:
#:
#:     science/replicate_pairing.py now measures a covariance from paired
#:     replicate runs, and least_squares takes only a diagonal, so the
#:     caller whitens with a Cholesky factor. That identity holds for a
#:     KNOWN Sigma. A SAMPLE covariance over variables carrying an exact
#:     linear relation is positive SEMI-definite by construction, and the
#:     Cholesky then has no defined result. The obligation is to
#:     establish definiteness with the SAME rule the operation applies to
#:     the design -- a pivot at or below rank_tolerance times the largest
#:     pivot is zero -- and to drop the deficient direction deliberately
#:     rather than let it survive.
RANK_DEFICIENT_COVARIANCE = "RANK_DEFICIENT_COVARIANCE"

#: A replicate set carrying ONE variable. The covariance is a 1x1 matrix
#: and the correlation is 1.0 -- structurally, not measurably: a variable
#: correlates with itself whatever the data says. Named because a second
#: real source produced exactly this and the result came back with ZERO
#: reasons, which reads as a computed correlation. A number that is true
#: by construction and a number that was measured must not be
#: indistinguishable in the same field; that is the shape recorded in
#: architecture/admission_reachability.yaml as silence mistaken for
#: cleanliness.
TOO_FEW_VARIABLES_FOR_A_CORRELATION = "TOO_FEW_VARIABLES_FOR_A_CORRELATION"
#: A context key that takes a different value on every run, so every run is
#: its own group. Either an acquisition locator leaked into content, or these
#: runs are not replicates. Named rather than decided -- see the docstring.
EVERY_RUN_DIFFERS_IN = "EVERY_RUN_DIFFERS_IN"

#: Keys that describe the MEASUREMENT rather than the conditions it was
#: made under. They travel with the cell and never group.
_PER_CELL_KEYS = ("value", "uncertainty", "uncertainty_kind")
#: Keys that name what was measured rather than the circumstances.
# ONE KEY, AFTER THE RECONCILIATION. This read `("variable", "property")`
# and preferred `variable`, which made it a reader that accepted two
# encodings of one meaning -- the shape this pair removes at the writer.
# `property` is the variable identity (see science/table.py's note); the
# retired synonym is refused by observation_is_table_alignable, which is
# the gate that owns variable identity. Not defended against a second time
# here: a stray `variable` reaching this consumer becomes a context key
# and splits the replicate set, which is loud, and tolerating it here
# would make the retirement half-happen.
_COLUMN_KEYS = ("property",)


@dataclass(frozen=True)
class Cell:
    """One variable measured on one run."""

    value: float
    uncertainty: Optional[float]
    uncertainty_kind: Optional[str]
    observation_id: str


@dataclass(frozen=True)
class ReplicateSet:
    """Runs paired with the values they produced, in one comparison context.

    `rows` is run-major: rows[i][j] is the cell for run `run_ids[i]` and
    variable `variables[j]`. That the pairing is expressible as an index
    is the whole content of this module.
    """

    context: Tuple[Tuple[str, object], ...]
    run_ids: Tuple[str, ...]
    variables: Tuple[str, ...]
    rows: Tuple[Tuple[Cell, ...], ...]

    def column(self, variable: str) -> Tuple[float, ...]:
        index = self.variables.index(variable)
        return tuple(row[index].value for row in self.rows)

    def paired(self, first: str, second: str) -> Tuple[Tuple[float, float], ...]:
        """The pairs the projection could not express."""
        i, j = self.variables.index(first), self.variables.index(second)
        return tuple((row[i].value, row[j].value) for row in self.rows)


@dataclass(frozen=True)
class SampleCovariance:
    """The sample covariance over a replicate set, and what it could not say."""

    variables: Tuple[str, ...]
    means: Tuple[float, ...]
    covariance: Tuple[Tuple[float, ...], ...]
    correlation: Tuple[Tuple[Optional[float], ...], ...]
    n_runs: int
    #: Effective rank under the compute layer's published cutoff, and the
    #: cutoff used. The tolerance travels WITH the rank because a rank is
    #: meaningless without the threshold that produced it -- the same
    #: reason a measurement carries its uncertainty kind.
    effective_rank: int
    rank_tolerance: float
    reasons: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(self.reasons)))

    def rho(self, first: str, second: str) -> Optional[float]:
        i, j = self.variables.index(first), self.variables.index(second)
        return self.correlation[i][j]


@dataclass(frozen=True)
class Pairing:
    """Every replicate set recoverable from a pool, and every refusal."""

    sets: Tuple[ReplicateSet, ...]
    refusals: Tuple[Tuple[str, str], ...]   # (code, what it was about)

    def __post_init__(self) -> None:
        object.__setattr__(self, "refusals", tuple(sorted(self.refusals)))


def _context_of(content: Mapping[str, object]) -> Tuple[Tuple[str, object], ...]:
    """Everything that conditions the measurement.

    Not the value, not the per-run uncertainty figures, not the variable
    name, and NOT the run -- which is carried as the row index instead.
    """
    excluded = set(_PER_CELL_KEYS) | set(_COLUMN_KEYS)
    return tuple(sorted(
        (key, value) for key, value in content.items() if key not in excluded))


def _variable_of(content: Mapping[str, object]) -> Optional[str]:
    for key in _COLUMN_KEYS:
        name = content.get(key)
        if isinstance(name, str) and name:
            return name
    return None


def pair_replicates(observations: Iterable[object]) -> Pairing:
    """Recover run-to-value pairing from observations.

    Each observation must name exactly one Record -- that Record is its
    run. Observations sharing a comparison context form one replicate set;
    within it, each run is a row and each variable a column.
    """
    grouped: dict = {}
    refusals = []

    for observation in observations:
        record_ids = tuple(getattr(observation, "record_ids", ()) or ())
        content = getattr(observation, "content", None)
        identity = str(getattr(observation, "id", "<no id>"))
        if len(record_ids) != 1:
            refusals.append((AMBIGUOUS_RUN_IDENTITY, identity))
            continue
        if not isinstance(content, Mapping):
            refusals.append((AMBIGUOUS_RUN_IDENTITY, identity))
            continue
        variable = _variable_of(content)
        value = content.get("value")
        if variable is None or not isinstance(value, (int, float)) or isinstance(value, bool):
            # Not a paired quantity at all; nothing to pair, nothing to refuse.
            continue

        context = _context_of(content)
        run = record_ids[0]
        bucket = grouped.setdefault(context, {})
        row = bucket.setdefault(run, {})
        if variable in row:
            refusals.append((CONFLICTING_VALUE_FOR_A_RUN, f"{run}:{variable}"))
            continue
        uncertainty = content.get("uncertainty")
        row[variable] = Cell(
            value=float(value),
            uncertainty=float(uncertainty) if isinstance(uncertainty, (int, float))
            and not isinstance(uncertainty, bool) else None,
            uncertainty_kind=content.get("uncertainty_kind")
            if isinstance(content.get("uncertainty_kind"), str) else None,
            observation_id=identity,
        )

    sets = []
    for context, runs in grouped.items():
        variable_sets = {frozenset(row) for row in runs.values()}
        if len(variable_sets) != 1:
            refusals.append((RAGGED_REPLICATE_SET, repr(context)))
            continue
        variables = tuple(sorted(next(iter(variable_sets))))
        run_ids = tuple(sorted(runs))
        sets.append(ReplicateSet(
            context=context,
            run_ids=run_ids,
            variables=variables,
            rows=tuple(tuple(runs[run][variable] for variable in variables)
                       for run in run_ids),
        ))

    sets.sort(key=lambda s: repr(s.context))
    refusals.extend(_keys_that_split_every_run(grouped))
    return Pairing(sets=tuple(sets), refusals=tuple(refusals))


def _keys_that_split_every_run(grouped: Mapping) -> Sequence[Tuple[str, str]]:
    """Context keys whose removal merges the groups AND which take a
    distinct value on every run.

    Phase 16's rule run forward. Only meaningful when the grouping
    actually produced singletons: with one group there is nothing split,
    and with genuine multi-run groups the split is doing real work.
    """
    if len(grouped) < 2 or not any(len(runs) == 1 for runs in grouped.values()):
        return ()

    observed = [(dict(context), run) for context, runs in grouped.items() for run in runs]
    keys: Set[str] = set()
    for context, _ in observed:
        keys.update(context)

    found = []
    for key in sorted(keys):
        if not all(key in context for context, _ in observed):
            continue
        merged = {tuple(sorted((k, v) for k, v in context.items() if k != key))
                  for context, _ in observed}
        if len(merged) >= len(grouped):
            continue                      # dropping it merges nothing
        by_run = {run: context.get(key) for context, run in observed}
        try:
            distinct = len(set(by_run.values()))
        except TypeError:                 # unhashable value: cannot be a locator
            continue
        if distinct == len(by_run) and distinct > 1:
            found.append((EVERY_RUN_DIFFERS_IN, key))
    return tuple(found)


def published_rank_tolerance() -> float:
    """The compute layer's cutoff, READ FROM ITS PUBLISHED ARTIFACT.

    NOT TYPED HERE. `1e-12` is a value the compute layer owns and can
    change; a copy of it in this module is a second encoding of one fact,
    and the two would stop agreeing exactly when the compute layer moved
    it -- silently, since nothing compares a number in this file to a
    number in that header.

    architecture/exchange/scl_requirements.yaml carries it under
    `published_constants`, parsed there from
    native/include/scl/least_squares.hpp by that repository's generator.
    So the chain is: header -> generator -> artifact -> here, with a
    digest at the artifact and a mirror check across the pair. This is a
    JOIN, and the artifact moving is what makes it visible.

    Raises rather than defaulting. A cutoff quietly standing in for the
    counterparty's would be the same defect as copying it, with the
    additional property that nobody could see it had happened.
    """
    artifact = (_REPO_ROOT / "architecture" / "exchange" / "scl_requirements.yaml")
    document = _yaml.loads(artifact.read_text())
    constants = document.get("published_constants")
    if not constants or "least_squares_rank_tolerance_default" not in constants:
        raise LookupError(
            "scl_requirements.yaml publishes no least_squares rank tolerance; "
            "the covariance rank cannot be established by the compute layer's "
            "own rule, and this module does not invent one"
        )
    return float(constants["least_squares_rank_tolerance_default"])


def covariance_rank(matrix, rank_tolerance: float) -> int:
    """Effective rank by pivoted Cholesky, under the compute layer's rule.

    `sigma_j <= tol * sigma_max` becomes `pivot <= tol * largest_pivot`.
    They are the same rule about the same sort of object -- a spectrum of
    non-negative numbers whose small end is indistinguishable from zero --
    and using the counterparty's is what makes the two sides agree about
    which directions exist.

    Written without refusing on a non-positive pivot, deliberately: the
    whole finding is that refusing there is a coin flip. Every pivot is
    computed and then classified, so the answer does not depend on the
    sign a rounding error happened to produce.
    """
    size = len(matrix)
    if size == 0:
        return 0
    factor = [[0.0] * size for _ in range(size)]
    pivots: List[float] = []
    for i in range(size):
        for j in range(i + 1):
            carried = sum(factor[i][k] * factor[j][k] for k in range(j))
            if i == j:
                pivot = matrix[i][i] - carried
                pivots.append(pivot)
                factor[i][j] = math.sqrt(pivot) if pivot > 0.0 else 0.0
            else:
                factor[i][j] = (
                    (matrix[i][j] - carried) / factor[j][j] if factor[j][j] > 0.0 else 0.0
                )
    largest = max(pivots)
    if largest <= 0.0:
        return 0
    return sum(1 for pivot in pivots if pivot > rank_tolerance * largest)


def sample_covariance(replicates: ReplicateSet) -> Optional[SampleCovariance]:
    """The covariance the pairing makes computable.

    Returns None when there are fewer than two runs -- the same rule the
    vendored disagreement statistic already applies, and for the same
    reason: one value is not a sample.
    """
    n = len(replicates.run_ids)
    if n < 2:
        return None

    variables = replicates.variables
    columns = [replicates.column(variable) for variable in variables]
    means = tuple(sum(column) / n for column in columns)

    covariance = []
    for i, column_i in enumerate(columns):
        covariance_row: List[float] = []
        for j, column_j in enumerate(columns):
            covariance_row.append(sum((a - means[i]) * (b - means[j])
                                      for a, b in zip(column_i, column_j)) / (n - 1))
        covariance.append(tuple(covariance_row))

    reasons = []
    if len(variables) < 2:
        # The set is still returned -- the means and the 1x1 covariance are
        # real and a caller may want them -- but the correlation it carries
        # is 1.0 by construction and the reason says so.
        reasons.append(TOO_FEW_VARIABLES_FOR_A_CORRELATION)
    correlation = []
    for i in range(len(variables)):
        # Optional[float]: a degenerate variable has no correlation to report,
        # and None says so rather than a number standing in for absence.
        correlation_row: List[Optional[float]] = []
        for j in range(len(variables)):
            denominator = math.sqrt(covariance[i][i] * covariance[j][j])
            if denominator == 0.0:
                correlation_row.append(None)
                if covariance[i][i] == 0.0:
                    reasons.append(DEGENERATE_VARIABLE)
            else:
                correlation_row.append(covariance[i][j] / denominator)
        correlation.append(tuple(correlation_row))

    tolerance = published_rank_tolerance()
    rank = covariance_rank(covariance, tolerance)
    if rank < len(variables):
        reasons.append(RANK_DEFICIENT_COVARIANCE)

    return SampleCovariance(
        variables=variables,
        means=means,
        covariance=tuple(covariance),
        correlation=tuple(correlation),
        n_runs=n,
        effective_rank=rank,
        rank_tolerance=tolerance,
        reasons=tuple(set(reasons)),
    )


@dataclass(frozen=True)
class PairedResult:
    """A replicate set, its covariance if one exists, and why if it does not."""

    replicates: ReplicateSet
    covariance: Optional[SampleCovariance]
    reasons: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(self.reasons)))


def covariance_of(observations: Iterable[object]) -> Tuple[PairedResult, ...]:
    """Pair, then compute, keeping the two separable.

    The pairing is the structural result and the covariance is a function
    of it. Anyone wanting a different statistic replaces the second half
    without touching the first.

    A set too small to have a covariance comes back with the reason rather
    than a bare None. `sample_covariance` still returns None on its own --
    that mirrors the vendored disagreement statistic and is the honest
    answer to "what is the covariance" -- but a caller asking this
    function is asking about a POOL, and "there is none" without "because
    one run is not a sample" is the silence this repository keeps finding.
    """
    results = []
    for replicates in pair_replicates(observations).sets:
        covariance = sample_covariance(replicates)
        reasons = list(covariance.reasons) if covariance is not None else [
            TOO_FEW_RUNS_FOR_A_COVARIANCE]
        results.append(PairedResult(replicates=replicates, covariance=covariance,
                                    reasons=tuple(reasons)))
    return tuple(results)
