"""Phase F's single empirical proof: late-arriving incremental records
are already handleable with EXISTING primitives (opaque
`AcquisitionCheckpoint.position` + `AdapterBinding.advance_position` +
Phase A/B's existing content-addressed deduplication), via an
adapter-level "trailing safety window" idiom -- no change to
`daf.catalog.checkpoint`, `daf.orchestration.adapter_registry`, or
`daf.scheduling.runner` is exercised or required here.

Scenario: a source's sequence 5 is visible before sequences 3 and 4
(out-of-order delivery -- `timestamp/sequence == acquisition order`
cannot be assumed, per docs/DAF_DOMAIN_RECONNAISSANCE.md section 11).

- A NAIVE `advance_position` (`daf.orchestration.bindings`'s existing
  `incremental_dataset_binding`, unmodified) advances straight to the
  maximum sequence seen (5) and therefore permanently skips 3 and 4 once
  they do arrive, because the adapter filters strictly `sequence >
  since_sequence`.
- A SAFETY-WINDOW `advance_position` -- built here, entirely in test
  code, from the exact same existing `AdapterBinding` shape -- instead
  advances to `max_sequence_seen - SAFETY_WINDOW`, so the next run
  re-requests a trailing margin. The late arrivals are captured; the
  already-seen records in that margin come back as ordinary,
  already-proven-safe duplicates (Phase A/B), never re-admitted twice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from daf.adapters.incremental_dataset import IncrementalDatasetSourceAdapter, sequence_of, locator_for
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.extractors.local_dataset import LocalDatasetExtractor
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.bindings import incremental_dataset_binding
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.result import AcquiredArtifact, AcquisitionOutcome
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).parent / "fixtures"
SAFETY_WINDOW = 3


def _growing_dataset(tmp_path):
    """One dataset file that GROWS, which is what a real incremental
    source is. Phase S made the dataset path part of the artifact
    locator, so simulating growth with two DIFFERENT fixture paths would
    now (correctly) describe two different datasets -- and record 5 would
    be two distinct records, hence two Observations. Copying each fixture
    over a single path keeps this test about what it is actually about:
    late-arriving sequences and cursor behaviour."""
    dataset = tmp_path / "readings.json"

    def grow_to(fixture_name):
        dataset.write_text((FIXTURES / fixture_name).read_text())
        return dataset

    return dataset, grow_to


def _safety_window_advance_position(
    artifacts: Tuple[AcquiredArtifact, ...], previous_position: Optional[str]
) -> Optional[str]:
    """The idiom docs/DAF_DOMAIN_RECONNAISSANCE.md section 11 describes --
    entirely a binding-level choice, using the SAME AdapterBinding shape
    Phase E already defined."""
    if not artifacts:
        return previous_position
    max_sequence = max(sequence_of(a.locator) for a in artifacts)
    if previous_position is not None:
        max_sequence = max(max_sequence, sequence_of(previous_position))
    return locator_for(max(0, max_sequence - SAFETY_WINDOW))


def _safety_window_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> IncrementalDatasetSourceAdapter:
        path = Path(str(request.parameters["path"]))
        since = request.parameters.get("since")
        since_sequence = sequence_of(str(since)) if since is not None else None
        return IncrementalDatasetSourceAdapter(
            path=path, source_name=source.name, retrieved_at=request.requested_at, since_sequence=since_sequence
        )

    return AdapterBinding(
        adapter_id="incremental-dataset-safety-window",
        build_adapter=build_adapter,
        build_extractor=LocalDatasetExtractor,
        advance_position=_safety_window_advance_position,
    )


def _setup(adapter_id: str, binding: AdapterBinding, tmp_path: Path):
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(binding)
    sources.register(
        SourceDefinition(
            source_id="readings", name="readings", domain="test-only", adapter_id=adapter_id, capabilities=("incremental",)
        )
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    return sources, adapters, pool, checkpoints


def test_naive_advance_position_permanently_loses_late_arriving_records(tmp_path):
    sources, adapters, pool, checkpoints = _setup("incremental-dataset", incremental_dataset_binding(), tmp_path)

    dataset, grow_to = _growing_dataset(tmp_path)
    grow_to("late_arrival_initial.json")
    initial_plan = AcquisitionPlan(
        plan_id="readings-plan", source_id="readings",
        parameters={"path": str(dataset)}, mode="incremental",
    )
    first = execute_plan(initial_plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")
    # Phase S: the locator now carries the dataset path, so assert on the
    # sequences it still yields -- which is what this test is actually about.
    assert {sequence_of(a.locator) for a in first.artifacts} == {1, 2, 5}
    assert checkpoints.get("readings-plan").position == "000000000005"  # naive: jumps straight to the max

    # Sequences 3 and 4 arrive late.
    grow_to("late_arrival_extended.json")
    grown_plan = AcquisitionPlan(
        plan_id="readings-plan", source_id="readings",
        parameters={"path": str(dataset)}, mode="incremental",
    )
    second = execute_plan(grown_plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    # since_sequence=5 -- sequences 3 and 4 are BOTH <= 5, so the adapter
    # never even returns them. Permanently lost, exactly as documented.
    assert second.artifacts == ()
    assert len(pool.all_observations()) == 3  # only ever the original 3 records


def test_safety_window_advance_position_captures_late_arriving_records(tmp_path):
    sources, adapters, pool, checkpoints = _setup(
        "incremental-dataset-safety-window", _safety_window_binding(), tmp_path
    )

    dataset, grow_to = _growing_dataset(tmp_path)
    grow_to("late_arrival_initial.json")
    initial_plan = AcquisitionPlan(
        plan_id="readings-plan", source_id="readings",
        parameters={"path": str(dataset)}, mode="incremental",
    )
    first = execute_plan(initial_plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")
    # Phase S: the locator now carries the dataset path, so assert on the
    # sequences it still yields -- which is what this test is actually about.
    assert {sequence_of(a.locator) for a in first.artifacts} == {1, 2, 5}
    # SAFETY_WINDOW=3 behind the max (5) -- position lags deliberately.
    assert checkpoints.get("readings-plan").position == "000000000002"

    grow_to("late_arrival_extended.json")
    grown_plan = AcquisitionPlan(
        plan_id="readings-plan", source_id="readings",
        parameters={"path": str(dataset)}, mode="incremental",
    )
    second = execute_plan(grown_plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    # since_sequence=2 -- re-fetches 3, 4, 5: the late arrivals are NEW,
    # and the already-seen 5 comes back as an ordinary, safe duplicate.
    assert second.outcome == AcquisitionOutcome.ACQUIRED
    newness_by_sequence = {sequence_of(a.locator): a.is_new for a in second.artifacts}
    assert newness_by_sequence == {
        3: True,
        4: True,
        5: False,  # already durably persisted -- not re-admitted, not duplicated
    }
    assert len(pool.all_observations()) == 5  # all five records now present, none lost, none duplicated
