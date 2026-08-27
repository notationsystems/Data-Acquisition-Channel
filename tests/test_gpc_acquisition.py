"""The first acquisition path in this repository that reaches the
SCIENTIFIC gates -- and the detector proofs for the one precondition that
cannot be repaired after data exists.

WHAT IS AND IS NOT MEASURED HERE. There is no GPC instrument, no polymer
and no acquisition anywhere in reach of this repository. Every number
below is FABRICATED, is labelled `fabricated_fixture` in the content it
produces, and says nothing about any material. What is real is the PATH:
five runs enter as five Records, ten observations pass both scientific
gates, one replicate set comes out, and a correlation is reachable from
it. The rho this file asserts is a property of the fixture that was
written to produce it, not a measurement -- which is why it is asserted
against the value computed from the fixture's own numbers rather than
against a constant that would look like a finding.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import statistics
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import (DATA_PROVENANCE_KINDS,  # noqa: E402
                                     GpcReportFetchError, GpcReportSourceAdapter)
from daf.extractors.gpc_report import (GpcReportExtractionError,  # noqa: E402
                                       GpcReportExtractor)
from daf.storage.frozen_mapping import FrozenMapping  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from evidence.types import make_observation  # noqa: E402
from science.admissibility import no_context_free_property  # noqa: E402
from science.replicate_pairing import (CONFLICTING_VALUE_FOR_A_RUN,  # noqa: E402
                                       EVERY_RUN_DIFFERS_IN, covariance_of,
                                       pair_replicates)
from science.table import observation_is_table_alignable  # noqa: E402
from scout.interface import RawDocument  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
REPORT = FIXTURES / "gpc_report_synthetic_ps4471.json"
DERIVED_COLUMN = FIXTURES / "gpc_report_synthetic_derived_column.json"
UNLABELLED = FIXTURES / "gpc_report_synthetic_unlabelled_provenance.json"
WHEN = "2026-08-27T00:00:00Z"

MN = "number_average_molar_mass"
MW = "weight_average_molar_mass"


def adapter_for(path=REPORT):
    return GpcReportSourceAdapter(path=path, source_name="synthetic-gpc", retrieved_at=WHEN)


def acquire(path=REPORT):
    pool = EvidencePool()
    findings, failures = run_scout(adapter_for(path), GpcReportExtractor(), pool)
    return pool, findings, failures


def observations(path=REPORT):
    pool, _, _ = acquire(path)
    return sorted(pool.all_observations(), key=lambda o: o.id)


def fixture_correlation():
    """Recomputed from the fixture file itself, so the assertion tracks
    the fabricated data rather than restating a number."""
    report = json.loads(REPORT.read_text())
    columns = {MN: [], MW: []}
    for run in report["runs"]:
        for measurement in run["measurements"]:
            columns[measurement["variable"]].append(measurement["value"])
    a, b = columns[MN], columns[MW]
    mean_a, mean_b = statistics.fmean(a), statistics.fmean(b)
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / (len(a) - 1)
    return cov / (statistics.stdev(a) * statistics.stdev(b))


# =====================================================================
# The path exists
# =====================================================================

def test_one_record_per_run_not_one_per_report():
    """The irreversible precondition, discharged where it actually lives.
    `run_scout` builds exactly one Record per RawDocument, so this is the
    adapter's obligation and no extractor could satisfy it."""
    documents = adapter_for().fetch()
    report = json.loads(REPORT.read_text())
    assert len(documents) == len(report["runs"]) == 5

    pool, _, _ = acquire()
    records = {record_id for obs in pool.all_observations() for record_id in obs.record_ids}
    assert len(records) == 5, "five runs must be five Records"
    for obs in pool.all_observations():
        assert len(obs.record_ids) == 1, (
            "an observation naming more than one Record has no run, and pair_replicates "
            "refuses it as AMBIGUOUS_RUN_IDENTITY"
        )


def test_the_run_identifier_is_on_the_locator_and_never_in_content():
    documents = adapter_for().fetch()
    for document in documents:
        payload = json.loads(document.content)
        for key in ("run_id", "report_id", "id"):
            assert key not in payload, f"{key!r} is an acquisition locator and must not reach content"
        assert "#GPC-2026-0431/inj-" in document.locator

    for obs in observations():
        assert not {"run_id", "report_id", "id"} & set(obs.content)


def test_every_acquired_observation_passes_both_scientific_gates():
    """Neither gate has ever been pointed at content this repository
    produced. Both are now."""
    acquired = observations()
    assert len(acquired) == 10
    for obs in acquired:
        table = observation_is_table_alignable(obs.content)
        context = no_context_free_property(obs.content)
        assert table.admissible, f"table gate refused acquired content: {list(table.reasons)}"
        assert context.admissible, f"admissibility gate refused acquired content: {list(context.reasons)}"


def test_the_pairing_consumer_reaches_a_correlation():
    """Step five of the build order. The number is the FIXTURE's, not a
    material's -- see this module's docstring."""
    results = covariance_of(observations())
    assert len(results) == 1
    result = results[0]
    assert result.reasons == ()
    assert result.replicates is not None and result.covariance is not None
    assert result.replicates.variables == (MN, MW)
    assert len(result.replicates.run_ids) == 5

    index = {name: i for i, name in enumerate(result.replicates.variables)}
    rho = result.covariance.correlation[index[MN]][index[MW]]
    assert rho == pytest.approx(fixture_correlation(), abs=1e-12)
    assert 0.0 < abs(rho) < 1.0, (
        "a fixture producing rho = +-1 would exercise the path without exercising the pairing; "
        "architecture/polymer_vertical.yaml records that a degenerate design returns a confident "
        "number that is not a measurement"
    )


def test_the_acquired_evidence_is_reachable_as_a_referent():
    """Empty entities is what made every earlier DAF acquisition
    unreachable from `materials`. The sample identity here is the
    report's own, transported rather than invented."""
    pool, _, _ = acquire()
    referents = [(r.natural_key, r.kind) for r in pool.all_referents()]
    assert referents == [("PS-lot-4471", "sample")]


def test_conditions_arrive_as_a_frozen_mapping():
    """Precondition four of the readiness record: the one representation
    that satisfies the grouping and the table gate at once."""
    for obs in observations():
        assert isinstance(obs.content["conditions"], FrozenMapping)
        assert hash(obs.content["conditions"]) is not None


# =====================================================================
# Detector proofs -- plant the defect the check claims to catch
# =====================================================================

@dataclasses.dataclass(frozen=True)
class OneDocumentPerReportAdapter:
    """The irreversible precondition, violated. Deliberately written as a
    whole adapter rather than as a patched payload, because that is the
    shape the mistake actually takes: an author who reads a GPC report as
    one document."""

    path: pathlib.Path

    def fetch(self):
        report = json.loads(self.path.read_text())
        payload = {key: report[key] for key in
                   ("data_provenance", "sample_id", "sample_kind", "method", "conditions")}
        payload["measurements"] = [m for run in report["runs"] for m in run["measurements"]]
        return (RawDocument(
            source_name="synthetic-gpc", source_kind="instrument_report",
            content=json.dumps(payload, sort_keys=True, allow_nan=False),
            locator=f"{self.path}#{report['report_id']}",
            retrieval_method="file:gpc_report_v1", retrieved_at=WHEN),)


def test_one_record_per_report_is_loud_when_the_values_differ():
    """DETECTOR PROOF, first mode. Ten measurements land under ONE run, so
    the pairing sees a run claiming two values for one variable and
    refuses.

    MEASURED CORRECTION to this test's first draft, which asserted the
    observations would collapse to fewer than ten. They do not: Observation
    identity covers `content`, and `value` differs between runs, so all ten
    survive as distinct facts naming one Record. The collapse the readiness
    record describes needs EQUAL values -- which is the next test, and is
    the mode that stays silent."""
    pool = EvidencePool()
    run_scout(OneDocumentPerReportAdapter(REPORT), GpcReportExtractor(), pool)
    acquired = list(pool.all_observations())
    assert len(acquired) == 10
    assert len({record for obs in acquired for record in obs.record_ids}) == 1

    codes = {code for code, _ in pair_replicates(acquired).refusals}
    assert CONFLICTING_VALUE_FOR_A_RUN in codes, (
        "one Record per report must be refused by the pairing consumer, not summarised"
    )
    assert all(result.covariance is None for result in covariance_of(acquired)), (
        "no correlation may be produced from a pool whose runs cannot be told apart"
    )


def test_one_record_per_report_is_SILENT_when_the_values_agree():
    """DETECTOR PROOF, second mode, and the unrepairable one.

    This is the readiness record's own case run for real: five runs that
    report the SAME number from one Record are one observation, because
    identity is over (record_ids, extraction_method, content) and all
    three agree. Nothing raises, nothing is refused, and the replicate set
    is gone before any consumer sees it -- the estimated spread is not
    merely wrong, the members it was to be computed over never existed.
    Recorded here because the loud mode above could otherwise be read as
    covering the failure, and it covers only half of it."""
    report = json.loads(REPORT.read_text())
    for run in report["runs"]:
        for measurement in run["measurements"]:
            measurement["value"] = 100000.0 if measurement["variable"] == MN else 200000.0
            measurement["uncertainty"] = 1000.0
    twin = FIXTURES / "gpc_report_synthetic_one_record_identical_runs.json"
    twin.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    try:
        pool = EvidencePool()
        _, failures = run_scout(OneDocumentPerReportAdapter(twin), GpcReportExtractor(), pool)
        acquired = list(pool.all_observations())

        assert failures == (), "the loss is silent: nothing is refused at admission"
        assert len(acquired) == 2, (
            f"five replicates per variable collapsed to {len(acquired)} observations. This is the "
            "downward variance bias, and no code anywhere reports it"
        )
        assert pair_replicates(acquired).refusals == (), (
            "and the pairing has nothing to complain about -- one run reporting two variables once "
            "each is a well-formed, and entirely wrong, replicate set of size one"
        )

        # The same data through the real adapter keeps all five.
        correct = EvidencePool()
        run_scout(GpcReportSourceAdapter(path=twin, source_name="synthetic-gpc",
                                         retrieved_at=WHEN), GpcReportExtractor(), correct)
        assert len(list(correct.all_observations())) == 10
    finally:
        twin.unlink()


def test_a_run_identifier_in_content_is_refused_at_the_extractor():
    """DETECTOR PROOF, first line. The extractor asserts what the adapter
    already guarantees, because the failure is silent everywhere else."""
    documents = adapter_for().fetch()
    payload = json.loads(documents[0].content)
    payload["run_id"] = "inj-01"
    poisoned = dataclasses.replace(documents[0], content=json.dumps(payload, sort_keys=True))

    @dataclasses.dataclass(frozen=True)
    class _Adapter:
        def fetch(self):
            return (poisoned,)

    with pytest.raises(GpcReportExtractionError, match="acquisition locator"):
        run_scout(_Adapter(), GpcReportExtractor(), EvidencePool())


def test_a_run_identifier_in_content_would_otherwise_be_silent():
    """DETECTOR PROOF, second line: what the guard above is FOR. With the
    locator in content and no guard, nothing raises -- the pairing simply
    reports EVERY_RUN_DIFFERS_IN and, without that code, would report a
    pool of singletons indistinguishable from one genuine run."""
    poisoned = []
    for obs in observations():
        content = dict(obs.content)
        # The run identity is the Record; leaking it into content is
        # exactly what the adapter refuses to do.
        content["run_id"] = obs.record_ids[0]
        poisoned.append(make_observation(
            record_ids=obs.record_ids, extraction_method=obs.extraction_method,
            content=content, confidence=1.0, extracted_at=WHEN))

    pairing = pair_replicates(poisoned)
    codes = {code for code, _ in pairing.refusals}
    assert EVERY_RUN_DIFFERS_IN in codes, (
        "the leak must be named. If this ever stops firing, a run identifier in content is silent "
        "again and the precondition is back to being a sentence"
    )
    assert all(len(s.run_ids) == 1 for s in pairing.sets), (
        "every run its own single-member set -- the shape that looks like a pool holding one run"
    )


def test_a_condition_that_really_does_change_every_run_is_the_discriminating_case():
    """Without this, EVERY_RUN_DIFFERS_IN would be indistinguishable from
    `complain whenever there is more than one set`. A real condition with
    REPEATED levels -- five runs at two temperatures, three and two --
    must produce two genuine sets and no refusal.

    Split by RUN rather than by observation index: the two observations of
    one run must stay together, or the set is ragged and this measures a
    different thing. That was this test's first-draft defect."""
    runs = sorted({obs.record_ids[0] for obs in observations()})
    hot = set(runs[3:])
    built = []
    for obs in observations():
        content = dict(obs.content)
        content["conditions"] = FrozenMapping({
            **dict(content["conditions"]),
            "column_temperature_c": 45.0 if obs.record_ids[0] in hot else 35.0,
        })
        built.append(make_observation(
            record_ids=obs.record_ids, extraction_method=obs.extraction_method,
            content=content, confidence=1.0, extracted_at=WHEN))

    pairing = pair_replicates(built)
    assert pairing.refusals == (), f"a genuine condition must not be flagged: {pairing.refusals}"
    assert EVERY_RUN_DIFFERS_IN not in {code for code, _ in pairing.refusals}
    assert len(pairing.sets) == 2
    assert sorted(len(s.run_ids) for s in pairing.sets) == [2, 3]


def test_a_derived_column_is_refused_and_not_dropped():
    """Dispersity is Mw/Mn. architecture/evidence_class.yaml classes
    computed evidence as DerivedValue, and there is no path from
    Extractor to DerivedValue -- so emitting it here would assign it the
    measured class. Refused, so the omission is visible."""
    with pytest.raises(GpcReportExtractionError, match="computed from other reported quantities"):
        acquire(DERIVED_COLUMN)


def test_the_refusal_names_the_column_rather_than_the_record():
    with pytest.raises(GpcReportExtractionError) as excinfo:
        acquire(DERIVED_COLUMN)
    assert "dispersity" in str(excinfo.value)


def test_unlabelled_provenance_is_refused_at_the_adapter():
    """Fabricated numbers must not be able to enter the pool wearing the
    same shape as measured ones. Nothing is defaulted."""
    with pytest.raises(GpcReportFetchError, match="data_provenance"):
        adapter_for(UNLABELLED).fetch()


def test_the_provenance_label_travels_into_content():
    """A measured fact recorded only in prose is bound to nothing. This
    one is content-addressed with the numbers it labels."""
    for obs in observations():
        assert obs.content["data_provenance"] == "fabricated_fixture"
        assert obs.content["data_provenance"] in DATA_PROVENANCE_KINDS


def test_two_runs_reporting_the_same_number_stay_two_observations():
    """Distinctness rests entirely on the locator carrying the run id:
    make_document hashes only source/content/method, so two identical
    runs collapse to ONE Document, and only make_record's locator keeps
    them two Records."""
    report = json.loads(REPORT.read_text())
    for run in report["runs"]:
        for measurement in run["measurements"]:
            measurement["value"] = 100000.0 if measurement["variable"] == MN else 200000.0
            measurement["uncertainty"] = 1000.0
    twin = FIXTURES / "gpc_report_synthetic_identical_runs.json"
    twin.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    try:
        pool, _, _ = acquire(twin)
        acquired = list(pool.all_observations())
        assert len(acquired) == 10, (
            "identical runs that merge silently understate the spread, which is the overconfident "
            "direction"
        )
        assert len({d.id for d in pool.all_observations()}) == 10
    finally:
        twin.unlink()


def test_a_duplicate_run_id_within_a_report_is_refused():
    report = json.loads(REPORT.read_text())
    report["runs"][1]["run_id"] = report["runs"][0]["run_id"]
    duplicate = FIXTURES / "gpc_report_synthetic_duplicate_run_id.json"
    duplicate.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    try:
        with pytest.raises(GpcReportFetchError, match="twice"):
            adapter_for(duplicate).fetch()
    finally:
        duplicate.unlink()


# =====================================================================
# The gate relation nobody owns -- bound to a mechanism, not to prose
# =====================================================================

def test_the_two_science_gates_disagree_on_the_column_key():
    """MEASURED during this build. `observation_is_table_alignable`
    requires `variable`; `no_context_free_property` requires `property`
    and `method`. Neither mentions the other's key, and the content in
    architecture/polymer_acquisition_readiness.yaml's own tests -- which
    that record describes as passing "every gate that exists" -- is
    refused by the second.

    Recorded as a test rather than as a sentence so that if either gate
    is ever reconciled with the other, this fails and the extractor's
    duplicated column key can be removed."""
    readiness_shape = {
        "sample_id": "PS-lot-4471", "variable": MN, "value": 104000.0, "unit": "g/mol",
        "uncertainty": 1200.0, "uncertainty_kind": "stated",
        "conditions": FrozenMapping({"solvent": "THF"}),
    }
    assert observation_is_table_alignable(readiness_shape).admissible
    context = no_context_free_property(readiness_shape)
    assert not context.admissible
    assert set(context.reasons) == {"MISSING_METHOD", "MISSING_PROPERTY"}


def test_the_extractor_carries_both_column_keys_with_one_string():
    for obs in observations():
        assert obs.content["variable"] == obs.content["property"], (
            "two gates read two different keys for one concept; the extractor satisfies both by "
            "carrying one string under both names, and this asserts they can never drift"
        )
