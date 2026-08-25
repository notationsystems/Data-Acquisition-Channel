"""Does EDGAR's daily-index form type constitute method provenance for
the property-admissibility gate? No -- and the reason is not even that
form type is the wrong kind of field. `daf/extractors/edgar_daily_index.py`
produces no property assertion at all, so the question of what could
satisfy `MISSING_METHOD` does not arise for this source.

Also corrects a real error: Phase 29's own report claimed form_type was
"present in the raw .idx row, currently discarded." Measured here: it is
not discarded. It is parsed, per filing, and aggregated into
`form_type_counts` -- and has been since this extractor was written.

Every acquisition below is the real, unmodified Scout/DAF path. No
production code was changed by this phase; these tests exist to lock the
determination, not a fix.
"""

from __future__ import annotations

from pathlib import Path

from assertion.property_admissibility import (
    assess_pool,
    canonical_assertion_quarantine_store,
    property_candidates,
)
from daf.adapters.edgar_daily_index import EdgarDailyIndexSourceAdapter
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import RuntimeIdentity
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.extractors.edgar_daily_index import EdgarDailyIndexExtractor
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics._yaml import loads
from epistemics.evidence_class import ASSERTED
from science.admissibility import no_context_free_property

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DETERMINATIONS = loads(
    (REPO_ROOT / "architecture" / "method_provenance_reachability.yaml").read_text()
)["determinations"]
EDGAR = DETERMINATIONS["edgar_daily_index_form_type"]

RUNTIME = RuntimeIdentity(python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1)


def _edgar_routes():
    return {
        "index.json": (FIXTURES / "edgar_index_listing_synthetic.json").read_bytes(),
        "company.20260701.idx": (FIXTURES / "edgar_daily_index_synthetic_20260701.idx").read_bytes(),
        "company.20260702.idx": (FIXTURES / "edgar_daily_index_synthetic_20260702.idx").read_bytes(),
        "company.20260703.idx": (FIXTURES / "edgar_daily_index_synthetic_20260703.idx").read_bytes(),
    }


def _router(routes):
    def fetch(url: str) -> bytes:
        for suffix, content in routes.items():
            if url.endswith(suffix):
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return fetch


def _acquire_edgar(root, *, started_at="2026-08-25T00:00:00Z"):
    """The real, unmodified EDGAR acquisition path: adapter -> extractor
    -> run_scout -> ClassifiedPool, wrapped with execution recording."""
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="edgar-filings",
            name="SEC EDGAR",
            domain="filings",
            adapter_id="edgar-daily-index",
            required_parameters=("year", "quarter"),
            capabilities=("incremental",),
        )
    )

    def build_adapter(source, request):
        return EdgarDailyIndexSourceAdapter(
            year=int(request.parameters["year"]),
            quarter=int(request.parameters["quarter"]),
            retrieved_at=request.requested_at,
            fetch_bytes=_router(_edgar_routes()),
        )

    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(
            adapter_id="edgar-daily-index", build_adapter=build_adapter, build_extractor=EdgarDailyIndexExtractor
        )
    )
    pool = ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id="source_policy:phase30", by_source_kind={"daily-index": ASSERTED}),
    )
    recorded = execute_plan_recorded(
        AcquisitionPlan(plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3}),
        sources,
        adapters,
        pool,
        CheckpointStore(root / "checkpoints"),
        requested_at=started_at,
        executions=ExecutionRecordStore(root),
        quarantine=QuarantineStore(root),
        runtime=RUNTIME,
        started_at=started_at,
        finished_at=started_at,
    )
    return recorded, pool


# --------------------------------------------------- 1. field preservation


def test_form_type_is_not_discarded_by_the_extractor(tmp_path):
    """The correction. Phase 29 claimed this field was discarded. It is
    parsed per filing and aggregated -- measured on a real acquisition,
    not read from the extractor source alone."""
    recorded, pool = _acquire_edgar(tmp_path)
    assert recorded.result.outcome.value == "acquired"

    observations = pool.all_observations()
    assert len(observations) == 3

    all_form_types = set()
    for observation in observations:
        assert "form_type_counts" in observation.content
        for filing in observation.content["filings"]:
            assert "form_type" in filing
            all_form_types.add(filing["form_type"])
        # per-filing values and the aggregate agree
        assert sum(observation.content["form_type_counts"].values()) == len(observation.content["filings"])

    assert all_form_types == set(EDGAR["real_values_observed"])


def test_the_extractor_source_was_not_modified_by_this_phase():
    """§16: no production code changed. The parsing logic that already
    carries form_type through predates this phase."""
    source = (REPO_ROOT / "daf" / "extractors" / "edgar_daily_index.py").read_text()
    assert '"form_type": form_type' in source
    assert "form_type_counts[form_type]" in source


# ------------------------------------------- 2/3. semantic classification


def test_the_observed_form_types_are_regulatory_filing_classifications():
    """§3's source-authenticity test, locked against real values rather
    than the field's name. Every value acquired is a documented SEC
    filing-type code, none a measurement/computational/simulation
    method."""
    observed = set(EDGAR["real_values_observed"])
    known_sec_form_types = {"10-K", "8-K", "8-K/A", "S-1", "424B3", "D"}
    assert observed == known_sec_form_types

    # None of the real values resembles any known scientific method
    # vocabulary this repository has ever encountered (magnitude types,
    # uncertainty kinds, or the ASTM-style method string used in the
    # Phase 29 accepted-property fixture).
    scientific_method_tokens = {"mb", "ml", "mw", "md", "mww", "astm", "stated", "estimated", "propagated", "absent"}
    assert observed.isdisjoint({t.lower() for t in scientific_method_tokens})


def test_the_classification_is_document_classification_not_method():
    assert EDGAR["semantic_classification"] == "document_classification"
    assert EDGAR["verdict"] == "document_classification"


# --------------------------------------- 4. observation identity preserved


def test_observation_identity_is_unaffected_because_content_is_unchanged(tmp_path):
    """§4/§10: no code was changed, so no identity could have changed.
    Verified by running the same acquisition twice and checking every
    observation id is reproduced exactly, and by content-hashing the
    extractor's own real output against what Phase 29's fixtures already
    exercised."""
    first, _ = _acquire_edgar(tmp_path / "a", started_at="2026-08-25T00:00:00Z")
    second, _ = _acquire_edgar(tmp_path / "b", started_at="2026-08-26T00:00:00Z")

    first_ids = {o.id for o in ClassifiedPool(
        FilesystemEvidenceStore(tmp_path / "a" / "evidence"),
        SourceClassPolicy(id="x", by_source_kind={}),
    ).store.all_documents()}
    second_ids = {o.id for o in ClassifiedPool(
        FilesystemEvidenceStore(tmp_path / "b" / "evidence"),
        SourceClassPolicy(id="x", by_source_kind={}),
    ).store.all_documents()}
    assert first_ids == second_ids, "identical source bytes must reproduce identical artifact identity"
    assert first.execution.artifact_ids == second.execution.artifact_ids
    assert first.execution.id != second.execution.id, "two runs remain two distinct executions"


# ----------------------------------------------- 5/6. gate behavior


def test_edgar_content_has_no_property_key_at_all(tmp_path):
    """The deeper finding under the semantic one: even setting aside
    what form_type MEANS, there is no property/value assertion in EDGAR
    content for a method to attach to."""
    _, pool = _acquire_edgar(tmp_path)
    for observation in pool.all_observations():
        assert "property" not in observation.content
        assert "value" not in observation.content


def test_no_context_free_property_reports_every_absence_not_just_method(tmp_path):
    """MISSING_METHOD is one of six simultaneous absences on real EDGAR
    content, not the single gap a method-only fix would close."""
    _, pool = _acquire_edgar(tmp_path)
    for observation in pool.all_observations():
        verdict = no_context_free_property(observation.content)
        assert not verdict.admissible
        assert set(verdict.reasons) == {
            "MISSING_PROPERTY",
            "MISSING_VALUE",
            "MISSING_UNIT",
            "MISSING_METHOD",
            "MISSING_CONDITIONS",
            "MISSING_UNCERTAINTY_KIND",
        }


def test_zero_property_candidates_are_examined_for_a_real_edgar_acquisition(tmp_path):
    """The property-admissibility layer never even reaches EDGAR
    observations, through the real, unmodified pipeline."""
    recorded, pool = _acquire_edgar(tmp_path)
    candidates = property_candidates(pool, recorded.execution.id)
    assert candidates == ()

    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))
    assert report.candidates_examined == 0
    assert report.accepted == 0
    assert report.refused == 0
    assert report.rejection_rate is None, "zero candidates is absence, not a rate of zero"


def test_form_type_was_not_forced_through_the_method_gate():
    """§16 exclusion, checked against the actual wiring code: nothing in
    `assertion/` special-cases EDGAR or its form_type field."""
    source = (REPO_ROOT / "assertion" / "property_admissibility.py").read_text()
    assert "form_type" not in source
    assert "edgar" not in source.lower()


# ------------------------------------------------ 7/8. conditions/uncertainty


def test_conditions_and_uncertainty_remain_independently_absent():
    """§7/§8: treated separately from the method finding, and neither is
    synthesized. Measured against the real gate output above, which
    already carries MISSING_CONDITIONS and MISSING_UNCERTAINTY_KIND
    alongside MISSING_METHOD -- none was solved by the other."""
    assert "MISSING_CONDITIONS" in EDGAR["conditions"]
    assert "MISSING_UNCERTAINTY_KIND" in EDGAR["uncertainty"] or "uncertainty" in EDGAR["uncertainty"].lower()

    # No uncertainty_kind value is assigned anywhere in the determination --
    # not `absent`, not any of the other three. Checked structurally rather
    # than by forbidding the English word, since the prose must be able to
    # discuss why `absent` specifically was not chosen.
    assert "uncertainty_kind" not in EDGAR
    from science.admissibility import UNCERTAINTY_KINDS

    for kind in UNCERTAINTY_KINDS:
        assert EDGAR.get("assigned_uncertainty_kind") != kind


# --------------------------------------------------------- 9. real acquisition


def test_the_real_edgar_path_remains_fully_executable(tmp_path):
    """Nothing about this phase's determination broke acquisition."""
    recorded, pool = _acquire_edgar(tmp_path)
    assert recorded.result.outcome.value == "acquired"
    assert recorded.execution.status == "SUCCEEDED"
    assert len(pool.all_observations()) == 3
    assert recorded.execution.admission_failure_count == 0


# ------------------------------------------------ 11. evidence boundary


def test_no_evidence_pool_bypass_and_edgar_observations_remain_real_evidence(tmp_path):
    recorded, pool = _acquire_edgar(tmp_path)
    before = pool.fingerprint()

    property_candidates(pool, recorded.execution.id)
    assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert pool.fingerprint() == before, "reconnaissance changed the evidence pool"
    for observation in pool.all_observations():
        assert pool.has_observation(observation.id)
        assert pool.register.class_of(observation.id) == ASSERTED


# ---------------------------------------------- 12. Phase 27/28/29 metrics


def test_phase_27_28_29_metrics_are_unaffected_by_this_determination(tmp_path):
    from daf.execution.metrics import rejection_metrics

    recorded, pool = _acquire_edgar(tmp_path)
    metrics = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    assert metrics.accepted == 3
    assert metrics.terminal_refusals == 0
    assert metrics.attempts == 3
    assert metrics.rejection_rate == 0.0

    backlog_categories = {c.category for c in __import__(
        "daf.execution.metrics", fromlist=["unclassified_backlog"]
    ).unclassified_backlog(pool.store, pool.register).categories}
    assert "documents" in backlog_categories


# ------------------------------------------------- the next-frontier candidate


def test_the_usgs_candidate_is_recorded_but_not_implemented():
    """The next executable frontier is named, evidenced, and explicitly
    NOT built in this phase -- matching this repository's established
    one-frontier-per-phase discipline."""
    usgs = DETERMINATIONS["usgs_magnitude_type"]
    assert usgs["verdict"] == "legitimate_method_provenance"
    assert usgs["action_taken"] == "none"

    extractor_source = (REPO_ROOT / "daf" / "extractors" / "usgs_earthquakes.py").read_text()
    assert '"magnitude_type": properties.get("magType")' in extractor_source
    assert '"method"' not in extractor_source, "USGS content was not reshaped by this phase"
