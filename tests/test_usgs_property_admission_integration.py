"""USGS earthquake magnitude, wired against the real property-admissibility
gates -- and correctly still rejected, for reasons the source genuinely
cannot supply.

    real USGS acquisition (adapter -> extractor -> run_scout -> pool)
        |
        v  Observation.content now carries property/value/unit/method
    science.admissibility.no_context_free_property   (UNCHANGED)
        |
    MISSING_METHOD:  resolved (magnitude_type is genuine method provenance)
    MISSING_UNIT:    resolved (dimensionless is the true physical fact)
    MISSING_CONDITIONS:       still refused -- no real conditioning field
    MISSING_UNCERTAINTY_KIND: still refused -- no real error data

This is Phase 31's central result: correctly resolving a semantic
ambiguity does not, by itself, make a source admissible. The remaining
two refusals are as genuine as EDGAR's six were in Phase 30 -- neither
gate was weakened, and nothing was fabricated to close them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from assertion.property_admissibility import (
    CANONICAL_ASSERTION_STAGE,
    assess_pool,
    canonical_assertion_quarantine_store,
    property_candidates,
)
from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import RuntimeIdentity
from daf.execution.metrics import rejection_metrics
from daf.execution.quarantine import QuarantineIdentityMismatch, quarantine_record_to_dict
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.extractors.usgs_earthquakes import DIMENSIONLESS_UNIT, PROPERTY, UsgsEarthquakeExtractor
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics._yaml import loads
from epistemics.evidence_class import MEASURED
from science.admissibility import no_context_free_property, quantity_is_typed

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DETERMINATIONS = loads(
    (REPO_ROOT / "architecture" / "method_provenance_reachability.yaml").read_text()
)["determinations"]
USGS = DETERMINATIONS["usgs_magnitude_type"]
EDGAR = DETERMINATIONS["edgar_daily_index_form_type"]

RUNTIME = RuntimeIdentity(python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1)


def _usgs_router(routes):
    def fetch(url: str) -> bytes:
        for marker, content in routes.items():
            if marker in url:
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return fetch


def _standard_routes():
    return {
        "eventid=synth00000001": (FIXTURES / "usgs_event_detail_synth00000001.json").read_bytes(),
        "eventid=synth00000002": (FIXTURES / "usgs_event_detail_synth00000002.json").read_bytes(),
        "eventid=synth00000003": (FIXTURES / "usgs_event_detail_synth00000003.json").read_bytes(),
        "starttime=": (FIXTURES / "usgs_listing_synthetic.json").read_bytes(),
    }


def _acquire_usgs(root, routes=None, *, started_at="2026-08-25T00:00:00Z"):
    """The real, unmodified USGS acquisition path: adapter -> extractor
    -> run_scout -> ClassifiedPool, wrapped with execution recording."""
    routes = routes if routes is not None else _standard_routes()
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="usgs-quakes",
            name="USGS Earthquakes",
            domain="environmental-observations",
            adapter_id="usgs-earthquakes",
            required_parameters=("start_time", "end_time", "min_magnitude"),
            capabilities=("incremental",),
        )
    )

    def build_adapter(source, request):
        return UsgsEarthquakeSourceAdapter(
            start_time=str(request.parameters["start_time"]),
            end_time=str(request.parameters["end_time"]),
            min_magnitude=float(request.parameters["min_magnitude"]),
            retrieved_at=request.requested_at,
            fetch_bytes=_usgs_router(routes),
        )

    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(
            adapter_id="usgs-earthquakes", build_adapter=build_adapter, build_extractor=UsgsEarthquakeExtractor
        )
    )
    pool = ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id="source_policy:phase31", by_source_kind={"event-detail": MEASURED}),
    )
    recorded = execute_plan_recorded(
        AcquisitionPlan(
            plan_id="usgs-plan",
            source_id="usgs-quakes",
            parameters={"start_time": "2026-01-01", "end_time": "2026-01-02", "min_magnitude": 1.0},
        ),
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


# --------------------------------------------------- 1. real acquisition


def test_real_usgs_acquisition_reaches_magnitude_observations(tmp_path):
    recorded, pool = _acquire_usgs(tmp_path)
    assert recorded.result.outcome.value == "acquired"

    observations = pool.all_observations()
    assert len(observations) == 3
    assert {o.content["magnitude_type"] for o in observations} == {"mb", "ml"}


# ------------------------------------------------- 2. magnitude_type preserved


def test_magnitude_type_is_preserved_alongside_the_new_method_key(tmp_path):
    """Additive, never replaced: both the original and the new key exist
    and always agree, because both are set from the same variable."""
    _, pool = _acquire_usgs(tmp_path)
    for o in pool.all_observations():
        assert o.content["method"] == o.content["magnitude_type"]
        assert o.content["value"] == o.content["magnitude"]


# --------------------------------------------------- 3. method semantics


def test_method_is_the_verbatim_source_value_never_reinterpreted():
    """§5: no new method ontology. The value is carried through exactly,
    not wrapped, prefixed, or mapped to a synonym."""
    source = (REPO_ROOT / "daf" / "extractors" / "usgs_earthquakes.py").read_text()
    assert '"method": magnitude_type' in source


def test_a_missing_magtype_yields_a_genuine_missing_method_rejection(tmp_path):
    """Honesty check: a real event lacking magType must not receive a
    default. Exercised through the real gate, not merely the extractor."""
    import json

    malformed_listing = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [{"id": "no-magtype", "properties": {"updated": 1700000000000}}],
        }
    )
    no_magtype_detail = json.dumps(
        {
            "type": "Feature",
            "id": "no-magtype",
            "properties": {"mag": 2.5, "time": 1, "updated": 2, "place": "p"},
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0, 1.0]},
        }
    )
    recorded, pool = _acquire_usgs(
        tmp_path,
        routes={"eventid=no-magtype": no_magtype_detail.encode(), "starttime=": malformed_listing.encode()},
    )
    assert recorded.result.outcome.value == "acquired"
    observation = pool.all_observations()[0]
    assert observation.content["method"] is None

    verdict = no_context_free_property(observation.content)
    assert "MISSING_METHOD" in verdict.reasons


# ------------------------------------------------- 4/5. quantity semantics


def test_quantity_is_typed_accepts_the_dimensionless_unit(tmp_path):
    _, pool = _acquire_usgs(tmp_path)
    for o in pool.all_observations():
        verdict = quantity_is_typed(o.content)
        assert "MISSING_UNIT" not in verdict.reasons
        assert "UNTYPED_QUANTITY" not in verdict.reasons
        assert o.content["unit"] == DIMENSIONLESS_UNIT


def test_scale_identifier_never_appears_as_the_unit_value(tmp_path):
    """§4/§6: Mw must never become unit='Mw'. The scale lives only in
    `method`/`magnitude_type`; `unit` is always the dimensionless
    declaration, regardless of which magnitude scale was used."""
    _, pool = _acquire_usgs(tmp_path)
    scale_codes = {"mb", "ml", "mw", "md", "mww"}
    for o in pool.all_observations():
        assert o.content["unit"] not in scale_codes
        assert o.content["unit"] == "dimensionless"


def test_quantity_contract_requires_no_dimensional_validation():
    """§3, measured against the real gate source rather than assumed."""
    import inspect

    source = inspect.getsource(quantity_is_typed)
    assert "content.get(\"unit\")" in source
    # No unit vocabulary, dimension table, or SI validation exists.
    for forbidden in ("SI_UNITS", "dimension", "pint", "astropy"):
        assert forbidden not in source


# --------------------------------------------------- 6. property identity


def test_property_quantity_scale_and_method_are_not_conflated(tmp_path):
    _, pool = _acquire_usgs(tmp_path)
    observation = pool.all_observations()[0]
    content = observation.content

    assert content["property"] == PROPERTY == "earthquake_magnitude"
    assert content["value"] == content["magnitude"]
    assert content["unit"] == "dimensionless"
    assert content["method"] == content["magnitude_type"] == "mb"
    # Four distinct concepts, four distinct values -- none equal any other
    # except the deliberate value/magnitude and method/magnitude_type pairs.
    assert content["property"] != content["method"]
    assert content["unit"] != content["method"]
    assert content["property"] != content["unit"]


# --------------------------------------------------------- 7. uncertainty


def test_uncertainty_remains_genuinely_missing_not_fabricated(tmp_path):
    _, pool = _acquire_usgs(tmp_path)
    for o in pool.all_observations():
        assert "uncertainty_kind" not in o.content
        assert "uncertainty" not in o.content
        verdict = quantity_is_typed(o.content)
        assert "MISSING_UNCERTAINTY_KIND" in verdict.reasons


def test_absent_was_considered_and_rejected_not_merely_omitted():
    """§7's distinction, preserved from Phase 30: 'the source did not
    report uncertainty' is not 'the source reported no uncertainty'."""
    assert "absent" in USGS["uncertainty_decision"].lower()
    assert "explicitly reported no error" in USGS["uncertainty_decision"]


# ---------------------------------------------------------- 8. conditions


def test_conditions_remain_genuinely_missing_not_synthesized(tmp_path):
    _, pool = _acquire_usgs(tmp_path)
    for o in pool.all_observations():
        assert "conditions" not in o.content
        verdict = no_context_free_property(o.content)
        assert "MISSING_CONDITIONS" in verdict.reasons


def test_identity_and_revision_metadata_are_not_treated_as_conditions():
    """place/origin_time/depth_km identify the event; status is revision
    metadata, per the same reasoning Phase 17 applied to NOAA's `q`."""
    assert "identity" in USGS["conditions_decision"].lower()
    assert "status" in USGS["conditions_decision"]
    assert "revision" in USGS["conditions_decision"].lower()


# ------------------------------------------------ 9/10. admission outcome


def test_the_real_acquisition_is_examined_and_rejected_for_exactly_two_reasons(tmp_path):
    recorded, pool = _acquire_usgs(tmp_path)
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert report.candidates_examined == 3
    assert report.accepted == 0
    assert report.refused == 3
    assert set(report.by_code) == {"MISSING_CONDITIONS", "MISSING_UNCERTAINTY_KIND"}
    assert "MISSING_METHOD" not in report.by_code
    assert "MISSING_UNIT" not in report.by_code
    assert "MISSING_PROPERTY" not in report.by_code
    assert "MISSING_VALUE" not in report.by_code


def test_a_refused_usgs_property_remains_real_admitted_evidence(tmp_path):
    recorded, pool = _acquire_usgs(tmp_path)
    before = pool.fingerprint()

    assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert pool.fingerprint() == before, "a canonical-assertion pass changed the evidence pool"
    for o in pool.all_observations():
        assert pool.has_observation(o.id)
        assert pool.register.class_of(o.id) == MEASURED


def test_rejected_usgs_properties_are_quarantined_with_full_linkage(tmp_path):
    recorded, pool = _acquire_usgs(tmp_path)
    quarantine = canonical_assertion_quarantine_store(tmp_path)
    report = assess_pool(pool, recorded.execution.id, quarantine)

    stored = quarantine.for_execution(recorded.execution.id)
    assert len(stored) == report.refused == 3
    for record in stored:
        assert record.execution_id == recorded.execution.id
        assert record.stage == CANONICAL_ASSERTION_STAGE
        assert {e.code for e in record.errors} <= {"MISSING_CONDITIONS", "MISSING_UNCERTAINTY_KIND"}

    scout_quarantine = QuarantineStore(tmp_path)
    assert scout_quarantine.for_execution(recorded.execution.id) == ()
    assert recorded.execution.admission_failure_count == 0


def test_the_quarantine_records_are_tamper_evident(tmp_path):
    recorded, pool = _acquire_usgs(tmp_path)
    quarantine = canonical_assertion_quarantine_store(tmp_path)
    assess_pool(pool, recorded.execution.id, quarantine)

    stored = quarantine.for_execution(recorded.execution.id)[0]
    payload = quarantine_record_to_dict(stored)
    path = quarantine.root / f"{stored.id}.json"
    path.write_text(__import__("json").dumps(dict(payload, stage="tampered")))

    with pytest.raises(QuarantineIdentityMismatch):
        canonical_assertion_quarantine_store(tmp_path).all_records()


# ------------------------------------------------------ 11. identity


def test_observation_identity_changed_and_is_disclosed(tmp_path):
    """§11: the content-addressed identity DID change, because content
    genuinely changed. Verified directly rather than merely asserted in
    prose: the SAME record_ids a real acquisition actually produced,
    re-hashed with the OLD (pre-Phase-31) content shape, yields a
    DIFFERENT observation id than the real, current one -- isolating the
    identity change to content alone, with the real record untouched."""
    from evidence.types import make_observation

    _, pool = _acquire_usgs(tmp_path)
    new_observation = next(
        o for o in pool.all_observations() if o.content["event_id"] == "synth00000001"
    )

    old_shape_content = {
        key: value
        for key, value in new_observation.content.items()
        if key not in ("property", "value", "unit", "method")
    }
    assert old_shape_content == {
        "event_id": "synth00000001",
        "magnitude": 4.1,
        "magnitude_type": "mb",
        "place": "SYNTHETIC TEST PLACE ALPHA",
        "origin_time": 1700000001000,
        "updated": 1700000101000,
        "status": "reviewed",
        "longitude": -100.0001,
        "latitude": 10.0001,
        "depth_km": 12.3,
    }, "the pre-Phase-31 keys must all still be present and unchanged"

    old_shape_observation = make_observation(
        record_ids=new_observation.record_ids,
        extraction_method=new_observation.extraction_method,
        content=old_shape_content,
        confidence=new_observation.confidence,
        extracted_at=new_observation.extracted_at,
    )

    assert new_observation.id != old_shape_observation.id, (
        "content genuinely changed and the identity change must be real, not concealed"
    )
    assert new_observation.record_ids == old_shape_observation.record_ids, (
        "the underlying record -- what was actually fetched -- did not change"
    )


def test_artifact_identity_is_unaffected_by_the_content_addition(tmp_path):
    """Artifact identity is H({source_id, locator}) -- it never depends
    on Observation.content, so it is provably unaffected."""
    first, _ = _acquire_usgs(tmp_path / "a", started_at="2026-08-25T00:00:00Z")
    second, _ = _acquire_usgs(tmp_path / "b", started_at="2026-08-26T00:00:00Z")

    assert first.execution.artifact_ids == second.execution.artifact_ids
    assert first.execution.id != second.execution.id


# ---------------------------------------------- 12. EDGAR unchanged (cross-source)


def test_edgar_semantics_are_unchanged_by_the_usgs_extension(tmp_path):
    """§15: the two determinations remain distinct. Nothing about wiring
    USGS reinterprets or loosens the EDGAR verdict."""
    assert EDGAR["verdict"] == "document_classification"
    assert USGS["verdict"] == "legitimate_method_provenance"
    assert EDGAR["verdict"] != USGS["verdict"]

    edgar_source = (REPO_ROOT / "daf" / "extractors" / "edgar_daily_index.py").read_text()
    assert '"property"' not in edgar_source
    assert '"method"' not in edgar_source


# ------------------------------------------------------- 13. no bypass


def test_no_evidence_pool_bypass_exists_for_usgs_admissibility(tmp_path):
    import ast

    offenders = []
    for path in sorted((REPO_ROOT / "assertion").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name.startswith(("put_", "admit_")):
                offenders.append(f"{path.name}:{name}")
    assert offenders == []


# ------------------------------------------------------ 14. rejection metrics


def test_phase_27_28_metrics_are_unaffected_by_the_usgs_extension(tmp_path):
    recorded, _ = _acquire_usgs(tmp_path)
    metrics = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    assert metrics.accepted == 3
    assert metrics.terminal_refusals == 0
    assert metrics.attempts == 3
    assert metrics.rejection_rate == 0.0
    assert metrics.by_code == ()


def test_repeated_real_acquisition_produces_identical_admissibility_verdicts(tmp_path):
    first_recorded, first_pool = _acquire_usgs(tmp_path, started_at="2026-08-25T00:00:00Z")
    first = assess_pool(first_pool, first_recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    second_recorded, _ = _acquire_usgs(tmp_path, started_at="2026-08-26T00:00:00Z")
    second = assess_pool(
        first_pool, second_recorded.execution.id, canonical_assertion_quarantine_store(tmp_path)
    )

    assert first.candidates_examined == second.candidates_examined
    assert first.by_code == second.by_code
    assert first.rejection_rate == second.rejection_rate


def test_the_real_usgs_property_candidates_are_deterministically_ordered(tmp_path):
    recorded, pool = _acquire_usgs(tmp_path)
    a = property_candidates(pool, recorded.execution.id)
    b = property_candidates(pool, recorded.execution.id)
    assert a == b
    assert [c.observation_id for c in a] == sorted(c.observation_id for c in a)
