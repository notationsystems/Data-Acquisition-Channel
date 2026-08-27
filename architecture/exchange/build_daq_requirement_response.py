#!/usr/bin/env python3
"""Generates the DAQ requirement-response artifact.

WHAT IT IS FOR. The compute layer's requirements artifact lists rows it
owns the STATUS of. DAQ cannot move a row -- the artifact is theirs and
mirrored read-only here -- but the evidence for moving one is DAQ's to
supply. This artifact is that evidence, content-addressed and paired with
its sidecar so a reader can check it rather than take it.

WHAT IT IS NOT. It states no status. Every row carries what DAQ built,
what it measured, and where a reader can re-run it, and stops. Writing
`SATISFIED` here would be DAQ answering the compute layer's question about
the compute layer's own requirement, which the joint protocol forbids for
the same reason it forbids DAQ electing a workload.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from canonical_yaml import canonical_bytes, canonical_sha256  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))
from epistemics._yaml import loads  # noqa: E402

#: The requirement text is READ FROM THE COUNTERPARTY'S ARTIFACT, never
#: transcribed. The first draft of this file transcribed it and truncated
#: one statement at a semicolon -- the same subset-read-as-the-set error
#: recorded in architecture/proof_integrity.yaml, made while writing the
#: artifact that reports on it. A quotation that can drift is a paraphrase
#: with extra steps.
_REQUIREMENTS = loads(
    (_REPO_ROOT / "architecture" / "exchange" / "scl_requirements.yaml").read_text())

#: THE ROW KEY IS (WORKLOAD, REQUIREMENT), NOT REQUIREMENT.
#:
#: The first version of this file keyed on the requirement name alone and
#: scoped itself to one hardcoded workload. Both halves were wrong and the
#: second hid the first:
#:
#:   * `stable_sample_and_variable_identity` is a row in BOTH least_squares
#:     and pca, with DIFFERENT statement text (274 and 163 characters).
#:     Keyed by name across workloads the two collide, one silently
#:     overwrites the other, and the artifact then quotes one workload's
#:     question while claiming to answer the other's. Measured before this
#:     file was extended, not after it broke.
#:   * scoping to `kalman_filter_linear` meant the collision could not
#:     occur -- so the derivation looked sound while being evaluated over
#:     exactly one partition of a state that has seven.
#:
#: That is the shape a derivation takes when its SCOPE is enumerated even
#: though its CONTENT is derived: correct everywhere it runs, and silent
#: about everywhere it does not. The scope is now the requirements
#: artifact's own partition -- every workload it declares -- and the
#: completeness assertion below is over that partition rather than over a
#: name written here.
_DAQ_ROWS = {
    (workload, row["requirement"]): row
    for workload, entry in _REQUIREMENTS["workloads"].items()
    for row in entry.get("blocking_requirements", ())
    if row["owner"] == "daq"
}


def _asked(workload: str, requirement: str) -> str:
    return _DAQ_ROWS[(workload, requirement)]["statement"]


def _key(workload: str, requirement: str) -> str:
    return f"{workload}::{requirement}"

RESPONSES = {
    _key("kalman_filter_linear", "structured_measurement_uncertainty"): {
        "daq_built": "science/structured_uncertainty.py -- a measurement covariance R admitted into an observation, with the requirement's ONLY-WHEN clause enforced as a correspondence rule between value and uncertainty.",
        "what_the_requirement_asked": _asked("kalman_filter_linear", "structured_measurement_uncertainty"),
        "evidence": [
            "an n-component value with an n-row uncertainty and n component units is admitted",
            "a scalar sigma on a multivariate value is REFUSED as SCALAR_UNCERTAINTY_ON_A_MULTIVARIATE_VALUE -- the ONLY-WHEN clause, enforced rather than advisory",
            "a matrix on a scalar value is REFUSED as STRUCTURED_UNCERTAINTY_ON_A_SCALAR_VALUE. This closed a measured hole: quantity_is_typed ADMITTED a 2x2 uncertainty on a scalar value, because two gates each correct in isolation left the relation between them unowned",
            "an uncertainty of the wrong outer dimension is REFUSED",
            "every leaf of the value and the uncertainty, at any depth, is held to the shared leaf rule",
            "the off-diagonal clause -- 'for a measurement vector it discards the off-diagonal terms that determine how the filter weights components against each other' -- is what the correspondence rule protects. Refusing a scalar sigma on a multivariate value is precisely refusing the discard, so the off-diagonals cannot be silently absent; they are either present in R or the record is refused.",
            "the consequence you recorded -- that R would have to be ASSERTED by the modeller rather than measurement-derived, moving the estimate's confidence from measured to asserted without that being visible -- is addressed at the representation rather than by convention: a measurement-derived R has somewhere to live, so asserting one is now a choice rather than the only option.",
        ],
        "what_daq_deliberately_does_not_check": "numeric entry, rectangular, square, symmetric, positive-semidefinite -- the five your covariance contract states. A ragged R of the right outer length is ADMITTED here, with a test asserting it, so none of the five may be assumed checked upstream.",
        "reproduce": "python -m pytest tests/test_structured_uncertainty.py",
    },
    _key("kalman_filter_linear", "recursive_generation_depth"): {
        "daq_built": "science/lineage_depth.py -- evidence-lineage depth, bounded, recorded per record, and verified against lineage rather than trusted.",
        "what_the_requirement_asked": _asked("kalman_filter_linear", "recursive_generation_depth"),
        "the_status_your_artifact_records_is_stale": "it says vacuously_enforced. DAQ corrected that downward to represented_unenforced on 2026-08-25, because the earlier evidence proved acyclicity rather than boundedness. As of this artifact the status is ENFORCED. Reported, not edited -- the artifact is yours.",
        "evidence": [
            "BOTH CLAUSES now implemented. The rule reads 'derivation from derivation is bounded and the depth is recorded' and was measured to be implemented in neither: nothing was bounded and no depth was recorded.",
            "a recursive computation declares stream_identity, window_or_horizon, initialization_provenance (measured | computed(prior_id)) and lineage_depth -- the first three from your requirement's semantic domain, the fourth being the depth-is-recorded half",
            "depth 0 requires measured initialization AND every input stream measured; nothing else reaches 0",
            "initialization from a computed prior is prior_depth + 1",
            "THE COMPOSITION GUARD: depth is a maximum over BOTH kinds of source. A filter initialized from a fresh measured state while consuming another filter's OUTPUT is depth 1, not 0. An initialization-only reading of the semantic domain calls it grounded, and that rule is implemented in the test suite and shown to do so.",
            "a declared bound exists (MAX_LINEAGE_DEPTH = 3), is enforced, and is recorded as a POLICY rather than a derivation",
            "iteration count is still not lineage depth -- a filter running 10000 iterations over one measured stream is depth 0",
            "a partial declaration is refused rather than read as non-recursive, which is how a recursive result would otherwise pass as an ordinary one",
            "depth carries its contributions, not only its value, because the failure being bounded is silent",
        ],
        "where_depth_lives": "DerivedValue.content. The vendored DerivedValue carries exactly (id, derived_from, method, content, confidence, derived_at) and is never modified, so depth is declared in content and VERIFIED against lineage rather than being a field anyone can set freely.",
        "what_remains_yours": "computation identity is yours and execution identity is STE's. DAQ owns and now enforces the evidence-lineage semantics only.",
        "reproduce": "python -m pytest tests/test_lineage_depth.py tests/test_recursive_lineage_depth.py",
    },
    _key("least_squares", "stable_sample_and_variable_identity"): {
        "daq_built": "science/table.py -- observation_is_table_alignable, an aligned-observation-table gate over an already-admitted observation. Built 2026-08-26 and reported here for the first time; DAQ had not answered this row.",
        "what_the_requirement_asked": _asked("least_squares", "stable_sample_and_variable_identity"),
        "evidence": [
            "a missing sample identity is REFUSED as MISSING_SAMPLE_IDENTITY; a missing variable identity as MISSING_VARIABLE_IDENTITY",
            "THE ROW-POSITION CLAUSE IS ENFORCED BY TYPE, which is the part that matters: an integer sample identity is REFUSED as UNTYPED_SAMPLE_IDENTITY and an integer variable identity as UNTYPED_VARIABLE_IDENTITY. A row ordinal presented as an identity does not pass, whatever it is called.",
            "the identity types are held apart from their presence deliberately: an int sample id and the str form of the same number are DIFFERENT JOIN KEYS, so a partially-typed table splits in two and a fit runs over half its rows with healthy-looking residuals. That is the failure this row's consequence_if_unmet describes, reached by a different route.",
            "a first acquisition path now produces content that passes this gate: daf/extractors/gpc_report.py, five runs of two variables, admissible with zero reasons. Before it, the gate had only ever been applied to constructed observations.",
        ],
        "a_supplementary_check_that_is_an_enumeration_and_is_reported_as_one": "POSITIONAL_IDENTITY_IS_NOT_IDENTITY additionally refuses content carrying positional-looking KEY NAMES. Measured: `row_index` and `position` fire; `row`, `index` and `ordinal` do not. It is a denylist of names, it is not the protection, and it must not be read as one -- the type rule above is what closes the clause. Reported rather than quietly relied on.",
        "reproduce": "python -m pytest tests/test_aligned_observation_table.py tests/test_gpc_acquisition.py",
    },
    _key("pca", "stable_sample_and_variable_identity"): {
        "daq_built": "the same capability. Answered as its own row rather than folded into the least_squares one, because the two rows carry DIFFERENT statement text and a response keyed by requirement name alone would silently answer one workload's question with the other's.",
        "what_the_requirement_asked": _asked("pca", "stable_sample_and_variable_identity"),
        "evidence": [
            "identical mechanism and identical measurements to the least_squares row of this name; nothing workload-specific was built",
            "your statement says both are the multivariate_observation_table modality and are satisfied by the same DAQ-side capability. DAQ confirms the capability is one capability, and answers both rows so neither is left looking unanswered.",
        ],
        "reproduce": "python -m pytest tests/test_aligned_observation_table.py",
    },
    _key("least_squares", "explicit_missing_value_semantics"): {
        "daq_built": "science/table.py -- absence as STRUCTURE rather than as a value, with a closed reason vocabulary.",
        "what_the_requirement_asked": _asked("least_squares", "explicit_missing_value_semantics"),
        "evidence": [
            "absence is expressed by a `value_absence` key naming a reason from a closed set: not_measured, below_detection, above_range, withheld, lost_in_acquisition",
            "a null value with no reason is REFUSED as MISSING_ABSENCE_REASON -- so `absent` cannot be asserted without saying which absence it is",
            "a reason outside the vocabulary is REFUSED as UNKNOWN_ABSENCE_REASON",
            "a value AND an absence together is REFUSED as VALUE_AND_ABSENCE_BOTH_PRESENT",
            "a non-finite value is REFUSED as SENTINEL_ENCODED_ABSENCE, and separately at the acquisition boundary by daf/extractors/_passthrough.py before it can reach an Observation id",
        ],
        "what_daq_deliberately_does_not_check": "AN IN-RANGE SENTINEL. Measured: value = -999.0 and value = 9999 are ADMITTED, with no reason code from any gate. Only NON-FINITE sentinels are caught. Your statement says missing values must not be `encoded as a sentinel number`, and DAQ answers the half it can: absence has a structural representation, so a sentinel is unnecessary, and the sentinels that are type-distinguishable are refused. A magic number inside the valid range of the quantity is indistinguishable from a measurement without domain knowledge DAQ does not have, and nothing here detects one. Do not assume this half closed.",
        "and_the_second_clause_is_not_daqs_to_close": "`or elided by dropping rows` is about what a CONSUMER does with a table, not about what an observation carries. DAQ makes the absent cell representable and refuses the shapes that would hide it; whether a fit silently drops the row is decided where the fit happens.",
        "reproduce": "python -m pytest tests/test_aligned_observation_table.py",
    },
    _key("pca", "commensurable_units_or_explicit_scaling"): {
        "daq_built": "science/admissibility.py -- a unit is required per quantity, and science/structured_uncertainty.py holds component units to correspond with the value's components.",
        "what_the_requirement_asked": _asked("pca", "commensurable_units_or_explicit_scaling"),
        "evidence": [
            "a missing or empty unit is REFUSED as MISSING_UNIT, so a dimensionless payload cannot pass as a quantity",
            "for a multivariate value, a unit list whose length does not match the components is REFUSED as UNITS_DO_NOT_MATCH_COMPONENTS, and a non-string component unit as UNTYPED_COMPONENT_UNIT -- so per-variable units are recorded rather than assumed shared",
        ],
        "what_daq_deliberately_does_not_check": "THE SCALAR UNIT IS NOT TYPED. Measured: unit = 3, unit = 3.5, unit = True, unit = [\"g/mol\"] and unit = {} all PASS quantity_is_typed; only a missing or empty unit fires MISSING_UNIT. This is presence-not-type, the same asymmetry architecture/invariants.yaml already records for the table gate's identities, one field over -- and it is load-bearing here, because a unit that is not a string cannot be compared for commensurability at all. DAQ reports this row as PARTIALLY evidenced for that reason.",
        "and_commensurability_itself_is_not_daqs": "DAQ records the unit per variable. Whether two recorded units are COMMENSURABLE, and whether a scaling choice is asserted as a model parameter, are model decisions at the fit. DAQ supplies the channel; it does not supply the comparison.",
        "reproduce": "python -m pytest tests/test_aligned_observation_table.py tests/test_structured_uncertainty.py",
    },
}

DOCUMENT = {
    "artifact": "daq_requirement_response",
    "extends": "core@1.0.0",
    "owner": "daf",
    # ONE PARTY, TWO NAMES, and neither side noticed for the whole exchange.
    # This repository calls itself `daf` in all six of its own artifacts;
    # the compute layer addresses all eight of its requirement rows to
    # `daq`. Both are internally consistent, so no check inside either
    # repository could see it -- it is only visible when something JOINS on
    # the token, which nothing did until the cross-repository claim check
    # tried to match a response to the row it answers.
    #
    # Declared here rather than fixed by renaming, for two reasons. It is
    # THIS repository's own name, so the compute layer renaming its rows
    # would be one side deciding the other's identity. And both tokens sit
    # in hash-bound artifacts, so a rename is a coordinated reissue for a
    # question that is not yet decided.
    #
    # A two-entry closed vocabulary is one of the cases where a list IS the
    # property -- there are two parties -- so this is a declaration rather
    # than an enumeration standing in for one.
    "also_known_as": "daq, in the compute layer's requirements artifact",
    "the_names_are_one_party": True,
    "paired_artifact": "scl_requirements.yaml, in the compute layer's repository",
    # DERIVED FROM THE ROWS ANSWERED, never written down. The previous
    # version named one workload here as a string, which is what confined
    # the artifact to a single partition while its row derivation looked
    # complete.
    "responds_to_workloads": sorted({key.split("::")[0] for key in RESPONSES}),
    "generated_by": "architecture/exchange/build_daq_requirement_response.py",
    "states_no_status": "deliberately. Every row carries what DAQ built, what it measured and how to re-run it, and stops. The status of a requirement in your artifact is yours to set; writing SATISFIED here would be DAQ answering your question about your own requirement.",
    "rows_addressed_are_derived_not_listed": "every DAQ-owned blocking row the requirements artifact declares, across EVERY workload it declares -- not a workload named here. The counts below are computed from the artifact; a subset read as the set is a mistake this pair has now made three times, and the previous version of this field described a derivation whose scope was nonetheless a hardcoded name.",
    "row_accounting": {
        "daq_owned_rows_upstream": len(_DAQ_ROWS),
        "answered_here": len(RESPONSES),
        "not_answered_and_why": {
            _key(workload, requirement): (
                "SATISFIED upstream before this artifact existed, on evidence the requirements "
                "artifact records against the row itself. Listed so the count reconciles and the "
                "row is visibly considered rather than invisibly skipped."
            )
            for (workload, requirement) in sorted(_DAQ_ROWS)
            if _key(workload, requirement) not in RESPONSES
        },
        "the_assertion": "answered + not_answered == daq_owned_rows_upstream. Every DAQ-owned row is in exactly one of the two.",
        "how_that_assertion_is_actually_held": "BY CONSTRUCTION, not by a check. not_answered_and_why is the derived complement of the answered set within the DAQ-owned rows, so the two cannot fail to reconcile while the derivation stands. The generator's completeness branch is therefore UNREACHABLE today and is recorded as silent rather than as passing; what it guards against is that derivation being replaced by a written-out list, which is the edit that would reintroduce the defect.",
        "what_does_fire": "the stray-row refusal. A response naming a row the requirements artifact does not declare -- a row withdrawn upstream, or a typo -- stops the generator. Detector-proved by planting one.",
    },
    "responses": RESPONSES,
}


def _refuse_if_a_row_is_neither_answered_nor_accounted_for() -> None:
    """The completeness assertion, over the requirements artifact's own
    partition rather than over a scope named in this file.

    This is the check the previous version could not have: with the scope
    fixed to one workload, a DAQ-owned row appearing in any other workload
    was not unanswered, it was invisible."""
    accounted = set(RESPONSES) | set(DOCUMENT["row_accounting"]["not_answered_and_why"])
    upstream = {_key(workload, requirement) for (workload, requirement) in _DAQ_ROWS}

    # THIS BRANCH IS UNREACHABLE TODAY AND IS RECORDED AS SILENT, NOT AS
    # PASSING. `not_answered_and_why` is DERIVED as the complement of
    # RESPONSES within _DAQ_ROWS, so `accounted` always equals `upstream`
    # and `missing` is always empty. Completeness holds BY CONSTRUCTION
    # rather than by this check.
    #
    # It is kept because the change that would break completeness is
    # exactly the change that makes it reachable: replacing the derived
    # complement with a written-out list. Then a row added upstream lands
    # in neither set and this fires. A guard whose whole value is against a
    # future edit is worth keeping and is worth saying so about -- reporting
    # its zero as a measurement would be the vacuous pass this pair files.
    missing = upstream - accounted
    if missing:
        raise SystemExit(
            f"DAQ-owned rows neither answered nor accounted for: {sorted(missing)}. "
            "Answer them or record why not; a row that is in neither set is one nobody looked at."
        )
    stray = accounted - upstream
    if stray:
        raise SystemExit(
            f"rows answered that the requirements artifact does not declare: {sorted(stray)}. "
            "A response to a withdrawn row passes every check that only looks at what was answered."
        )


def main() -> int:
    _refuse_if_a_row_is_neither_answered_nor_accounted_for()
    here = pathlib.Path(__file__).resolve().parent
    artifact = here / "daq_requirement_response.yaml"
    artifact.write_bytes(canonical_bytes(DOCUMENT))
    (here / "daq_requirement_response.sha256").write_text(canonical_sha256(DOCUMENT) + "\n")
    print(f"wrote {artifact.name} {canonical_sha256(DOCUMENT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
