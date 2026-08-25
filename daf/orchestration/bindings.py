"""Concrete AdapterBinding factories for the DAF's sources.

This is deliberately the ONE module in `daf.orchestration` allowed to
import `daf.adapters.*`/`daf.extractors.*` -- `daf.orchestration.orchestrator`
itself never does (see its own docstring and the AST-level proof in
tests/test_acquisition_orchestrator.py). Adding a new source means adding
one function here, never touching the orchestrator.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Optional, Tuple

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.adapters.edgar_daily_index import EdgarDailyIndexSourceAdapter
from daf.adapters.incremental_dataset import IncrementalDatasetSourceAdapter, locator_for, sequence_of
from daf.adapters.local_dataset import LocalDatasetSourceAdapter
from daf.adapters.noaa_water_level import NoaaWaterLevelSourceAdapter, window_end_of
from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
from daf.extractors.arxiv import ArxivExtractor
from daf.extractors.edgar_daily_index import EdgarDailyIndexExtractor
from daf.extractors.local_dataset import LocalDatasetExtractor
from daf.extractors.noaa_water_level import NoaaWaterLevelExtractor
from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor
from daf.orchestration.adapter_registry import AdapterBinding
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.result import AcquiredArtifact
from daf.orchestration.source_registry import SourceDefinition


def arxiv_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> ArxivSourceAdapter:
        arxiv_ids = tuple(request.parameters["arxiv_ids"])
        return ArxivSourceAdapter(arxiv_ids=arxiv_ids, retrieved_at=request.requested_at)

    return AdapterBinding(adapter_id="arxiv", build_adapter=build_adapter, build_extractor=ArxivExtractor)


def local_dataset_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> LocalDatasetSourceAdapter:
        path = Path(str(request.parameters["path"]))
        return LocalDatasetSourceAdapter(
            path=path, source_name=source.name, retrieved_at=request.requested_at
        )

    return AdapterBinding(
        adapter_id="local-dataset", build_adapter=build_adapter, build_extractor=LocalDatasetExtractor
    )


def _advance_incremental_position(
    artifacts: Tuple[AcquiredArtifact, ...], previous_position: Optional[str]
) -> Optional[str]:
    if not artifacts:
        return previous_position  # nothing acquired this run -- position is unchanged, never regresses
    max_sequence = max(sequence_of(artifact.locator) for artifact in artifacts)
    if previous_position is not None:
        max_sequence = max(max_sequence, sequence_of(previous_position))
    return locator_for(max_sequence)


def incremental_dataset_binding() -> AdapterBinding:
    """Same underlying record shape/extractor as `local_dataset_binding`
    -- the only difference is genuine cursor support: `request.parameters["since"]`
    (a locator-shaped string, injected by `daf.scheduling.runner.execute_plan`
    from the plan's checkpoint) becomes `since_sequence`, and
    `advance_position` computes the next checkpoint position from what was
    actually acquired."""

    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> IncrementalDatasetSourceAdapter:
        path = Path(str(request.parameters["path"]))
        since = request.parameters.get("since")
        since_sequence = sequence_of(str(since)) if since is not None else None
        return IncrementalDatasetSourceAdapter(
            path=path, source_name=source.name, retrieved_at=request.requested_at, since_sequence=since_sequence
        )

    return AdapterBinding(
        adapter_id="incremental-dataset",
        build_adapter=build_adapter,
        build_extractor=LocalDatasetExtractor,
        advance_position=_advance_incremental_position,
    )


def _advance_edgar_position(
    artifacts: Tuple[AcquiredArtifact, ...], previous_position: Optional[str]
) -> Optional[str]:
    """EDGAR daily-index locators ARE the position (a YYYYMMDD date
    string) -- no adapter-specific decoding needed, unlike
    `incremental_dataset`'s zero-padded sequence numbers. No trailing
    safety window (Phase F's late-arrival idiom) is needed here: SEC
    publishes exactly one immutable file per business day, once -- see
    docs/DAF_EDGAR_ADAPTER.md's "Checkpoint semantics" section for why
    this source does not exhibit the late-arrival problem."""
    if not artifacts:
        return previous_position
    max_date = max(artifact.locator for artifact in artifacts)
    if previous_position is not None:
        max_date = max(max_date, previous_position)
    return max_date


def edgar_daily_index_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> EdgarDailyIndexSourceAdapter:
        year = int(request.parameters["year"])
        quarter = int(request.parameters["quarter"])
        since = request.parameters.get("since")
        return EdgarDailyIndexSourceAdapter(
            year=year,
            quarter=quarter,
            retrieved_at=request.requested_at,
            since_date=str(since) if since is not None else None,
        )

    return AdapterBinding(
        adapter_id="edgar-daily-index",
        build_adapter=build_adapter,
        build_extractor=EdgarDailyIndexExtractor,
        advance_position=_advance_edgar_position,
    )


def _iso8601_from_epoch_ms(epoch_ms: int) -> str:
    dt = datetime.datetime.fromtimestamp(epoch_ms / 1000, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _advance_usgs_position(
    artifacts: Tuple[AcquiredArtifact, ...], previous_position: Optional[str]
) -> Optional[str]:
    """USGS's incremental cursor is a "last revised" timestamp -- NOT the
    locator (a stable event id, unchanged across revisions). Unlike
    EDGAR/incremental_dataset, this value only exists inside each
    artifact's own raw content, never in its locator, which is exactly
    why Phase H added `AcquiredArtifact.raw_content` (see
    daf.orchestration.result and daf.orchestration.adapter_registry).
    Parses `properties.updated` (epoch milliseconds) from each acquired
    event's raw GeoJSON, converts to the same ISO-8601 string shape the
    adapter's own `updated_after` query parameter expects, and advances
    to the maximum revision time seen -- the same "never regress, fold
    in the previous position" shape as `_advance_edgar_position`, just
    reading content instead of locator."""
    if not artifacts:
        return previous_position
    max_updated_ms = max(json.loads(artifact.raw_content)["properties"]["updated"] for artifact in artifacts)
    max_position = _iso8601_from_epoch_ms(max_updated_ms)
    if previous_position is not None:
        max_position = max(max_position, previous_position)
    return max_position


def usgs_earthquakes_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> UsgsEarthquakeSourceAdapter:
        since = request.parameters.get("since")
        return UsgsEarthquakeSourceAdapter(
            start_time=str(request.parameters["starttime"]),
            end_time=str(request.parameters["endtime"]),
            min_magnitude=float(request.parameters["minmagnitude"]),
            retrieved_at=request.requested_at,
            updated_after=str(since) if since is not None else None,
        )

    return AdapterBinding(
        adapter_id="usgs-earthquakes",
        build_adapter=build_adapter,
        build_extractor=UsgsEarthquakeExtractor,
        advance_position=_advance_usgs_position,
    )


def _advance_noaa_position(
    artifacts: Tuple[AcquiredArtifact, ...], previous_position: Optional[str]
) -> Optional[str]:
    """NOAA's window locator (`"{station}:{product}:{begin}:{end}"`)
    carries its own cursor value -- the window's end date -- exactly
    like EDGAR's date-string locator and UNLIKE USGS's event-id locator
    (which needed Phase H's `raw_content` field because no cursor
    information could be recovered from the locator alone). Reading
    `.locator` here, not `.raw_content`, is a deliberate, empirically-
    grounded choice, not an oversight -- see
    docs/DAF_NOAA_WATER_LEVEL_ADAPTER.md."""
    if not artifacts:
        return previous_position
    max_end = max(window_end_of(artifact.locator) for artifact in artifacts)
    if previous_position is not None:
        max_end = max(max_end, previous_position)
    return max_end


def noaa_water_level_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> NoaaWaterLevelSourceAdapter:
        since = request.parameters.get("since")
        return NoaaWaterLevelSourceAdapter(
            station=str(request.parameters["station"]),
            product=str(request.parameters["product"]),
            start_date=str(request.parameters["start_date"]),
            end_date=str(request.parameters["end_date"]),
            retrieved_at=request.requested_at,
            since_window_end=str(since) if since is not None else None,
        )

    return AdapterBinding(
        adapter_id="noaa-water-level",
        build_adapter=build_adapter,
        build_extractor=NoaaWaterLevelExtractor,
        advance_position=_advance_noaa_position,
    )
