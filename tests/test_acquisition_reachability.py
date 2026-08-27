"""Every verdict in architecture/acquisition_reachability.yaml, re-executed.

A reachability record whose verdicts are read rather than run is a list of
claims. These tests plant the violations again, on the real path, and
check the codes by name.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sys
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import GpcReportSourceAdapter  # noqa: E402
from daf.adapters.gpc_summary_export import GpcSummaryExportSourceAdapter  # noqa: E402
from daf.extractors.gpc_report import GpcReportExtractionError, GpcReportExtractor  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from science.admissibility import no_context_free_property, quantity_is_typed  # noqa: E402
from science.replicate_pairing import covariance_of, pair_replicates  # noqa: E402
from science.structured_uncertainty import uncertainty_corresponds_to_value  # noqa: E402
from science.table import observation_is_table_alignable  # noqa: E402
from scout.interface import RawDocument  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "acquisition_reachability.yaml").read_text())
FIXTURES = REPO_ROOT / "tests" / "fixtures"
F1 = FIXTURES / "gpc_report_synthetic_ps4471.json"
F2 = FIXTURES / "gpc_summary_export_synthetic_vendor.csv"
WHEN = "2026-08-27T00:00:00Z"
DECL = dict(data_provenance="fabricated_fixture", sample_kind="sample", method="m",
            unit_by_column={"Mw": "g/mol", "PDI": "dimensionless"},
            kind_by_column={"Mw": "measured", "PDI": "derived"})


def _codes(observations):
    codes = set()
    for o in observations:
        for gate in (observation_is_table_alignable, quantity_is_typed,
                     no_context_free_property, uncertainty_corresponds_to_value):
            codes |= set(gate(o.content).reasons)
    codes |= {c for c, _ in pair_replicates(observations).refusals}
    for r in covariance_of(observations):
        codes |= set(r.reasons)
        if r.covariance is not None:
            codes |= set(r.covariance.reasons)
    return codes


def acquire_source_1(mutate=None):
    """Plant in the FIXTURE and run the real path. Returns (codes, error)."""
    report = json.loads(F1.read_text())
    if mutate:
        mutate(report)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(report, fh, allow_nan=True)
        path = pathlib.Path(fh.name)
    try:
        pool = EvidencePool()
        run_scout(GpcReportSourceAdapter(path=path, source_name="s", retrieved_at=WHEN),
                  GpcReportExtractor(), pool)
        return _codes(sorted(pool.all_observations(), key=lambda o: o.id)), None
    except Exception as exc:                      # noqa: BLE001 -- the point is which one
        return set(), f"{type(exc).__name__}"
    finally:
        path.unlink(missing_ok=True)


def acquire_source_2():
    pool = EvidencePool()
    run_scout(GpcSummaryExportSourceAdapter(path=F2, source_name="s", retrieved_at=WHEN, **DECL),
              GpcReportExtractor(), pool)
    return sorted(pool.all_observations(), key=lambda o: o.id)


def _each(fn):
    def mutate(report):
        for run in report["runs"]:
            for measurement in run["measurements"]:
                fn(measurement)
    return mutate


# =====================================================================
# The reachable ten, re-planted
# =====================================================================

REACHABLE_PLANTS = {
    "CONDITION_KEYS_ARE_NOT_IDENTIFIERS": lambda r: r["conditions"].__setitem__("", "x"),
    "CONDITION_KEY_SHADOWS_AN_IDENTITY": lambda r: r["conditions"].__setitem__("sample_id", "x"),
    "MISSING_UNCERTAINTY": _each(lambda m: (m.__setitem__("uncertainty", None),
                                            m.__setitem__("uncertainty_kind", "stated"))),
    "UNKNOWN_UNCERTAINTY_KIND": _each(lambda m: m.__setitem__("uncertainty_kind", "guessed")),
    "RAGGED_REPLICATE_SET": lambda r: r["runs"][0].__setitem__(
        "measurements", r["runs"][0]["measurements"][:1]),
    "TOO_FEW_RUNS_FOR_A_COVARIANCE": lambda r: r.__setitem__("runs", r["runs"][:1]),
    "DEGENERATE_VARIABLE": _each(lambda m: m.__setitem__("value", 100000.0)),
    "TOO_FEW_VARIABLES_FOR_A_CORRELATION": lambda r: [
        run.__setitem__("measurements", run["measurements"][:1]) for run in r["runs"]],
    "EVERY_RUN_DIFFERS_IN": lambda r: [
        run.__setitem__("conditions", dict(r["conditions"], injection_sequence=i))
        for i, run in enumerate(r["runs"])],
}


@pytest.mark.parametrize("code", sorted(REACHABLE_PLANTS))
def test_a_reachable_code_fires_from_a_plant_in_the_fixture(code):
    """REACHABLE means the violation travelled the path the real data
    takes. Named, never counted."""
    assert code in RECORD["reachable"]["codes"], f"{code} is not recorded reachable"
    fired, error = acquire_source_1(REACHABLE_PLANTS[code])
    assert error is None, (
        f"the plant for {code} tripped {error} before reaching the gate -- MALFORMED, not a hit"
    )
    assert code in fired, f"planted for {code}, fired {sorted(fired)}"


def test_conflicting_value_for_a_run_is_reachable_via_one_record_per_report():
    """The tenth. Its route is a different Record granularity rather than
    a content mutation."""
    report = json.loads(F1.read_text())
    payload = {k: report[k] for k in
               ("data_provenance", "sample_id", "sample_kind", "method", "conditions")}
    payload["acquisition_declared"] = ""
    payload["measurements"] = [m for run in report["runs"] for m in run["measurements"]
                               if m["kind"] == "measured"]

    @dataclasses.dataclass(frozen=True)
    class _OnePerReport:
        def fetch(self):
            return (RawDocument(source_name="s", source_kind="instrument_report",
                                content=json.dumps(payload, sort_keys=True, allow_nan=False),
                                locator="x#report", retrieval_method="r", retrieved_at=WHEN),)

    pool = EvidencePool()
    run_scout(_OnePerReport(), GpcReportExtractor(), pool)
    codes = {c for c, _ in pair_replicates(list(pool.all_observations())).refusals}
    assert "CONFLICTING_VALUE_FOR_A_RUN" in codes


def test_the_reachable_set_is_exactly_ten_and_matches_the_record():
    assert len(RECORD["reachable"]["codes"]) == RECORD["summary"]["reachable_from_acquisition"] == 10


# =====================================================================
# SILENT, and reported as silent
# =====================================================================

def test_the_counts_reconcile_to_every_code():
    """A partial accounting is not a measurement."""
    s = RECORD["summary"]
    assert (s["reachable_from_acquisition"]
            + s["unreachable_pre_empted_by_an_earlier_refusal"]
            + s["unreachable_because_content_cannot_express_the_violation"]
            + s["unreachable_by_pipeline_construction"]) == s["codes_total"] == 42


def test_ambiguous_run_identity_is_unreachable_by_a_traced_line_not_by_nobody_finding_one():
    pipeline = (REPO_ROOT / "vendor" / "scout-retrieval-agent" / "scout" / "pipeline.py").read_text()
    assert "record_ids=(record.id,)" in pipeline, (
        "the vendored pipeline no longer builds exactly one Record per observation; "
        "AMBIGUOUS_RUN_IDENTITY may now be reachable and the verdict needs re-measuring"
    )
    fired, _ = acquire_source_1()
    assert "AMBIGUOUS_RUN_IDENTITY" not in fired


def test_the_absence_vocabulary_is_entirely_unexercised_by_acquisition():
    """SILENT, not clean. No acquisition path emits `value_absence`, so
    every code guarding it reports zero for a reason that is not a
    measurement."""
    for observations in (acquire_source_2(), ):
        assert all("value_absence" not in o.content for o in observations)
    fired, _ = acquire_source_1()
    assert not ({"UNKNOWN_ABSENCE_REASON", "VALUE_AND_ABSENCE_BOTH_PRESENT"} & fired)


def test_clean_data_fires_nothing_on_source_1_and_exactly_one_code_on_source_2():
    """The only non-zero count in the measurement, and it is real."""
    fired1, error1 = acquire_source_1()
    assert error1 is None and fired1 == set()
    fired2 = _codes(acquire_source_2())
    assert fired2 == {"TOO_FEW_VARIABLES_FOR_A_CORRELATION"}


# =====================================================================
# The three items WO-3 added
# =====================================================================

def test_the_drop_set_is_derived_and_every_member_is_excluded_by_name():
    """§1.1. Derived by running both adapters -- a new adapter key fails
    this until it is carried or excluded with a reason."""
    declared = set(RECORD["the_drop_set"]) - {
        "what_was_asked", "measured", "the_property_asserted"}

    adapters = [
        GpcReportSourceAdapter(path=F1, source_name="s", retrieved_at=WHEN),
        GpcSummaryExportSourceAdapter(path=F2, source_name="s", retrieved_at=WHEN, **DECL),
    ]
    for adapter in adapters:
        emitted, measurement_keys = set(), set()
        for document in adapter.fetch():
            payload = json.loads(document.content)
            emitted |= set(payload)
            for m in payload.get("measurements", []):
                measurement_keys |= set(m)
        emitted = (emitted - {"measurements"}) | measurement_keys

        pool = EvidencePool()
        run_scout(adapter, GpcReportExtractor(), pool)
        carried = set()
        for o in pool.all_observations():
            carried |= set(o.content)

        dropped = emitted - carried
        assert dropped == declared, (
            f"the drop set moved to {sorted(dropped)}; the record declares {sorted(declared)}. "
            "A key dropped without a declared reason is a summarisation loss at the boundary that "
            "produced three of them already."
        )


def test_a_caller_declared_field_is_recoverable_from_a_pooled_observation():
    """§1.2. The difference between declaring and fabricating is that a
    consumer can tell -- verified by reading one back, with no adapter."""
    declared = {f.strip() for f in acquire_source_2()[0].content["acquisition_declared"].split(",")}
    assert declared == {"data_provenance", "measurement_kind", "method", "sample_kind", "unit"}

    pool = EvidencePool()
    run_scout(GpcReportSourceAdapter(path=F1, source_name="s", retrieved_at=WHEN),
              GpcReportExtractor(), pool)
    source_stated = next(iter(pool.all_observations()))
    assert source_stated.content["acquisition_declared"] == "", (
        "a source that states everything must say so EXPLICITLY. With the key absent, it is "
        "indistinguishable from an adapter that never reported what it declared -- "
        "absence-as-signal, which is the vacuous-pass shape inside the discriminator itself."
    )


def test_the_undeclared_kind_refusal_is_reachable_with_a_planted_violation():
    """§1.3. It replaced an enumeration that was silently failing, so a
    REACHABLE verdict backed by a plant is the evidence the repair is real
    rather than a rename."""
    _, error = acquire_source_1(_each(lambda m: m.pop("kind")))
    assert error == "GpcReportExtractionError"
    _, error_derived = acquire_source_1(_each(lambda m: m.__setitem__("kind", "derived")))
    assert error_derived == "GpcReportExtractionError"


def test_the_verified_measurement_kind_is_not_recorded_anywhere():
    """The drop-set finding that is more than bookkeeping: the extractor
    verifies the class and nothing carries the result."""
    from evidence.types import Observation

    assert "evidence_class" not in Observation.__dataclass_fields__
    pipeline = (REPO_ROOT / "vendor" / "scout-retrieval-agent" / "scout" / "pipeline.py").read_text()
    assert "EvidenceClassAssignment" not in pipeline
    for o in acquire_source_2():
        assert "kind" not in o.content
    assert "nothing records the result" in RECORD["the_drop_set"]["kind"]["the_part_worth_stating"]

    # CORRECTED IN PHASE A. The first two clauses hold; the third --
    # "this path does not use ClassifiedPool" -- described the harness,
    # not the path, and the correction must stay attached to the claim.
    assert "misattributed" in RECORD["the_drop_set"]["kind"]["corrected_in_phase_a"]


def test_the_self_check_limit_and_the_sibling_number_are_both_stated():
    assert "weakest evidence shape" in RECORD["the_self_check_limit"]
    assert "sharing a misreading" in RECORD["the_self_check_limit"]

    sibling = loads((REPO_ROOT / "vendor" / "scout-retrieval-agent" / "architecture"
                     / "chemistry_reachability.yaml").read_text())["summary"]
    assert sibling["exercised_by_real_acquisition"] == 0, (
        "the sibling's probe now reports acquisition reaching a chemistry gate; that is its "
        "finding to report and this record must be re-measured against it"
    )
    assert "has not re-run the probe" in RECORD["not_daqs_number"]
