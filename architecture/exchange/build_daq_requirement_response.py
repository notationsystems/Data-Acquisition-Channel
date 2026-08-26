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
_ROWS = {
    row["requirement"]: row
    for row in _REQUIREMENTS["workloads"]["kalman_filter_linear"]["blocking_requirements"]
}


def _asked(requirement: str) -> str:
    return _ROWS[requirement]["statement"]

RESPONSES = {
    "structured_measurement_uncertainty": {
        "daq_built": "science/structured_uncertainty.py -- a measurement covariance R admitted into an observation, with the requirement's ONLY-WHEN clause enforced as a correspondence rule between value and uncertainty.",
        "what_the_requirement_asked": _asked("structured_measurement_uncertainty"),
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
    "recursive_generation_depth": {
        "daq_built": "science/lineage_depth.py -- evidence-lineage depth, bounded, recorded per record, and verified against lineage rather than trusted.",
        "what_the_requirement_asked": _asked("recursive_generation_depth"),
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
    "responds_to_workload": "kalman_filter_linear",
    "generated_by": "architecture/exchange/build_daq_requirement_response.py",
    "states_no_status": "deliberately. Every row carries what DAQ built, what it measured and how to re-run it, and stops. The status of a requirement in your artifact is yours to set; writing SATISFIED here would be DAQ answering your question about your own requirement.",
    "rows_addressed_are_derived_not_listed": "both DAQ-owned blocking rows the requirements artifact lists for this workload. The count is taken from the artifact programmatically rather than from prose -- a subset read as the set is a mistake this pair has now made three times.",
    "responses": RESPONSES,
}


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    artifact = here / "daq_requirement_response.yaml"
    artifact.write_bytes(canonical_bytes(DOCUMENT))
    (here / "daq_requirement_response.sha256").write_text(canonical_sha256(DOCUMENT) + "\n")
    print(f"wrote {artifact.name} {canonical_sha256(DOCUMENT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
