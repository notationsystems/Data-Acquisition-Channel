"""Generates `daq_capabilities.yaml` -- DAF's half of the two-artifact
exchange, paired with the compute layer's `scl_requirements.yaml`.

MEASURED FACTS AND CAPABILITIES ONLY. This artifact contains no workload
selection: an artifact that ranked or recommended would be making the
joint decision on the decision record's behalf. Every capability row
carries a traced evidence pointer, and every claim here was measured
against this repository's real gate, real extractors and real fixtures
rather than read off its documentation.

Canonicalized per the exchange canonicalization spec, using the
byte-identical `canonical_yaml.py` vendored from the compute layer's
repository. Both copies produce the same digest for the shared
`canonicalization_fixture.yaml`, which is how the two repositories
confirm they agree on the encoding before either artifact's hash means
anything.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from canonical_yaml import canonical_bytes, canonical_sha256  # noqa: E402

_EXISTING = "EXISTING"
_REUSABLE = "REUSABLE"
_SMALL_EXTENSION = "SMALL EXTENSION"
_MISSING = "MISSING"
_OUT_OF_SCOPE = "OUT OF SCOPE"


# ===================================================== capability inventory

CAPABILITIES = {
    "ordered_scalar_sequence": {
        "classification": _EXISTING,
        "evidence": "daf/extractors/noaa_water_level_measurements.py produces one Observation per reading with a scalar `value`, a `measurement_time` and a `unit`. Measured on the real 240-reading fixture tests/fixtures/noaa_live_8454000_20240115_mllw.json.",
        "note": "the only modality this repository supplies from a live external scientific source today",
    },
    "uniform_sample_spacing": {
        "classification": _SMALL_EXTENSION,
        "evidence": "measured on the real NOAA fixture: all 239 inter-sample gaps are exactly 360.0 s, so the series IS uniform. But nothing computes, checks or records that fact -- uniformity holds by observation, not by contract.",
        "note": "see unresolved_edges.uniformity_is_unchecked",
    },
    "per_sample_timestamps": {
        "classification": _EXISTING,
        "evidence": "measurement_time is carried in Observation.content for every NOAA reading, deliberately (daf/extractors/noaa_water_level_measurements.py's own field classification)",
    },
    "scalar_uncertainty": {
        "classification": _EXISTING,
        "evidence": "architecture/uncertainty_provenance_reachability.yaml determines noaa_water_level_sigma as supported_uncertainty; `sigma` is present on all 240 real readings and surfaces as uncertainty/uncertainty_kind",
    },
    "uncertainty_kind_vocabulary": {
        "classification": _EXISTING,
        "evidence": "science/admissibility.py UNCERTAINTY_KINDS = (stated, estimated, propagated, absent); `absent` is a declarable answer distinct from the field being missing",
    },
    "structured_uncertainty_covariance": {
        "classification": _MISSING,
        "evidence": "architecture/nonscalar_quantity.yaml; measured in tests/test_nonscalar_quantity_frontier.py. A covariance is not refused -- it is SILENTLY ADMITTED by the gate and fails later in materials.analysis as TypeError: unhashable type: 'list'.",
        "note": "an unchecked hole rather than a declared gap; see nonscalar_quantity_finding",
    },
    "multivariate_observation_value": {
        "classification": _MISSING,
        "evidence": "science/admissibility.py quantity_is_typed type-checks `value` with isinstance(value, (int, float)); a vector is refused as UNTYPED_QUANTITY in any container. Measured in tests/test_nonscalar_quantity_frontier.py.",
    },
    "stable_sample_identity": {
        "classification": _EXISTING,
        "evidence": "every Observation carries a content-addressed id (evidence.identity.content_hash); observation identity is one of the six distinct identities architecture/execution_record.yaml separation.rule names",
    },
    "stable_variable_identity": {
        "classification": _MISSING,
        "evidence": "no observation-table or column concept exists. A single Observation carries one `property` name and one scalar `value`; nothing names a variable ACROSS observations in a way that would let a table be reassembled.",
    },
    "aligned_observation_table": {
        "classification": _MISSING,
        "evidence": "no adapter, extractor or storage type produces or represents a joinable multi-variable table. Every extractor emits independent Observations.",
    },
    "explicit_missing_value_semantics": {
        "classification": _MISSING,
        "evidence": "content values are scalars with no absent representation. The uncertainty channel has `absent` as a declarable kind, but `value` has no counterpart -- a missing measurement is an absent Observation, not a present Observation with an absent value.",
        "note": "the absent-vs-omitted distinction exists for uncertainty and does not generalize to value",
    },
    "units_per_variable": {
        "classification": _EXISTING,
        "evidence": "`unit` is required by quantity_is_typed and is refused as MISSING_UNIT when absent; carried per Observation",
        "note": "one unit per scalar quantity. What `unit` means for a vector-valued quantity is an open semantic question in architecture/nonscalar_quantity.yaml",
    },
    "measurement_conditions": {
        "classification": _EXISTING,
        "evidence": "architecture/condition_representation.yaml; conditions=FrozenMapping({'datum': ...}) on NOAA readings, required non-empty by no_context_free_property",
    },
    "method_provenance": {
        "classification": _MISSING,
        "evidence": "architecture/method_provenance_reachability.yaml. MISSING_METHOD is the one dimension no phase has resolved for NOAA: CO-OPS does not report, per reading, which sensor or algorithm produced a value, and inventing one was rejected.",
        "note": "measured consequence: all 240 real NOAA readings remain inadmissible for canonical assertion on method alone",
    },
    "execution_record": {
        "classification": _EXISTING,
        "evidence": "daf/execution/record.py, architecture/execution_record.yaml, scope daf_acquisition_only, two-hash identity discipline",
    },
    "evidence_class_assignment": {
        "classification": _EXISTING,
        "evidence": "epistemics/evidence_class.py; class_assigned_at_ingest is an enforced invariant",
    },
    "generation_depth_tracking": {
        "classification": _MISSING,
        "evidence": "architecture/recursive_depth.yaml. `generation_depth` appears nowhere in source; DerivedValue has no depth field; ancestry_of returns a flat set union that discards the level each node was reached at. The invariant's status was CORRECTED to represented_unenforced -- its former vacuously_enforced evidence argued only that a derivation CYCLE is unconstructible, which is true and does not support the rule: acyclicity is not boundedness.",
    },
    "physical_actuation": {
        "classification": _OUT_OF_SCOPE,
        "evidence": "no actuation authority boundary exists anywhere in this repository. Acquisition observes; it does not intervene.",
        "note": "matches the compute layer's own recorded position on pid_controller",
    },
    "model_execution": {
        "classification": _OUT_OF_SCOPE,
        "evidence": "architecture/execution_record.yaml excluded_fields.model_binding: no model execution occurs in this repository",
    },
}


# ============================== answers to the requirement rows received
#
# The compute layer's artifact raises blocking_requirements naming an
# owner. Every row owned by `daq` is answered here, so the two artifacts
# form an exchange rather than two monologues. A row is answered with a
# measured status, never with an intention.

REQUIREMENT_RESPONSES = {
    "ordered_scalar_sequence": {
        "raised_by": "scl_requirements.yaml workloads.fourier_transform_1d",
        "daf_status": "SATISFIED",
        "measured_basis": "daf/extractors/noaa_water_level_measurements.py supplies exactly this shape from a live external source; 240 real readings measured",
        "caveat": "none for the modality itself",
    },
    "annotating_sample_spacing": {
        "raised_by": "scl_requirements.yaml workloads.fourier_transform_1d",
        "daf_status": "SATISFIED_WITH_A_SHAPE_MISMATCH",
        "measured_basis": "DAF carries per-sample `measurement_time`, and the real NOAA series is uniform at 360.0 s across all 239 gaps.",
        "caveat": "DAF supplies TIMESTAMPS; the compute layer's transform accepts ONE optional scalar spacing. Nothing converts between them and nothing establishes that a series is uniform enough for a single spacing to be honest. See unresolved_edges.uniformity_is_unchecked -- this is a real edge between the two contracts, not a defect in either.",
    },
    "structured_measurement_uncertainty": {
        "raised_by": "scl_requirements.yaml workloads.kalman_filter_linear",
        "daf_status": "UNSATISFIED",
        "measured_basis": "architecture/nonscalar_quantity.yaml; a covariance is silently admitted and breaks the comparison consumer",
        "caveat": "the existing uncertainty_provenance_reachability verdict `unsupported_uncertainty` already exists for exactly this situation -- genuine uncertainty semantics the vocabulary cannot represent without a shared, cross-source extension. Nothing routes a covariance to that verdict today because nothing refuses it.",
    },
    "recursive_generation_depth": {
        "raised_by": "scl_requirements.yaml workloads.kalman_filter_linear",
        "daf_status": "UNSATISFIED",
        "measured_basis": "architecture/recursive_depth.yaml; generation_depth_bounded has no implementation and an empty domain. Its status has since been corrected from vacuously_enforced to represented_unenforced, because the former evidence proved acyclicity rather than boundedness.",
        "caveat": "routed as write-it-correctly-first, and determined NOT to be a bend provided the rule is authored before the first recursive result exists. The proposed rule is recorded as offered, not adopted.",
    },
    "stable_sample_and_variable_identity": {
        "raised_by": "scl_requirements.yaml workloads.least_squares and workloads.pca",
        "daf_status": "PARTIALLY_SATISFIED",
        "measured_basis": "sample identity EXISTS (content-addressed Observation ids); variable identity across observations does NOT, and no aligned-table representation exists",
        "caveat": "the two halves of this row have different answers, which the row as raised did not anticipate. Sample identity is solved; the table is not.",
    },
    "explicit_missing_value_semantics": {
        "raised_by": "scl_requirements.yaml workloads.least_squares",
        "daf_status": "UNSATISFIED",
        "measured_basis": "no absent representation exists for `value`; a missing measurement is an absent Observation, not a present one carrying an absence",
        "caveat": "the uncertainty channel HAS this distinction (uncertainty_kind=absent) and it does not generalize to value. The pattern exists in one field and not the other.",
    },
    "commensurable_units_or_explicit_scaling": {
        "raised_by": "scl_requirements.yaml workloads.pca",
        "daf_status": "PARTIALLY_SATISFIED",
        "measured_basis": "`unit` is required per Observation and refused as MISSING_UNIT when absent, so units are recorded. What does NOT exist is any commensurability relation between two units, or any scaling decision representation.",
        "caveat": "recording a unit and being able to compare two units are different capabilities; only the first exists",
    },
}


# ============================================================== findings

NONSCALAR_QUANTITY_FINDING = {
    "summary": "multivariate value and structured uncertainty are ONE extension, not two",
    "multivariate_value": {
        "representable": False,
        "failure_layer": "admissibility_gate",
        "visibility": "loud and early -- refused as UNTYPED_QUANTITY, so nothing downstream is ever handed one",
    },
    "structured_uncertainty": {
        "representable": False,
        "failure_layer": "comparison_consumer",
        "visibility": "silent and late -- ADMITTED by the gate with a stable content_hash, failing only in materials.analysis as TypeError: unhashable type: 'list'",
    },
    "why_one_extension": "relaxing the multivariate type check ON ITS OWN converts the structured-uncertainty failure from a loud gate refusal into a silent late TypeError, because a vector value is a Sequence and meets the same unhashable consumer a covariance meets. Closing the visible half first makes the invisible half worse, so neither can be closed alone.",
    "measured_not_inferred": "tests/test_nonscalar_quantity_frontier.py::test_admitting_a_vector_value_alone_would_widen_the_hole",
    "was_the_hole_ever_reached": {
        "answer": "no -- the repair is forward-only",
        "measured_basis": "exactly one extractor emits `uncertainty` at all (noaa_water_level_measurements.py) and it emits sigma, a scalar parsed by _optional_float. No committed fixture carries a non-scalar uncertainty. So no covariance-bearing Observation has ever been content-addressed, and nothing downstream ever consumed such a hash.",
        "why_it_was_asked": "a covariance that receives a stable content_hash before dying at the comparison layer has already been TREATED AS IDENTIFIED. Had one ever been referenced, repair would have had to reach backwards as well as forwards.",
        "but_unreached_is_not_unreachable": "daf/extractors/graph_dataset.py consumes entities/relations as structure and passes EVERY other key into Observation.content unmodified, by design. A source record declaring a covariance would be carried through verbatim, admitted, and content-addressed. The hole is closed today by what sources happen to send, not by any check -- the same extractor and the same mechanism as the Phase 35 verbatim-pass-through finding for `conditions`, in a different field.",
        "enforcement": "tests/test_nonscalar_quantity_frontier.py::test_no_extractor_emits_a_nonscalar_uncertainty, ::test_no_committed_fixture_carries_a_nonscalar_uncertainty, ::test_but_the_pass_through_extractor_would_carry_one_verbatim",
    },
    "the_fix_must_also_tighten_the_pass_through": {
        "finding": "daf/extractors/graph_dataset.py passes every non-structural key into Observation.content unmodified, and daf/extractors/local_dataset.py passes the ENTIRE parsed JSON object through with no structural extraction at all. Neither inspects a value's shape.",
        "consequence_for_scope": "the exposure is not bounded by what extractors currently emit. Adding covariance SUPPORT while leaving the pass-through open fixes the shape that was named and leaves the route open for the next one, which would again be admitted, again receive a stable id, and again fail only at the comparison layer.",
        "precedent": "not hypothetical -- the Phase 35 finding is the same route producing a plain unhashable dict for a declared `conditions` object.",
        "requirement": "a structured-uncertainty extension must tighten the verbatim route as well as add representation, so the contract binds shapes nobody wrote an extractor for.",
        "not_decided_here": "whether tightening means validating content shapes at the extraction boundary, refusing unknown non-scalar shapes, or wrapping them on the way in. That belongs to whoever builds the extension; this records that the pass-through is IN SCOPE for it.",
        "enforcement": "tests/test_nonscalar_quantity_frontier.py::test_two_extractors_pass_arbitrary_content_through_verbatim",
    },
    "which_half_must_lead": {
        "answer": "the structured-uncertainty half",
        "reason": "it is the silent one. Closing the multivariate half first converts the uncertainty failure from a loud gate refusal into a silent late TypeError, so the visible half cannot go first without making the invisible half worse. Ordering within a single extension, not two extensions.",
    },
    "shared_constraint_surface": "any non-scalar quantity must satisfy content_hash (JSON-serializable), materials.analysis (natively hashable) and serialization round-trip (reconstructed value indistinguishable from constructed) AT ONCE. The Mapping half of this surface was solved once already, by FrozenMapping in Phase 34; the Sequence half has no counterpart and freeze_nested_mappings deliberately does not recurse into lists.",
    "still_open_after_a_container_fix": [
        "the unit of a vector-valued quantity",
        "dimensional agreement between a value and its covariance",
        "whether uncertainty_kind's four values mean the same thing for a matrix as for a scalar",
        "component identity, so component order does not become load-bearing",
        "per-component absence",
    ],
    "detail": "architecture/nonscalar_quantity.yaml",
}

EXECUTION_RECORD_RESOLUTION = {
    "status": "DECIDED",
    "decided_by": "daf",
    "raised_by": "scl_requirements.yaml daq_execution_record_finding, correctly raised and left unresolved there",
    "adopted_shape": "discriminated kind with a shared core",
    "shared_core_is_the_intersection": True,
    "shared_core": [
        "id", "runtime_id", "started_at", "finished_at", "status",
        "input_fingerprint", "output_fingerprint", "error", "parent_execution_id",
        "content_digest",
    ],
    "acquisition_only": [
        "acquisition_operation_id", "plan_id", "source_id", "adapter_id",
        "adapter_version", "outcome", "artifact_ids", "version_ids",
        "admission_failure_count",
    ],
    "computation_only": [
        "computation_request_id", "backend", "backend_version", "hardware", "seed",
        "verification_status", "computation_identity",
    ],
    "refused_merges": "adapter_version/backend_version, outcome/verification_status and output_fingerprint/computation_identity are analogies rather than identities and were deliberately NOT unified; unifying any of them would change what content_digest covers in exchange for a word",
    "core_membership_rule": {
        "requires_both": ["present_in_every_kind", "identical_semantics_across_kinds"],
        "comparability_test": "a consumer must be able to compare the field across kinds WITHOUT KNOWING which kind it holds, and get a right answer",
        "on_presence_without_semantic_agreement": "move to the per-kind branches, with DIFFERENT NAMES if the meanings differ -- a shared name across differing meanings is the invitation to compare that the rule exists to remove",
        "why_the_first_version_was_insufficient": "it tested presence in both kinds and nothing else. That is how the junk drawer forms: a field present in both and meaning different things in each passes, lands in the core, then answers correctly for one kind and silently wrongly for the other. No error, no type failure -- a wrong equality.",
        "worked_case_operation_id": {
            "passed": "present_in_every_kind",
            "failed": "identical_semantics_across_kinds",
            "the_disagreement": "DAF's operation_id is H(plan_id, source_id, parameters, mode) and deliberately EXCLUDES the adapter, because a coordinate is never an identity here. The compute layer's request identity INCLUDES the backend, so the same mathematics on a different backend is a different request there. BOTH ARE RIGHT FOR THEIR DOMAIN, which is what makes it dangerous -- there is no error on either side to correct.",
            "consequence_if_it_had_stayed": "a shared core CONTAINING this field is worse than one without it, because the core is what promises comparability.",
            "resolution": "REMOVED from the core. Split into acquisition_operation_id and computation_request_id -- two names, because two meanings.",
            "why_not_keep_it_with_a_constraint": "an earlier revision kept it in the core and required implementation-independence of every kind. That imposes DAF's semantics on the compute layer's own identity model to preserve a field position -- the wrong trade. Moving it costs nothing while there is one kind.",
        },
        "consequence_for_the_core": "the core now carries NO kind-relative identity field. `id` remains and passes on its own terms: its DERIVATION is per-kind (it hashes whichever request identity the kind has), its MEANING is not. Derivation may be kind-specific; meaning may not.",
        "status": "RESOLVED_IN_DAF",
        "enforcement": "tests/test_execution_record_divergence.py",
    },
    "rejected_shapes": {
        "abstract_contract_two_concretes": "collapses into the adopted shape at the persistence boundary, since execution_record_from_dict must recover the kind FROM THE PAYLOAD, which requires a discriminant anyway",
        "rename": "produces the two-records-side-by-side arrangement this file's own integration_dependency rules out; retained as the fallback only if the intersection were empty, which it is not",
    },
    "implementation_timing": "the SHAPE is fixed now; the schema migration is not performed now, because no computation kind exists here to discriminate toward and introducing a one-valued discriminant would re-digest every stored record for no present capability",
    "is_a_bend": False,
    "bend_reasoning": "no invariant's semantic domain changes -- execution_recorded, execution_is_not_evidence and execution_identity_is_separate all keep their exact meaning under a discriminated record",
    "enforced_now": "tests/test_execution_record_divergence.py locks the intersection, the refused merges and the unchanged record, so the decision cannot drift before it is built",
    "detail": "architecture/execution_record.yaml divergence_resolution",
}

RECURSIVE_DEPTH_DETERMINATION = {
    "invariant": "generation_depth_bounded",
    "implemented": False,
    "invariant_status": "represented_unenforced",
    "measured_basis": "`generation_depth` appears nowhere in daf/, epistemics/, science/, boundary/, bridge/ or assertion/. The invariant is DECLARED and its DOMAIN is empty -- a third state, neither enforced nor absent.",
    "correction_mode": "write_it_correctly_first",
    "correction_mode_reason": "demonstrate-then-correct requires an implementation whose behaviour can be demonstrated and then corrected; there is none",
    "is_a_bend": False,
    "bend_reasoning": "the rule text is not weakened, narrowed or qualified -- it begins to APPLY. An invariant acquiring a non-empty domain is the opposite of a bend. What DOES change is the recorded EVIDENCE: 'no generative path exists to bound' becomes false, so it must be rewritten and the status moved off vacuously_enforced BEFORE any recursive result is admitted.",
    "the_condition_that_would_make_it_a_bend": "authoring the rule AFTER a recursive trajectory already exists -- then the rule's shape would be determined by the thing it constrains. This is why the ordering is load-bearing.",
    "bend_protocol_exists_in_daf": False,
    "bend_protocol_note": "no bend_protocol artifact, module or reference exists in this repository; the only occurrences of the word are ordinary prose. Recorded as a measured absence rather than treated as satisfied. This determination concludes no bend is required, so the absence does not block it.",
    "proposed_rule_status": "offered_not_adopted",
    "daf_assessment_of_the_guard": "the composition guard is the substantive part and is correct to include: without it, a chain alternating computation and re-ingestion would reset to depth 0 at every re-ingestion, so an arbitrarily long derived chain could present as depth 0 while satisfying the letter of the rule",
    "what_daf_would_still_have_to_supply": "the rule references initialization_provenance and a per-stream evidence class. Evidence classes exist; nothing carries a per-stream class into a computation's inputs. That is DAF-side work and is not costed here.",
    "domain_emptiness_is_asserted_directly": {
        "why": "the source-level detectors establish NO VIOLATION WAS FOUND, which is weaker than THE DOMAIN IS EMPTY. The two come apart exactly when a detector's coverage narrows -- a path shaped differently, a record written by a tool, a fixture that gets persisted. A guard that would silently stop detecting is the same failure class as a conformance test that has never failed.",
        "what_is_asserted": "no `computed` or `derived` evidence-class record exists anywhere, scanned as RAW JSON rather than through assignment_from_dict -- because a corrupt computed record is still a computed record, and a parse-based check would refuse it and report nothing found.",
        "fires_on": "the first record of either class, well-formed or not",
        "why_this_layer_is_needed": "nothing FORBIDS a computed or derived assignment; both are canonically admissible. The domain is empty because nothing produces one, and that is a fact about today which no rule protects.",
        "enforcement": "tests/test_recursive_lineage_depth.py::test_no_generative_class_record_exists_anywhere, proven to fire by ::test_the_domain_detector_fires_on_a_planted_record",
    },
    "detail": "architecture/recursive_depth.yaml",
}


UNRESOLVED_EDGES = {
    "uniformity_is_unchecked": {
        "edge": "DAF supplies per-sample timestamps; the compute layer's transform accepts ONE optional scalar sample spacing. The real NOAA series is uniform at exactly 360.0 s, so a single spacing happens to be honest for it -- but nothing computes, checks or records that. A gapped or irregular series would silently violate the single-spacing assumption while every number involved stayed well-formed.",
        "measured_basis": "all 239 inter-sample gaps in tests/fixtures/noaa_live_8454000_20240115_mllw.json are exactly 360.0 s; no code anywhere asserts this",
        "owner": "unassigned -- it falls between the two contracts rather than inside either",
        "why_it_is_not_solved_here": "DAF does not know that a consumer wants a single spacing, and the compute layer does not see the timestamps. Neither side is wrong on its own terms; the gap is the conversion nobody owns.",
        "shape": "this is the same shape as the compute layer's own annotating-parameter rule: a wrong spacing is invisibly present rather than visibly absent",
        "status": "RECORDED_UNRESOLVED",
    },
    "unreached_by_accident": {
        "edge": "Two holes in this repository are currently harmless only because nothing exercises them: a covariance uncertainty is admitted but unreached because no extractor emits one, and series uniformity is relied upon but unchecked because the one real series happens to be uniform.",
        "why_it_matters": "both would be discovered by the first workload that used them, not by a check. A gap that is closed by luck reads identically to one that is closed by design, right up until it does not.",
        "status": "RECORDED_UNRESOLVED",
    },
    "absent_is_not_zero_generalization": {
        "edge": "The compute layer records absent-is-not-zero as a core-vocabulary candidate on three independent arrivals. DAF supplies a fourth and a counter-example at once: uncertainty_kind HAS a declarable `absent`, and `value` has no counterpart at all -- a missing measurement is an absent Observation rather than a present one carrying an absence.",
        "reading": "the distinction is real and is NOT uniformly applied even within one repository, which is mild evidence for the core-vocabulary reading and equally mild evidence that per-field absence semantics differ enough to resist one treatment",
        "status": "RECORDED_UNRESOLVED",
    },
}


IDENTITY_MODEL = {
    "distinct_identities": "artifact identity, artifact version identity, acquisition identity, execution identity, observation identity and evidence identity are six distinct identities; an execution record may REFERENCE them and may not REDEFINE them",
    "primitive": "evidence.identity.content_hash -- the same primitive every id in this repository uses",
    "execution_id": "H(operation_id, runtime_id, started_at), minted BEFORE the run begins, so a run that fails at its first step still has one",
    "operation_id": "H(plan_id, source_id, parameters, mode), stable across runs",
    "content_digest": "H(every field except id and content_digest), minted when the run ends -- the identity hash deliberately excludes the outcome, so integrity over the outcome needs its own digest",
    "enforcement": "tests/test_execution_record.py",
    "status": "EXISTING and unchanged by this artifact",
}


CORE_VOCABULARY_CANDIDATES = {
    "coverage_specified_by_enumeration": {
        "edge": "DAF proposes this as a core-vocabulary candidate on the same footing as absent-is-not-zero and one-meaning-one-encoding, on THREE independent arrivals in this repository: (1) a push reported failed by grepping command output for a failure string, which matched a stale `fatal` and reported failure over a success; (2) a mutation check that a mutation was applied without checking it reached executable semantics, so it passed on a comment; (3) the two-parser typed-agreement check, which globbed architecture/exchange and architecture/proposals and NOT architecture/decisions -- so an escape defect reached a hash-bearing artifact with every suite green.",
        "the_shared_shape": "in each case the check's PREDICATE was a list someone wrote rather than the property anyone cared about. A check specified by enumeration is correct exactly until the world grows an item nobody added to the list, and it fails SILENTLY at that moment -- it reports success, because the thing it enumerates is still fine.",
        "the_repair_that_generalizes": "assert the PROPERTY, not the enumeration. The decisions/ hole was not repaired by adding the directory; it was repaired by asserting the rule -- every directory carrying a .sha256 sidecar has its artifacts in the checked set -- which fails on the next hash-bearing directory nobody thought about. Adding the missing item fixes one instance; asserting the property fixes the class.",
        "how_to_tell_you_are_in_it": "the check names WHAT it looks at instead of deriving it. A glob over a written list of directories, a grep for a specific string, a search over an enumerated set of files -- each is a coverage predicate that cannot notice its own incompleteness.",
        "why_it_is_worse_than_the_defects_it_hides": "the enumerated check is not merely absent, it is ACTIVELY REASSURING. No coverage at all leaves a visible hole; coverage-by-enumeration reports green over the hole, and a green suite is then cited as evidence that the property holds.",
        "relation_to_the_other_two_candidates": "absent-is-not-zero is about a VALUE that must not be encodable as another value. One-meaning-one-encoding is about BYTES that must not carry two meanings. This is about a CHECK whose scope must not be a list -- the same family, applied to the verification layer rather than to the data.",
        "status": "PROPOSED_CORE_VOCABULARY_CANDIDATE",
    },
}


def _fixture_agreement() -> str:
    """The fixture digest READ FROM THE SIDECAR rather than transcribed.

    The transcribed value went stale through two coordinated reissues --
    it named a digest from before both -- because a hand-copied hash in a
    prose field is a claim nothing binds. Deriving it means the artifact
    cannot describe an encoding other than the one it was generated
    under."""
    recorded = (pathlib.Path(__file__).resolve().parent
                / "canonicalization_fixture.sha256").read_text().strip()
    return (f"both repositories independently produce {recorded} for the shared fixture -- "
            "verified by running canonical_yaml.py in each")


DOCUMENT = {
    "artifact": "daq_capabilities",
    "canonicalization": {
        "anchors_aliases": "forbidden",
        "encoding": "UTF-8, LF line endings, single trailing newline",
        "floats": "shortest round-trip repr; exponent form only when |x| < 1e-4 or |x| >= 1e16, and then always with a decimal point in the mantissa and an explicit exponent sign so the value round-trips as a float under YAML 1.1 as well as 1.2",
        "hash": "sha256 over the serialized bytes",
        "implementation": "architecture/exchange/canonical_yaml.py -- byte-identical to the compute layer's copy",
        "keys": "sorted lexicographically at every level",
        "reference_format": "sha256:<hex>",
        "sequence_in_sequence": "REFUSED at the emitter. The compact block form `- - 1` is read as a nested sequence by PyYAML and as the STRING '- 1' by the dependency-free reader, with no error from either -- same bytes, two values. No emitted form is read identically by both, so it is refused rather than rendered differently.",
        "serialization": "YAML 1.2, block style only; {} and [] are the one documented exception, since empty collections have no block form. Block style is NOT by itself sufficient for agreement -- `- - 1` is block style and is refused; see sequence_in_sequence.",
        "shared_fixture": "architecture/exchange/canonicalization_fixture.yaml",
        "shared_fixture_agreement": _fixture_agreement(),
        "strings": "double-quoted ALWAYS, values and keys alike. NOT 'only where plain style would be unsafe' -- that was the rule this artifact carried until the first coordinated reissue replaced it, and the description went un-updated through two reissues because nothing bound an artifact's account of the encoding to the encoding.",
    },
    "capability_inventory": CAPABILITIES,
    "core_vocabulary_candidates": CORE_VOCABULARY_CANDIDATES,
    "classification_vocabulary": [_EXISTING, _REUSABLE, _SMALL_EXTENSION, _MISSING, _OUT_OF_SCOPE],
    "contains_workload_selection": False,
    "execution_record_resolution": EXECUTION_RECORD_RESOLUTION,
    "extends": "core@1.0.0",
    "generated_by": "architecture/exchange/build_daq_capabilities.py",
    "identity_model": IDENTITY_MODEL,
    "nonscalar_quantity_finding": NONSCALAR_QUANTITY_FINDING,
    "owner": "daf",
    "paired_artifact": "scl_requirements.yaml, in the compute layer's repository",
    "recursive_depth_determination": RECURSIVE_DEPTH_DETERMINATION,
    "requirement_responses": REQUIREMENT_RESPONSES,
    "scope": "measured capabilities of this repository, and answers to the requirement rows it received. No workload is chosen or ordered here; that belongs to the joint decision record.",
    "unresolved_edges": UNRESOLVED_EDGES,
}


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    target = here / "daq_capabilities.yaml"
    target.write_bytes(canonical_bytes(DOCUMENT))
    digest = canonical_sha256(DOCUMENT)
    (here / "daq_capabilities.sha256").write_text(digest + "\n")
    print(f"wrote {target.name}")
    print(f"capabilities_artifact_hash: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
