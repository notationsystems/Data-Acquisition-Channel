"""Phase S: the acquisition-identity invariant, expressed once and
checked against every registered adapter.

THE INVARIANT, in three executable rules (they are separate claims and
each is asserted separately below):

  R1  SEPARATION -- if two acquisitions can represent DISTINCT logical
      external source objects, their artifact identities must not
      collide.

  R2  REVISION -- if two acquisitions represent the SAME logical source
      object with different retrieved content, they must share an
      artifact identity and receive different version identities.

  R3  CURSOR INDEPENDENCE -- the acquisition cursor must remain
      recoverable without depending on the rest of the locator. A cursor
      MAY be embedded in a locator; that is a source-specific
      implementation relationship, never an architectural identity.

WHY THIS FILE EXISTS RATHER THAN A RUNTIME ABSTRACTION. Two adapters have
now failed R1 in the same way -- NOAA (Phase R: `datum`/`units` absent
from the locator) and `incremental_dataset` (Phase S: the dataset `path`
absent). Both were payload-varying REQUEST parameters missing from the
logical artifact's name. That recurrence justifies stating the rule once
and checking it everywhere; it does NOT justify a generic runtime
identity framework, because deciding which request parameters vary a
payload requires source knowledge that exists only inside each adapter.
`compute_artifact_id(source_id, locator) = H({source_id, locator})` is
already the correct generic rule -- the two defects were adapters NAMING
their objects wrongly, not the rule being wrong. So the contract is
enforced here, as tests, and each fix stayed source-specific.

IDENTITY IS COMPUTED HERE EXACTLY AS PRODUCTION COMPUTES IT (`_identity`
below mirrors `scout.pipeline.run_scout` + `orchestrator.py:146`), so
these tests exercise adapters directly and stay fast, while the
end-to-end acquisition path is covered by each source's own suite and by
tests/test_noaa_artifact_identity.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from evidence.types import make_document, make_source
from materials.analysis import MaterialQuestion, analyze
from retrieval.engine import DeterministicRetrievalEngine

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.adapters.edgar_daily_index import EdgarDailyIndexSourceAdapter
from daf.adapters.incremental_dataset import (
    IncrementalDatasetSourceAdapter,
    document_locator_for,
    locator_for,
    sequence_of,
)
from daf.adapters.local_dataset import LocalDatasetSourceAdapter
from daf.adapters.noaa_water_level import NoaaWaterLevelSourceAdapter, window_end_of
from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.artifact_store import ArtifactStore
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore
from daf.storage.identity import compute_artifact_id
from daf.storage.metadata_index import MetadataIndex

FIXTURES = Path(__file__).resolve().parent / "fixtures"
AT = "2026-08-25T00:00:00Z"
STATION = "8454000"
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()
STND_BYTES = (FIXTURES / "noaa_live_8454000_20240115_stnd.json").read_bytes()


def _router(routes: Dict[str, bytes]):
    def _fetch(url: str) -> bytes:
        for suffix, content in routes.items():
            if url.endswith(suffix):
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return _fetch


def _identity(raw_document):
    """The production identity computation, reproduced exactly:
    `run_scout` derives the evidence Source from the RawDocument's
    kind/name, `make_document` derives the version id from the content,
    and the orchestrator derives the artifact id from source + locator."""
    source = make_source(kind=raw_document.source_kind, name=raw_document.source_name)
    document = make_document(
        source_id=source.id, raw_content=raw_document.content,
        retrieval_method=raw_document.retrieval_method, retrieved_at=raw_document.retrieved_at,
    )
    return compute_artifact_id(source.id, raw_document.locator), document.id


def _assert_separated(a, b, what):
    """R1: distinct logical objects, distinct artifact identities."""
    artifact_a, version_a = _identity(a)
    artifact_b, version_b = _identity(b)
    assert a.locator != b.locator, f"{what}: locators must differ"
    assert artifact_a != artifact_b, f"{what}: artifact identities must not collide"
    assert version_a != version_b, f"{what}: differing content implies differing versions"


def _assert_same_artifact_new_version(a, b, what):
    """R2: same logical object, changed content."""
    artifact_a, version_a = _identity(a)
    artifact_b, version_b = _identity(b)
    assert a.locator == b.locator, f"{what}: the same object keeps its locator"
    assert artifact_a == artifact_b, f"{what}: the same object keeps its artifact identity"
    assert version_a != version_b, f"{what}: changed content must be a new version"


# ====================================================================
# EDGAR  (matrix rows 1, 2)
# ====================================================================

def _edgar(routes, **kwargs):
    return EdgarDailyIndexSourceAdapter(
        year=2026, quarter=3, retrieved_at=AT, fetch_bytes=_router(routes), **kwargs
    ).fetch()


_EDGAR_ROUTES = {
    "index.json": (FIXTURES / "edgar_index_listing_synthetic.json").read_bytes(),
    "company.20260701.idx": (FIXTURES / "edgar_daily_index_synthetic_20260701.idx").read_bytes(),
    "company.20260702.idx": (FIXTURES / "edgar_daily_index_synthetic_20260702.idx").read_bytes(),
    "company.20260703.idx": (FIXTURES / "edgar_daily_index_synthetic_20260703.idx").read_bytes(),
}


def test_edgar_separates_artifacts_by_date():
    """R1. EDGAR's logical object is one daily index file; the date names
    it completely, and a date belongs to exactly one year/quarter."""
    documents = _edgar(_EDGAR_ROUTES)
    by_date = {d.locator: d for d in documents}
    assert set(by_date) == {"20260701", "20260702", "20260703"}
    _assert_separated(by_date["20260701"], by_date["20260702"], "EDGAR distinct dates")


def test_edgar_same_date_with_changed_bytes_is_a_new_version_of_one_artifact():
    """R2. SEC republishing a daily index must not create a second
    logical artifact."""
    original = _edgar(_EDGAR_ROUTES)[0]
    revised_routes = dict(_EDGAR_ROUTES)
    revised_routes["company.20260701.idx"] = (
        _EDGAR_ROUTES["company.20260701.idx"] + b"\nEXTRA CORP  10-K  0001234567  20260701  edgar/data/x.txt\n"
    )
    revised = _edgar(revised_routes)[0]
    _assert_same_artifact_new_version(original, revised, "EDGAR republished index")


# ====================================================================
# USGS  (matrix rows 3, 4) -- the important counterexample
# ====================================================================

_USGS_ROUTES = {
    "&limit=500": (FIXTURES / "usgs_listing_synthetic.json").read_bytes(),
    "eventid=synth00000001&format=geojson": (FIXTURES / "usgs_event_detail_synth00000001.json").read_bytes(),
    "eventid=synth00000002&format=geojson": (FIXTURES / "usgs_event_detail_synth00000002.json").read_bytes(),
    "eventid=synth00000003&format=geojson": (FIXTURES / "usgs_event_detail_synth00000003.json").read_bytes(),
}


def _usgs(routes, **kwargs):
    return UsgsEarthquakeSourceAdapter(
        start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
        retrieved_at=AT, fetch_bytes=_router(routes), **kwargs
    ).fetch()


def test_usgs_keeps_one_artifact_identity_across_a_real_revision():
    """R2, and the counterexample that keeps R1 honest. A USGS event is
    revised in place: same stable event id, changed content, changed
    `properties.updated`. Revision state must NOT become part of artifact
    identity -- otherwise every correction would fork a new artifact and
    the event's history would be unfollowable."""
    original = {d.locator: d for d in _usgs(_USGS_ROUTES)}["synth00000001"]

    revised_routes = dict(_USGS_ROUTES)
    revised_routes["eventid=synth00000001&format=geojson"] = (
        FIXTURES / "usgs_event_detail_synth00000001_revised.json"
    ).read_bytes()
    revised = {d.locator: d for d in _usgs(revised_routes)}["synth00000001"]

    assert json.loads(original.content)["properties"]["updated"] != (
        json.loads(revised.content)["properties"]["updated"]
    ), "the fixture really is a revision"
    _assert_same_artifact_new_version(original, revised, "USGS revised event")


def test_usgs_separates_distinct_events_and_ignores_filter_parameters():
    """R1, plus the reason USGS never had NOAA's defect:
    `min_magnitude`/`start_time`/`end_time` select WHICH events are
    returned, they do not change what event X contains. They are
    therefore correctly absent from the locator -- a payload-varying
    parameter at the result-set level is not an identity dimension of an
    individual artifact."""
    documents = {d.locator: d for d in _usgs(_USGS_ROUTES)}
    _assert_separated(documents["synth00000001"], documents["synth00000002"], "USGS distinct events")

    wider = UsgsEarthquakeSourceAdapter(
        start_time="2026-01-01", end_time="2026-01-02", min_magnitude=0.1,
        retrieved_at=AT, fetch_bytes=_router(_USGS_ROUTES),
    ).fetch()
    widened = {d.locator: d for d in wider}["synth00000001"]
    assert _identity(widened) == _identity(documents["synth00000001"]), (
        "a different filter must not re-identify the same event"
    )


# ====================================================================
# NOAA  (matrix rows 5, 6, 7, 8, 9)
# ====================================================================

def _noaa(payload, **kwargs):
    defaults = {
        "station": STATION, "product": "water_level",
        "start_date": "20240115", "end_date": "20240115",
        "retrieved_at": AT, "fetch_bytes": lambda url: payload,
    }
    defaults.update(kwargs)
    return NoaaWaterLevelSourceAdapter(**defaults).fetch()[0]


def test_noaa_separates_artifacts_by_datum_and_by_product():
    """R1, rows 5 and 6. Both dimensions are real request parameters that
    change what NOAA returns for one station and window."""
    _assert_separated(
        _noaa(MLLW_BYTES, datum="MLLW"), _noaa(STND_BYTES, datum="STND"), "NOAA distinct datums"
    )
    # product: same bytes replayed, so only the locator dimension differs
    water_level = _noaa(MLLW_BYTES, product="water_level")
    hourly = _noaa(MLLW_BYTES, product="hourly_height")
    assert water_level.locator != hourly.locator
    assert _identity(water_level)[0] != _identity(hourly)[0], "distinct products, distinct artifacts"
    assert _identity(water_level)[1] == _identity(hourly)[1], (
        "identical bytes still share a version id -- which is exactly why artifact "
        "identity and version identity must not be the same key"
    )


def test_noaa_time_zone_is_not_an_identity_dimension():
    """Row 7, and Phase R's explicitly deferred question, answered from
    the code rather than speculation: `time_zone` is a hard-coded URL
    literal (`&time_zone=gmt`), not a field of the adapter. It cannot
    vary between acquisitions, so it cannot produce two payloads under
    one identity, and adding it to the locator would be speculative."""
    source = (Path(__file__).resolve().parent.parent / "daf/adapters/noaa_water_level.py").read_text()
    assert "time_zone=gmt" in source, "the literal this conclusion rests on"
    assert not any(
        line.strip().startswith("time_zone") for line in source.splitlines()
    ), "time_zone must not be a configurable adapter field"

    fields = NoaaWaterLevelSourceAdapter.__dataclass_fields__
    assert "time_zone" not in fields
    assert {"datum", "units", "station", "product"} <= set(fields), (
        "every dimension that IS configurable is in the locator (asserted above)"
    )


def test_noaa_reacquisition_and_revision_keep_one_artifact(tmp_path):
    """Rows 8 and 2-for-NOAA: identical bytes are the same artifact AND
    the same version; changed bytes for the same window are the same
    artifact with a new version."""
    first = _noaa(MLLW_BYTES, datum="MLLW")
    again = _noaa(MLLW_BYTES, datum="MLLW")
    assert _identity(first) == _identity(again), "re-acquisition is not new evidence"

    revised = json.loads(MLLW_BYTES.decode())
    revised["data"][0]["v"] = "0.140"
    _assert_same_artifact_new_version(
        first, _noaa(json.dumps(revised).encode(), datum="MLLW"), "NOAA revised window"
    )


def test_noaa_cursor_survives_the_richer_locator():
    """R3, row 9. The cursor is the last locator component and checkpoint
    positions are bare dates -- neither depends on how many quantity
    dimensions precede them."""
    assert window_end_of(_noaa(MLLW_BYTES, datum="STND", units="english").locator) == "20240115"
    assert window_end_of(f"{STATION}:water_level:20240115:20240117") == "20240117", (
        "the parser never depended on a fixed component count"
    )


# ====================================================================
# incremental_dataset / local_dataset / arXiv  (matrix row 10)
# ====================================================================

def _dataset(tmp_path, name, records):
    path = tmp_path / name
    path.write_text(json.dumps(records))
    return path


def test_incremental_dataset_separates_artifacts_by_dataset_path(tmp_path):
    """R1 -- the collision Phase S reproduced and fixed. Two different
    dataset files acquired under ONE registered source both contained a
    record with sequence 1; a bare sequence locator made them one
    artifact, so the second read as a revision of the first."""
    a = _dataset(tmp_path, "stream_a.json", [{"sequence": 1, "id": "r1", "reading": "AAA"}])
    b = _dataset(tmp_path, "stream_b.json", [{"sequence": 1, "id": "r1", "reading": "BBB"}])

    doc_a = IncrementalDatasetSourceAdapter(path=a, source_name="Dataset", retrieved_at=AT).fetch()[0]
    doc_b = IncrementalDatasetSourceAdapter(path=b, source_name="Dataset", retrieved_at=AT).fetch()[0]
    _assert_separated(doc_a, doc_b, "incremental_dataset distinct files")


def test_incremental_dataset_same_record_revised_in_place_is_one_artifact(tmp_path):
    """R2. The real incremental scenario -- ONE dataset file whose record
    is corrected -- must stay one artifact with a new version."""
    path = _dataset(tmp_path, "stream.json", [{"sequence": 1, "id": "r1", "reading": "AAA"}])
    original = IncrementalDatasetSourceAdapter(path=path, source_name="Dataset", retrieved_at=AT).fetch()[0]
    path.write_text(json.dumps([{"sequence": 1, "id": "r1", "reading": "CORRECTED"}]))
    revised = IncrementalDatasetSourceAdapter(path=path, source_name="Dataset", retrieved_at=AT).fetch()[0]
    _assert_same_artifact_new_version(original, revised, "incremental_dataset in-place revision")


def test_incremental_dataset_cursor_is_recoverable_from_both_shapes(tmp_path):
    """R3. `locator_for` remains the CHECKPOINT POSITION format (a bare
    padded sequence) while `document_locator_for` names the artifact.
    `sequence_of` reads the last `#` component, so it handles both -- the
    same discipline as NOAA's `window_end_of`."""
    path = _dataset(tmp_path, "stream.json", [{"sequence": 7, "id": "r7"}])
    document = IncrementalDatasetSourceAdapter(path=path, source_name="Dataset", retrieved_at=AT).fetch()[0]

    assert document.locator == document_locator_for(path, 7)
    assert sequence_of(document.locator) == 7, "cursor recoverable from a full locator"
    assert sequence_of(locator_for(7)) == 7, "and from a bare checkpoint position"
    assert locator_for(7) == "000000000007", "the position format is unchanged"
    assert "#" not in locator_for(7), "a checkpoint position carries no dataset identity"


def test_local_dataset_and_arxiv_already_satisfy_the_invariant(tmp_path):
    """R1 for the two adapters that never had the defect.
    `local_dataset` already put its `path` in the locator -- the very
    precedent `incremental_dataset` should have followed. arXiv's only
    request dimension is WHICH ids to fetch, and its locator is the
    entry's own id, so no parameter can vary what a given entry
    contains."""
    a = _dataset(tmp_path, "a.json", [{"id": "r1", "reading": "AAA"}])
    b = _dataset(tmp_path, "b.json", [{"id": "r1", "reading": "BBB"}])
    _assert_separated(
        LocalDatasetSourceAdapter(path=a, source_name="DS", retrieved_at=AT).fetch()[0],
        LocalDatasetSourceAdapter(path=b, source_name="DS", retrieved_at=AT).fetch()[0],
        "local_dataset distinct files",
    )

    entries = ArxivSourceAdapter(
        arxiv_ids=("2401.00001", "2401.00002"), retrieved_at=AT,
        fetch_bytes=lambda url: (FIXTURES / "arxiv_two_entries.xml").read_bytes(),
    ).fetch()
    assert len(entries) == 2
    _assert_separated(entries[0], entries[1], "arXiv distinct entries")

    original = ArxivSourceAdapter(
        arxiv_ids=("2401.00001",), retrieved_at=AT,
        fetch_bytes=lambda url: (FIXTURES / "arxiv_single_entry_v1.xml").read_bytes(),
    ).fetch()[0]
    revised = ArxivSourceAdapter(
        arxiv_ids=("2401.00001",), retrieved_at=AT,
        fetch_bytes=lambda url: (FIXTURES / "arxiv_single_entry_v1_revised.xml").read_bytes(),
    ).fetch()[0]
    _assert_same_artifact_new_version(original, revised, "arXiv revised entry")


# ====================================================================
# Storage and scientific boundary  (matrix rows 11-15)
# ====================================================================

def _acquire_noaa(root, payload, datum, pool=None):
    pool = pool if pool is not None else DurablePool(FilesystemEvidenceStore(root / "evidence"))
    sources = SourceRegistry()
    sources.register(SourceDefinition(
        source_id="noaa-cm", name="NOAA CO-OPS Tides & Currents",
        domain="environmental-observations", adapter_id="noaa-water-level-measurements",
        required_parameters=("station", "product", "start_date", "end_date"), capabilities=("incremental",),
    ))
    adapters = AdapterRegistry()
    adapters.register(noaa_water_level_measurement_binding(
        datum=datum, units="metric", fetch_bytes=lambda url: payload,
    ))
    plan = AcquisitionPlan(
        plan_id="noaa-cm-plan", source_id="noaa-cm",
        parameters={"station": STATION, "product": "water_level",
                    "start_date": "20240115", "end_date": "20240115"},
    )
    return pool, execute_plan(
        plan, sources, adapters, pool, CheckpointStore(root / "checkpoints"), requested_at=AT
    )


def test_storage_resolves_both_artifacts_after_restart_and_index_rebuild(tmp_path):
    """Rows 11, 12, 13. ArtifactStore lookup after restart, MetadataIndex
    rebuild, and DurablePool fingerprint equivalence -- all across two
    artifacts that used to collide."""
    root = tmp_path / "store"
    pool, mllw = _acquire_noaa(root, MLLW_BYTES, "MLLW")
    _, stnd = _acquire_noaa(root, STND_BYTES, "STND", pool=pool)
    fingerprint_before = pool.fingerprint()
    observation_ids = sorted(o.id for o in pool.all_observations())

    expected = {
        next(iter({a.artifact_id for a in result.artifacts})):
            next(iter({a.version_id for a in result.artifacts}))
        for result in (mllw, stnd)
    }
    assert len(expected) == 2, "two distinct artifacts"

    # --- restart: fresh pool over the same on-disk store ---------------
    restarted = DurablePool(FilesystemEvidenceStore(root / "evidence"))
    assert sorted(o.id for o in restarted.all_observations()) == observation_ids
    assert restarted.fingerprint() == fingerprint_before, "fingerprint survives restart"

    artifact_store = ArtifactStore(restarted.store)
    for artifact_id, version_id in expected.items():
        assert artifact_store.get(artifact_id, version_id).id == version_id
        assert artifact_store.list_versions(artifact_id) == (version_id,)

    index = MetadataIndex(restarted.store.root / "index.sqlite3")
    index.rebuild(restarted.store)
    for artifact_id, version_id in expected.items():
        assert index.list_versions(artifact_id) == (version_id,), (
            "a rebuilt index derives exactly what acquisition reported"
        )


def test_scientific_identity_is_independent_of_acquisition_identity(tmp_path):
    """Rows 14 and 15. Observation identity and comparison context are
    computed from Observation.content alone -- they never consulted a
    locator, and none of Phase R's or Phase S's locator changes touched
    them."""
    root = tmp_path / "sci"
    pool, _ = _acquire_noaa(root, MLLW_BYTES, "MLLW")
    _, _ = _acquire_noaa(root, STND_BYTES, "STND", pool=pool)

    for observation in pool.all_observations():
        assert "locator" not in observation.content
        assert set(observation.content) == {
            "property", "value", "unit", "datum", "station_id", "measurement_time", "sigma",
            "uncertainty", "uncertainty_kind",
        }

    answer = analyze(
        pool, DeterministicRetrievalEngine(),
        MaterialQuestion(material_natural_key=STATION, property="water_level"),
    )
    assert len(answer.observed) == 480
    assert {dict(g.context)["datum"] for g in answer.observed_comparison_groups} == {"MLLW", "STND"}
    assert answer.observed_disagreement is None, (
        "unchanged from Phase Q: distinct measurement times are distinct quantities"
    )
