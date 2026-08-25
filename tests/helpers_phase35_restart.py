"""Two-subcommand driver proving the Phase 34 condition representation
survives a REAL OS-process restart -- two separate `python3` invocations
sharing nothing but an on-disk storage directory.

    python3 tests/helpers_phase35_restart.py acquire <store_dir>
    python3 tests/helpers_phase35_restart.py analyze <store_dir>

WHY THIS EXISTS RATHER THAN `daf/storage/demo.py`. That module already
proves restart persistence for DOCUMENT/ARTIFACT identity, but it drives
the LIVE NETWORK arXiv path (its own test skips when the network is
unavailable) and it never inspects `Observation.content`. Phase 35 needs
the opposite of both: a deterministic, fixture-backed, no-network
acquisition, inspected at the CONTENT level, because the thing under test
is a content-embedded value (`conditions`). `demo.py` is not modified.

WHY A `tests/` HELPER RATHER THAN A NEW `daf/` MODULE. It is a test
harness, not a capability the fabric offers anyone -- adding a production
module for it would be exactly the unnecessary expansion Phase 35's scope
forbids. `tests/helpers_state_gap.py` is the established precedent for a
non-`test_`-prefixed helper module living here.

EVERYTHING BELOW THE FIXTURE BYTES IS THE REAL, UNMODIFIED PRODUCTION
PATH: the real binding, the real adapter, the real extractor, the real
`scout.pipeline.run_scout` admission, the real `ClassifiedPool`/
`FilesystemEvidenceStore` persistence, and the real vendored
`materials.analysis.analyze`. Only the bytes the adapter would have
fetched over the network are supplied from a committed fixture, which is
the same substitution every acquisition test in this repository makes.

OUTPUT CONTRACT. Each subcommand prints `key = value` lines. The keys
common to both subcommands MUST match exactly across the two processes;
that comparison is the test. `conditions_native_hash` is deliberately NOT
among them -- see `conditions_hashable` below and Phase 35's report.
"""

from __future__ import annotations

# ruff: isort: off
#
# IMPORT ORDER IS LOAD-BEARING HERE and must not be sorted. This is a
# standalone script, so unlike every test module it gets no `conftest.py`
# to bootstrap the vendored substrate first: `evidence`/`materials`/
# `retrieval`/`scout` live in the git submodule and only resolve once
# `daf._vendor.ensure_on_path()` has run. Both hops are done explicitly
# below -- repo root onto the path so `daf` itself imports, then
# `daf._vendor` to add the submodule -- before any vendored import.
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from daf import _vendor

_vendor.ensure_on_path()

from evidence.identity import content_hash
from materials.analysis import MaterialQuestion, analyze
from retrieval.engine import DeterministicRetrievalEngine

from assertion.property_admissibility import (
    assess_pool,
    canonical_assertion_quarantine_store,
)
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import RuntimeIdentity
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics.evidence_class import MEASURED

# ruff: isort: on

FIXTURES = REPO_ROOT / "tests" / "fixtures"
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()
STATION = "8454000"
DATUM = "MLLW"
POLICY_ID = "source_policy:phase35"

# Fixed so two processes derive byte-identical execution/plan identity.
RUNTIME = RuntimeIdentity(
    python_version="3.11.0", platform="linux-restart", hostname="restart-host", process_id=1
)
NOAA_PARAMETERS = {
    "station": STATION,
    "product": "water_level",
    "start_date": "20240115",
    "end_date": "20240115",
}


def _pool(store_dir: Path) -> ClassifiedPool:
    """The SAME construction in both processes. In `acquire` this opens
    an empty store; in `analyze` it opens an already-populated one, which
    is precisely the hydration path Phase 34 measured as the one that
    reconstructs content from `json.loads`."""
    return ClassifiedPool(
        FilesystemEvidenceStore(store_dir),
        SourceClassPolicy(id=POLICY_ID, by_source_kind={"tide-station-window": MEASURED}),
    )


def _content_fingerprint(content) -> str:
    """Deliberately `content_hash`, never `hash()`: this must be stable
    across processes, and Python's native string hashing is not."""
    return content_hash({"content": dict(sorted(content.items()))})


def _report(pool: ClassifiedPool) -> None:
    """The keys that MUST agree across the restart boundary."""
    observations = sorted(pool.all_observations(), key=lambda o: o.id)
    first = observations[0]
    conditions = first.content["conditions"]

    print(f"observation_count = {len(observations)}")
    print(f"first_observation_id = {first.id}")
    print(f"all_observation_ids_digest = {content_hash([o.id for o in observations])}")
    print(f"content_fingerprint = {_content_fingerprint(first.content)}")
    print(f"content_keys = {sorted(first.content)}")
    print(f"conditions_type = {type(conditions).__name__}")
    print(f"conditions_items = {sorted(conditions.items())}")
    print(f"conditions_is_mapping = {isinstance(conditions, __import__('collections.abc', fromlist=['Mapping']).Mapping)}")
    # The VALUE of hash() is process-local (Python randomizes string
    # hashing per interpreter); the fact that hashing SUCCEEDS is the
    # invariant that must survive restart, so only that is reported.
    try:
        hash(conditions)
        hashable = True
    except TypeError:
        hashable = False
    print(f"conditions_hashable = {hashable}")
    print(f"conditions_immutable = {_is_immutable(conditions)}")
    print(f"pool_fingerprint = {pool.fingerprint()}")


def _is_immutable(conditions) -> bool:
    try:
        conditions["__probe__"] = 1
    except TypeError:
        return True
    return False


def _analysis_report(pool: ClassifiedPool) -> None:
    """The real, vendored consumer -- no mock, no bypass of
    `_comparison_context`."""
    answer = analyze(
        pool,
        DeterministicRetrievalEngine(),
        MaterialQuestion(material_natural_key=STATION, property="water_level"),
    )
    groups = answer.observed_comparison_groups
    print(f"analysis_observed_count = {len(answer.observed)}")
    print(f"analysis_group_count = {len(groups)}")
    print(f"analysis_group_datums = {sorted({dict(g.context)['conditions']['datum'] for g in groups})}")
    print(f"analysis_disagreement = {answer.observed_disagreement}")


def _admissibility_report(pool: ClassifiedPool, execution_id: str, root: Path) -> None:
    report = assess_pool(pool, execution_id, canonical_assertion_quarantine_store(root))
    print(f"admissibility_examined = {report.candidates_examined}")
    print(f"admissibility_accepted = {report.accepted}")
    print(f"admissibility_refused = {report.refused}")
    print(f"admissibility_by_code = {sorted(report.by_code.items())}")


def _acquire(store_dir: Path) -> None:
    root = store_dir.parent
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="noaa-cm",
            name="NOAA CO-OPS Tides & Currents",
            domain="environmental-observations",
            adapter_id="noaa-water-level-measurements",
            required_parameters=("station", "product", "start_date", "end_date"),
            capabilities=("incremental",),
        )
    )
    adapters = AdapterRegistry()
    adapters.register(
        noaa_water_level_measurement_binding(
            datum=DATUM, units="metric", fetch_bytes=lambda url: MLLW_BYTES
        )
    )
    pool = _pool(store_dir)
    recorded = execute_plan_recorded(
        AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-cm", parameters=dict(NOAA_PARAMETERS)),
        sources,
        adapters,
        pool,
        CheckpointStore(root / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
        executions=ExecutionRecordStore(root),
        quarantine=QuarantineStore(root),
        runtime=RUNTIME,
    )
    print(f"outcome = {recorded.result.outcome.value}")
    print(f"execution_id = {recorded.execution.id}")
    _report(pool)
    _analysis_report(pool)
    _admissibility_report(pool, recorded.execution.id, root / "acquire_assess")


def _analyze(store_dir: Path) -> None:
    """A BRAND NEW process, a brand new pool object, nothing shared with
    `acquire` but the bytes on disk."""
    root = store_dir.parent
    pool = _pool(store_dir)
    executions = ExecutionRecordStore(root).all_records()
    execution_id = min(record.id for record in executions)
    print("outcome = acquired")
    print(f"execution_id = {execution_id}")
    _report(pool)
    _analysis_report(pool)
    _admissibility_report(pool, execution_id, root / "analyze_assess")


def main(argv) -> int:
    if len(argv) != 3 or argv[1] not in ("acquire", "analyze"):
        print(__doc__)
        return 2
    store_dir = Path(argv[2])
    if argv[1] == "acquire":
        _acquire(store_dir)
    else:
        _analyze(store_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
