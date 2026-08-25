"""Phase R: the four identities NOAA acquisition produces, and why they
must stay distinct.

Phase 17 measured a real collision: for one station/product/window, NOAA
returns scientifically different quantities under different vertical
datums (MLLW 0.136 m vs STND 1.2 m at the same instant), but the locator
encoded only `station:product:begin:end`, so both collapsed onto one
logical artifact and the second read as a REVISION of the first.

THE IDENTITY CHAIN, as actually computed (not as described):

    source.id     = H({kind, name})                    <- adapter-fixed
    document.id   = H({source_id, H(raw_content),      <- VERSION identity
                       retrieval_method})
    record.locator= "station:product:datum:units:begin:end"
    artifact_id   = H({source_id, locator})            <- LOGICAL ARTIFACT
    cursor        = window_end_of(locator)             <- ACQUISITION CURSOR
                  = locator.rsplit(":", 1)[-1]
    observation.id= H(content incl. datum/unit/time)   <- SCIENTIFIC MEASUREMENT

For MLLW vs STND before Phase R: `source.id` identical (adapter hard-codes
name/kind), `raw_content` different so `document.id` differed correctly,
`observation.id` differed correctly (datum is in content) -- and
`artifact_id` was IDENTICAL. Exactly one of the four identities was
wrong, which is why the fix is one locator, not a new identity layer.

THE FIX is `datum`/`units` in the locator. That COMPLETES the existing
scheme rather than introducing a new coupling -- the locator already
carried `station` and `product`, scientific identity dimensions of
exactly the same kind. The cursor is untouched because `window_end_of`
reads the LAST component, and checkpoint positions are bare date strings,
never locators. Both are asserted below rather than assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daf.adapters.noaa_water_level import NoaaWaterLevelSourceAdapter, window_end_of
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.artifact_store import ArtifactNotFoundError, ArtifactStore
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore
from daf.storage.identity import compute_artifact_id
from daf.storage.metadata_index import MetadataIndex

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()
STND_BYTES = (FIXTURES / "noaa_live_8454000_20240115_stnd.json").read_bytes()

STATION = "8454000"
PARAMETERS = {
    "station": STATION, "product": "water_level",
    "start_date": "20240115", "end_date": "20240115",
}


def _acquire(root, payload=MLLW_BYTES, datum="MLLW", units="metric", pool=None, parameters=None):
    pool = pool if pool is not None else DurablePool(FilesystemEvidenceStore(root / "evidence"))
    sources = SourceRegistry()
    sources.register(SourceDefinition(
        source_id="noaa-cm", name="NOAA CO-OPS Tides & Currents",
        domain="environmental-observations", adapter_id="noaa-water-level-measurements",
        required_parameters=("station", "product", "start_date", "end_date"),
        capabilities=("incremental",),
    ))
    adapters = AdapterRegistry()
    adapters.register(noaa_water_level_measurement_binding(
        datum=datum, units=units, fetch_bytes=lambda url: payload,
    ))
    plan = AcquisitionPlan(
        plan_id="noaa-cm-plan", source_id="noaa-cm",
        parameters=dict(parameters if parameters is not None else PARAMETERS),
    )
    result = execute_plan(
        plan, sources, adapters, pool, CheckpointStore(root / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
    )
    return pool, result


def _one(values):
    distinct = set(values)
    assert len(distinct) == 1, f"expected a single distinct value, got {sorted(distinct)}"
    return next(iter(distinct))


# --------------------------------------------------------------------
# 1. The collision is gone: MLLW -> identity A, STND -> identity B
# --------------------------------------------------------------------

def test_different_datums_produce_different_logical_artifact_identities(tmp_path):
    """The stop condition. Same station, same product, same window, same
    source -- different vertical datum, therefore a different logical
    artifact."""
    pool, mllw = _acquire(tmp_path / "s", MLLW_BYTES, datum="MLLW")
    _, stnd = _acquire(tmp_path / "s", STND_BYTES, datum="STND", pool=pool)

    assert _one(a.locator for a in mllw.artifacts) == f"{STATION}:water_level:MLLW:metric:20240115:20240115"
    assert _one(a.locator for a in stnd.artifacts) == f"{STATION}:water_level:STND:metric:20240115:20240115"
    assert _one(a.artifact_id for a in mllw.artifacts) != _one(a.artifact_id for a in stnd.artifacts)

    # both are genuinely acquired, neither mistaken for a revision of the other
    assert mllw.outcome.value == "acquired" and stnd.outcome.value == "acquired"
    assert all(a.is_new for a in stnd.artifacts)


def test_units_are_part_of_identity_for_the_same_reason_as_datum(tmp_path):
    """`units` is the second quantity dimension the locator omitted. Two
    acquisitions differing only in declared units are different acquired
    objects, even for identical bytes."""
    metric = NoaaWaterLevelSourceAdapter(
        station=STATION, product="water_level", start_date="20240115", end_date="20240115",
        retrieved_at="2026-08-25T00:00:00Z", datum="MLLW", units="metric",
        fetch_bytes=lambda url: MLLW_BYTES,
    ).fetch()[0]
    english = NoaaWaterLevelSourceAdapter(
        station=STATION, product="water_level", start_date="20240115", end_date="20240115",
        retrieved_at="2026-08-25T00:00:00Z", datum="MLLW", units="english",
        fetch_bytes=lambda url: MLLW_BYTES,
    ).fetch()[0]

    assert metric.locator != english.locator
    assert compute_artifact_id("src", metric.locator) != compute_artifact_id("src", english.locator)


# --------------------------------------------------------------------
# 2/3. Duplicate and revision semantics survive unchanged
# --------------------------------------------------------------------

def test_same_datum_reacquisition_is_still_a_duplicate(tmp_path):
    """The identity fix must not turn re-acquisition into new evidence."""
    pool, first = _acquire(tmp_path / "d", MLLW_BYTES, datum="MLLW")
    observation_ids = sorted(o.id for o in pool.all_observations())

    _, again = _acquire(tmp_path / "d", MLLW_BYTES, datum="MLLW", pool=pool)
    assert again.outcome.value == "duplicate"
    assert _one(a.artifact_id for a in first.artifacts) == _one(a.artifact_id for a in again.artifacts)
    assert _one(a.version_id for a in first.artifacts) == _one(a.version_id for a in again.artifacts)
    assert sorted(o.id for o in pool.all_observations()) == observation_ids


def test_same_quantity_with_changed_content_is_a_new_version_not_a_new_artifact(tmp_path):
    """Revision semantics: NOAA re-issues a window as its QC pipeline
    flips readings from preliminary to verified. Same station, product,
    datum, units and window -- changed bytes -- must stay ONE logical
    artifact with a new version.

    The revised payload is the real MLLW response with one real reading's
    value altered; the transition itself is not fabricated as NOAA data,
    it is a controlled second version used only to exercise the identity
    mechanism."""
    original = json.loads(MLLW_BYTES.decode())
    revised = json.loads(MLLW_BYTES.decode())
    revised["data"][0]["v"] = "0.140"
    revised["data"][0]["q"] = "v"
    revised_bytes = json.dumps(revised).encode()

    pool, first = _acquire(tmp_path / "r", MLLW_BYTES, datum="MLLW")
    _, second = _acquire(tmp_path / "r", revised_bytes, datum="MLLW", pool=pool)

    assert original["data"][0]["v"] != revised["data"][0]["v"]
    assert _one(a.artifact_id for a in first.artifacts) == _one(a.artifact_id for a in second.artifacts), (
        "same logical artifact"
    )
    assert _one(a.version_id for a in first.artifacts) != _one(a.version_id for a in second.artifacts), (
        "distinct version"
    )

    artifact_store = ArtifactStore(pool.store)
    versions = artifact_store.list_versions(_one(a.artifact_id for a in first.artifacts))
    assert len(versions) == 2, "both versions retained; history is not overwritten"
    assert set(versions) == {
        _one(a.version_id for a in first.artifacts), _one(a.version_id for a in second.artifacts)
    }


# --------------------------------------------------------------------
# 4. Cursor / checkpoint semantics are untouched
# --------------------------------------------------------------------

def test_the_acquisition_cursor_is_unaffected_by_the_richer_locator():
    """`window_end_of` reads the LAST locator component, so inserting
    quantity dimensions before the dates cannot move the cursor. This is
    the constraint that made extending the locator viable at all."""
    assert window_end_of(f"{STATION}:water_level:MLLW:metric:20240115:20240117") == "20240117"
    assert window_end_of(f"{STATION}:water_level:STND:english:20240115:20240117") == "20240117"
    # the pre-Phase-R shape still parses identically -- the parser never
    # depended on a fixed component count
    assert window_end_of(f"{STATION}:water_level:20240115:20240117") == "20240117"


def test_checkpoint_advances_and_restart_resumes_across_the_new_locator(tmp_path):
    """Checkpoint positions are bare date strings, never locators, so the
    richer locator changes nothing about advancement or restart."""
    root = tmp_path / "cursor"
    checkpoints = CheckpointStore(root / "checkpoints")
    pool, first = _acquire(root, MLLW_BYTES, datum="MLLW")

    position = checkpoints.get("noaa-cm-plan").position
    assert position == "20240115", "a bare date, carrying no quantity dimension"
    assert window_end_of(_one(a.locator for a in first.artifacts)) == position

    # restart: a fresh pool and a fresh checkpoint store over the same directories
    restarted_pool = DurablePool(FilesystemEvidenceStore(root / "evidence"))
    assert CheckpointStore(root / "checkpoints").get("noaa-cm-plan").position == position
    assert sorted(o.id for o in restarted_pool.all_observations()) == sorted(
        o.id for o in pool.all_observations()
    )


# --------------------------------------------------------------------
# 5/7/8. Storage: ArtifactStore and MetadataIndex agree with the result
# --------------------------------------------------------------------

def test_artifact_store_and_metadata_index_resolve_the_new_identities(tmp_path):
    """`artifact_id` is derived, never a stored authority: ArtifactStore
    RECOMPUTES it from the Document's source_id and its Record's locator.
    MetadataIndex stores it, but only as an index -- `rebuild()`
    regenerates it from the store. Both must agree with what acquisition
    reported, for both datums."""
    pool, mllw = _acquire(tmp_path / "st", MLLW_BYTES, datum="MLLW")
    _, stnd = _acquire(tmp_path / "st", STND_BYTES, datum="STND", pool=pool)
    artifact_store = ArtifactStore(pool.store)

    for result in (mllw, stnd):
        artifact_id = _one(a.artifact_id for a in result.artifacts)
        version_id = _one(a.version_id for a in result.artifacts)

        document = artifact_store.get(artifact_id, version_id)
        assert document.id == version_id
        assert artifact_store._locator_for(document) == _one(a.locator for a in result.artifacts)
        assert artifact_store.list_versions(artifact_id) == (version_id,)

    # the two artifacts are separately addressable, and neither resolves
    # under the other's identity
    mllw_id = _one(a.artifact_id for a in mllw.artifacts)
    stnd_version = _one(a.version_id for a in stnd.artifacts)
    with pytest.raises(ArtifactNotFoundError, match="not a version of artifact"):
        artifact_store.get(mllw_id, stnd_version)

    index = MetadataIndex(pool.store.root / "index.sqlite3")
    index.rebuild(pool.store)
    for result in (mllw, stnd):
        artifact_id = _one(a.artifact_id for a in result.artifacts)
        assert index.list_versions(artifact_id) == (_one(a.version_id for a in result.artifacts),), (
            "a rebuilt index derives exactly the identities acquisition reported"
        )


# --------------------------------------------------------------------
# 6/9/10. The other three identities are unchanged by the fix
# --------------------------------------------------------------------

def test_observation_identity_is_independent_of_artifact_identity(tmp_path):
    """Scientific measurement identity is content-addressed over
    Observation.content and never consulted the locator -- it already
    separated MLLW from STND before Phase R, and is unchanged by it."""
    pool, _ = _acquire(tmp_path / "o", MLLW_BYTES, datum="MLLW")
    _, _ = _acquire(tmp_path / "o", STND_BYTES, datum="STND", pool=pool)

    by_datum = {}
    for observation in pool.all_observations():
        by_datum.setdefault(observation.content["datum"], []).append(observation)
    assert set(by_datum) == {"MLLW", "STND"}
    assert len(by_datum["MLLW"]) == len(by_datum["STND"]) == 240

    mllw_ids = {o.id for o in by_datum["MLLW"]}
    assert not (mllw_ids & {o.id for o in by_datum["STND"]}), "no observation identity is shared"

    # same reading, two datums, same instant -> different measurements
    mllw_first = next(o for o in by_datum["MLLW"] if o.content["measurement_time"] == "2024-01-15 00:00")
    stnd_first = next(o for o in by_datum["STND"] if o.content["measurement_time"] == "2024-01-15 00:00")
    assert mllw_first.content["value"] == 0.136 and stnd_first.content["value"] == 1.2
    assert mllw_first.id != stnd_first.id


def test_version_identity_still_tracks_content_not_quantity(tmp_path):
    """`document.id` = H({source_id, H(raw_content), retrieval_method}).
    It never consulted the locator, so identical bytes acquired under two
    different datums still share a version id -- while now correctly
    belonging to two different artifacts. This is precisely why version
    and artifact identity must not be the same key."""
    pool, mllw = _acquire(tmp_path / "v", MLLW_BYTES, datum="MLLW")
    _, same_bytes_other_datum = _acquire(tmp_path / "v", MLLW_BYTES, datum="STND", pool=pool)

    assert _one(a.version_id for a in mllw.artifacts) == _one(
        a.version_id for a in same_bytes_other_datum.artifacts
    ), "version identity is a function of content alone"
    assert _one(a.artifact_id for a in mllw.artifacts) != _one(
        a.artifact_id for a in same_bytes_other_datum.artifacts
    ), "artifact identity is a function of what was asked for"


def test_the_scientific_comparison_context_is_not_how_the_fix_works(tmp_path):
    """Phase 17 established that `datum` is a genuine scientific
    conditioning variable in Observation.content. The identity fix must
    not have been achieved by moving it out of content, nor made
    redundant by it -- acquisition identity and comparison context are
    separate concepts that happen to agree here."""
    pool, _ = _acquire(tmp_path / "c", MLLW_BYTES, datum="MLLW")
    _, _ = _acquire(tmp_path / "c", STND_BYTES, datum="STND", pool=pool)

    for observation in pool.all_observations():
        assert observation.content["datum"] in {"MLLW", "STND"}
        assert "locator" not in observation.content, (
            "acquisition identity never leaks into scientific content"
        )
