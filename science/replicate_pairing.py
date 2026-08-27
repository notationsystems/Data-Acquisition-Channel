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
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence, Tuple

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
#: A context key that takes a different value on every run, so every run is
#: its own group. Either an acquisition locator leaked into content, or these
#: runs are not replicates. Named rather than decided -- see the docstring.
EVERY_RUN_DIFFERS_IN = "EVERY_RUN_DIFFERS_IN"

#: Keys that describe the MEASUREMENT rather than the conditions it was
#: made under. They travel with the cell and never group.
_PER_CELL_KEYS = ("value", "uncertainty", "uncertainty_kind")
#: Keys that name what was measured rather than the circumstances.
_COLUMN_KEYS = ("variable", "property")


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
    keys = set()
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
        row = []
        for j, column_j in enumerate(columns):
            row.append(sum((a - means[i]) * (b - means[j])
                           for a, b in zip(column_i, column_j)) / (n - 1))
        covariance.append(tuple(row))

    reasons = []
    correlation = []
    for i in range(len(variables)):
        row = []
        for j in range(len(variables)):
            denominator = math.sqrt(covariance[i][i] * covariance[j][j])
            if denominator == 0.0:
                row.append(None)
                if covariance[i][i] == 0.0:
                    reasons.append(DEGENERATE_VARIABLE)
            else:
                row.append(covariance[i][j] / denominator)
        correlation.append(tuple(row))

    return SampleCovariance(
        variables=variables,
        means=means,
        covariance=tuple(covariance),
        correlation=tuple(correlation),
        n_runs=n,
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
