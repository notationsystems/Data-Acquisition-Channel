"""Concrete AdapterBinding factories for the DAF's sources.

This is deliberately the ONE module in `daf.orchestration` allowed to
import `daf.adapters.*`/`daf.extractors.*` -- `daf.orchestration.orchestrator`
itself never does (see its own docstring and the AST-level proof in
tests/test_acquisition_orchestrator.py). Adding a new source means adding
one function here, never touching the orchestrator.
"""

from __future__ import annotations

import datetime
import inspect
import json
from pathlib import Path
from typing import Optional, Tuple

from evidence.identity import content_hash

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.adapters.edgar_daily_index import EdgarDailyIndexSourceAdapter
from daf.adapters.incremental_dataset import IncrementalDatasetSourceAdapter, locator_for, sequence_of
from daf.adapters.local_dataset import LocalDatasetSourceAdapter
from daf.adapters.noaa_water_level import Fetcher, NoaaWaterLevelSourceAdapter, window_end_of
from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
from daf.extractors.arxiv import ArxivExtractor
from daf.extractors.edgar_daily_index import EdgarDailyIndexExtractor
from daf.extractors.graph_dataset import GraphDatasetExtractor
from daf.extractors.local_dataset import LocalDatasetExtractor
from daf.extractors.noaa_water_level import NoaaWaterLevelExtractor
from daf.extractors.noaa_water_level_measurements import NoaaWaterLevelMeasurementExtractor
from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor
from daf.orchestration.adapter_registry import AdapterBinding
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.result import AcquiredArtifact
from daf.orchestration.source_registry import SourceDefinition


def _code_version(*types: type) -> str:
    """The adapter version, DERIVED from the code that will run rather
    than declared as a string someone must remember to bump.

    Hashing the adapter's and extractor's own module source means the
    version changes exactly when the acquisition behaviour can change,
    and is identical on two machines running the same checkout -- which
    is what makes it usable in an execution record. Nothing is invented:
    if a binding declares no version, `AdapterBinding.version` stays
    `None` and the execution record says so explicitly."""
    sources = {}
    for t in types:
        path = inspect.getsourcefile(t)
        if path is None:
            raise ValueError(f"{t!r} has no Python source file; its version cannot be derived")
        sources[t.__module__] = Path(path).read_text()
    return content_hash(sources)


def arxiv_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> ArxivSourceAdapter:
        arxiv_ids = tuple(request.parameters["arxiv_ids"])
        return ArxivSourceAdapter(arxiv_ids=arxiv_ids, retrieved_at=request.requested_at)

    return AdapterBinding(
        adapter_id="arxiv",
        build_adapter=build_adapter,
        build_extractor=ArxivExtractor,
        version=_code_version(ArxivSourceAdapter, ArxivExtractor),
    )


def local_dataset_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> LocalDatasetSourceAdapter:
        path = Path(str(request.parameters["path"]))
        return LocalDatasetSourceAdapter(
            path=path, source_name=source.name, retrieved_at=request.requested_at
        )

    return AdapterBinding(
        adapter_id="local-dataset",
        build_adapter=build_adapter,
        build_extractor=LocalDatasetExtractor,
        version=_code_version(LocalDatasetSourceAdapter, LocalDatasetExtractor),
    )


def graph_dataset_binding() -> AdapterBinding:
    """Same file-of-JSON-records acquisition shape as
    `local_dataset_binding` -- deliberately the SAME unmodified
    `LocalDatasetSourceAdapter`, since nothing about acquisition differs.
    The only difference is the extractor: `GraphDatasetExtractor` reads
    the trust-graph structure each record declares about itself, so the
    admitted evidence carries referents/relationships and is therefore
    reachable by `materials.analysis`/`materials.iteration`. See that
    extractor's docstring for why no other DAF source does this."""

    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> LocalDatasetSourceAdapter:
        path = Path(str(request.parameters["path"]))
        return LocalDatasetSourceAdapter(
            path=path, source_name=source.name, retrieved_at=request.requested_at
        )

    return AdapterBinding(
        adapter_id="graph-dataset",
        build_adapter=build_adapter,
        build_extractor=GraphDatasetExtractor,
        version=_code_version(LocalDatasetSourceAdapter, GraphDatasetExtractor),
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
        version=_code_version(IncrementalDatasetSourceAdapter, LocalDatasetExtractor),
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
        version=_code_version(EdgarDailyIndexSourceAdapter, EdgarDailyIndexExtractor),
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
        version=_code_version(UsgsEarthquakeSourceAdapter, UsgsEarthquakeExtractor),
    )


def _advance_noaa_position(
    artifacts: Tuple[AcquiredArtifact, ...], previous_position: Optional[str]
) -> Optional[str]:
    """NOAA's window locator
    (`"{station}:{product}:{datum}:{units}:{begin}:{end}"`)
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
        version=_code_version(NoaaWaterLevelSourceAdapter, NoaaWaterLevelExtractor),
    )


def noaa_water_level_measurement_binding(
    *, datum: str = "MLLW", units: str = "metric", fetch_bytes: Optional[Fetcher] = None
) -> AdapterBinding:
    """The same unmodified `NoaaWaterLevelSourceAdapter` as
    `noaa_water_level_binding`, paired instead with the per-measurement,
    graph-declaring extractor so acquired readings reach
    `materials.analysis`. Both bindings are kept: the window-shaped one
    answers "what did this window contain", this one "what individual
    measurements were made".

    `datum`/`units` are accepted HERE, once, and handed to BOTH the
    adapter (which puts them in the request URL) and the extractor (which
    records them as scientific context). The response body echoes
    neither, so this is the only place the two can be kept consistent --
    `BuildExtractor` is a zero-argument factory and cannot read the
    request itself. Passing them separately to each would allow an
    adapter/extractor disagreement that no test could easily catch: every
    value silently labelled with a datum it was not measured against.

    `fetch_bytes` is the adapter's OWN existing injection point, surfaced
    here so a caller can replay a recorded real response instead of
    hitting the live service; omitted, the adapter's live HTTP default is
    used unchanged.

    RESOLVED IN PHASE R (docs/PHASE_18_NOAA_ARTIFACT_IDENTITY.md): making
    `datum`/`units` configurable here first exposed a real identity
    collision, since `ArtifactStore.artifact_id` keys on
    `(source_id, locator)` and the locator encoded only
    `station:product:begin:end`. Two scientifically different quantities
    (measured live: MLLW 0.136 m vs STND 1.2 m at the same instant)
    therefore shared one logical artifact, and the second read as a
    REVISION of the first. `NoaaWaterLevelSourceAdapter` now includes
    both dimensions in the locator, so distinct quantities are distinct
    artifacts. No caller constraint remains."""

    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> NoaaWaterLevelSourceAdapter:
        since = request.parameters.get("since")
        station = str(request.parameters["station"])
        product = str(request.parameters["product"])
        start_date = str(request.parameters["start_date"])
        end_date = str(request.parameters["end_date"])
        since_window_end = str(since) if since is not None else None

        # Written out twice rather than assembled as **kwargs so mypy
        # actually checks the call: the adapter's `fetch_bytes` default is
        # its live HTTP fetcher, which must stay in place when none is
        # injected -- passing None would disable acquisition entirely.
        if fetch_bytes is None:
            return NoaaWaterLevelSourceAdapter(
                station=station, product=product, start_date=start_date, end_date=end_date,
                retrieved_at=request.requested_at, since_window_end=since_window_end,
                datum=datum, units=units,
            )
        return NoaaWaterLevelSourceAdapter(
            station=station, product=product, start_date=start_date, end_date=end_date,
            retrieved_at=request.requested_at, since_window_end=since_window_end,
            datum=datum, units=units, fetch_bytes=fetch_bytes,
        )

    def build_extractor() -> NoaaWaterLevelMeasurementExtractor:
        return NoaaWaterLevelMeasurementExtractor(datum=datum, units=units)

    return AdapterBinding(
        adapter_id="noaa-water-level-measurements",
        build_adapter=build_adapter,
        build_extractor=build_extractor,
        advance_position=_advance_noaa_position,
        version=_code_version(NoaaWaterLevelSourceAdapter, NoaaWaterLevelMeasurementExtractor),
    )
