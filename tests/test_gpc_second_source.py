"""The second GPC source, measured against predictions recorded before it
was built.

WHAT IS AND IS NOT MEASURED. Every number is FABRICATED and labelled
`fabricated_fixture` in the content it produces. What is real is whether
the acquisition contract derived from ONE fixture survives a source of a
genuinely different shape -- and in one place it did not.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import GpcReportSourceAdapter  # noqa: E402
from daf.adapters.gpc_summary_export import (CONDITIONS_AS_REPORTED,  # noqa: E402
                                             GpcSummaryExportFetchError,
                                             GpcSummaryExportSourceAdapter)
from daf.extractors.gpc_report import (DERIVED_VARIABLES,  # noqa: E402
                                       GpcReportExtractionError, GpcReportExtractor)
from daf.storage.frozen_mapping import FrozenMapping  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from science.admissibility import no_context_free_property  # noqa: E402
from science.replicate_pairing import (TOO_FEW_VARIABLES_FOR_A_CORRELATION,  # noqa: E402
                                       covariance_of, pair_replicates)
from science.table import observation_is_table_alignable  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
VENDOR = FIXTURES / "gpc_summary_export_synthetic_vendor.csv"
NO_INJ = FIXTURES / "gpc_summary_export_synthetic_no_injection_id.csv"
FIRST_SOURCE = FIXTURES / "gpc_report_synthetic_ps4471.json"
WHEN = "2026-08-27T00:00:00Z"
PREREG = loads((REPO_ROOT / "architecture" / "gpc_second_source_preregistration.yaml").read_text())

DECLARED = dict(data_provenance="fabricated_fixture", sample_kind="sample",
                method="sec_thf_35c_polystyrene_calibrated",
                unit_by_column={"Mw": "g/mol", "PDI": "dimensionless"},
                kind_by_column={"Mw": "measured", "PDI": "derived"})


def adapter(path=VENDOR, **over):
    return GpcSummaryExportSourceAdapter(
        path=path, source_name="synthetic-vendor-sec", retrieved_at=WHEN,
        **{**DECLARED, **over})


def acquire(path=VENDOR, **over):
    pool = EvidencePool()
    findings, failures = run_scout(adapter(path, **over), GpcReportExtractor(), pool)
    return pool, failures


def observations(path=VENDOR, **over):
    pool, _ = acquire(path, **over)
    return sorted(pool.all_observations(), key=lambda o: o.id)


# =====================================================================
# The extractor is shared and unchanged -- that is the contract test
# =====================================================================

def test_the_second_source_uses_the_same_extractor_and_has_none_of_its_own():
    """If the second source had needed its own extractor, the contract
    would have been the first fixture's shape wearing a general name.
    Extraction is where the contract lives; acquisition is where the
    source shape lives."""
    assert not (REPO_ROOT / "daf" / "extractors" / "gpc_summary_export.py").exists()
    assert observations(), "the shared extractor produced nothing from the second source"


def test_neither_adapter_imports_the_other():
    """Two adapters that drift is a detectable state; one adapter
    reaching into another is a coupling nothing reports."""
    import ast

    def imported_modules(name):
        tree = ast.parse((REPO_ROOT / "daf" / "adapters" / name).read_text())
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
            elif isinstance(node, ast.Import):
                found |= {a.name for a in node.names}
        return found

    # Checked on the IMPORT GRAPH, not on the text: the second adapter's
    # docstring names the first one deliberately, to say it reuses its
    # extractor, and a substring check would fail on the explanation.
    first, second = imported_modules("gpc_report.py"), imported_modules("gpc_summary_export.py")
    assert not any("gpc_summary_export" in m for m in first)
    assert not any("gpc_report" in m for m in second)
    assert any("_provenance" in m for m in first) and any("_provenance" in m for m in second), (
        "the shared vocabulary must be factored into a module neither adapter owns"
    )


# =====================================================================
# Prediction by prediction
# =====================================================================

def test_prediction_one_record_per_run_when_runs_are_rows():
    """PREDICTED, and named in advance as the one expected to be wrong.
    It HELD."""
    obs = observations()
    assert len(obs) == 8
    assert len({o.record_ids for o in obs}) == 8, "eight rows must be eight Records"
    for o in obs:
        assert len(o.record_ids) == 1


def test_prediction_a_positional_locator_is_not_a_positional_identity():
    """The MECHANISM the prediction rested on, tested against a source
    with no injection column at all -- so the locator is purely
    positional. A test using the file that HAS an `Inj` column would pass
    without exercising this."""
    documents = adapter(NO_INJ).fetch()
    assert all("/row-" in d.locator for d in documents), (
        "this fixture exists to make the locator positional; if it is not, the prediction is "
        "untested rather than confirmed"
    )
    obs = observations(NO_INJ)
    assert len(obs) == 8 and len({o.record_ids for o in obs}) == 8

    for o in obs:
        assert not ({"row_index", "position", "Inj", "run_id", "id"} & set(o.content)), (
            "a positional key reached content, where the table gate refuses it -- the distinction "
            "the prediction rested on does not hold"
        )
        assert observation_is_table_alignable(o.content).admissible

    pairing = pair_replicates(obs)
    assert pairing.refusals == ()
    assert sorted(len(s.run_ids) for s in pairing.sets) == [3, 5]


def test_prediction_uncertainty_absent_is_reachable_from_a_real_source():
    """PREDICTED and marked MEASURED in the pre-registration -- a
    confirmation, not a discovery, and recorded as such."""
    for o in observations():
        assert o.content["uncertainty"] is None
        assert o.content["uncertainty_kind"] == "absent"
        assert no_context_free_property(o.content).admissible
    assert PREREG["predictions"]["uncertainty_absent_from_a_real_source"]["basis"].startswith("MEASURED")


def test_prediction_conditions_are_carried_verbatim_and_nothing_is_parsed():
    """The prediction named its own failure condition: if anything is
    found parsed out of the header block, the prediction failed and the
    contract did not."""
    raw_header = [line.lstrip("#").strip() for line in VENDOR.read_text().splitlines()
                  if line.startswith("#")]
    for o in observations():
        conditions = o.content["conditions"]
        assert isinstance(conditions, FrozenMapping)
        assert set(conditions) == {CONDITIONS_AS_REPORTED}, (
            f"conditions carry {sorted(conditions)} -- anything beyond the verbatim block means "
            "the header was parsed, which invents a field name, a unit and a type"
        )
        carried = conditions[CONDITIONS_AS_REPORTED]
        for line in raw_header:
            assert line in carried, f"the header line {line!r} was not carried verbatim"
        for invented in ("column_temperature_c", "temperature_c", "flow_rate_ml_per_min", "solvent"):
            assert invented not in conditions


def test_prediction_the_cost_of_carrying_prose_is_comparability():
    """Predicted and confirmed: the two sources describe the same
    physical conditions and land in different comparison contexts. A
    finding about the contract, not a defect to repair at the extractor."""
    from science.replicate_pairing import _context_of

    second = _context_of(observations()[0].content)
    pool = EvidencePool()
    run_scout(GpcReportSourceAdapter(path=FIRST_SOURCE, source_name="s", retrieved_at=WHEN),
              GpcReportExtractor(), pool)
    first = _context_of(sorted(pool.all_observations(), key=lambda o: o.id)[0].content)
    assert dict(first)["conditions"] != dict(second)["conditions"]
    assert set(first) != set(second), (
        "if the contexts ever match, the predicted cost is gone and the prediction should be "
        "re-measured rather than re-read"
    )


def test_prediction_rho_is_unreachable_and_the_reason_is_named():
    """PREDICTED. One variable survives where the consumer needs two --
    and the work order's gate requires the refusal be ATTRIBUTABLE."""
    obs = observations()
    assert sorted({o.content["property"] for o in obs}) == ["Mw"]
    results = covariance_of(obs)
    assert results
    for r in results:
        assert r.covariance is not None
        assert r.covariance.correlation == ((1.0,),)
        assert TOO_FEW_VARIABLES_FOR_A_CORRELATION in r.covariance.reasons, (
            "a 1x1 correlation of 1.0 is true by construction; returning it with no reason reads "
            "as a computed correlation"
        )


def test_the_first_source_still_reaches_a_real_rho_through_the_same_consumer():
    """The gate's other half: the shared path still closes for the source
    that can support it."""
    pool = EvidencePool()
    run_scout(GpcReportSourceAdapter(path=FIRST_SOURCE, source_name="s", retrieved_at=WHEN),
              GpcReportExtractor(), pool)
    results = covariance_of(list(pool.all_observations()))
    assert len(results) == 1
    cov = results[0].covariance
    assert cov is not None and cov.reasons == ()
    assert 0.0 < abs(cov.correlation[0][1]) < 1.0


def test_prediction_several_samples_separate_without_the_extractor_doing_anything():
    pool, _ = acquire()
    assert sorted(r.natural_key for r in pool.all_referents()) == ["PMMA-lot-882", "PS-lot-4471"]
    assert sorted(len(s.run_ids) for s in pair_replicates(list(pool.all_observations())).sets) == [3, 5]


# =====================================================================
# THE PREDICTION THAT FAILED
# =====================================================================

def test_the_derived_column_refusal_was_a_case_sensitive_enumeration():
    """THE FAILED PREDICTION, and the phase's central finding.

    Predicted: `PDI IS REFUSED as a derived column by the existing
    check`. It was not. DERIVED_VARIABLES is a case-sensitive list, the
    first fixture wrote `dispersity` because the same author wrote the
    fixture and the check, and a real vendor writes `PDI` -- the standard
    acronym. Eight derived quantities entered the pool wearing the
    `measured` class with every gate green.

    This is the reference-implementation problem demonstrated rather than
    argued: one fixture and one extractor by one author agree with each
    other and prove nothing about a second source."""
    assert "PDI" not in DERIVED_VARIABLES, (
        "if PDI is added to the list, this records the wrong history -- the repair was the "
        "declared kind, not a longer list"
    )
    assert "pdi" in DERIVED_VARIABLES

    # The repair is the DECLARED kind. A payload that reaches the extractor
    # declaring `derived` is refused -- shown here on the FIRST source's
    # derived-column fixture, which does declare one, so the refusal is
    # reachable rather than merely defined.
    pool = EvidencePool()
    with pytest.raises(GpcReportExtractionError, match="kind 'derived'"):
        run_scout(GpcReportSourceAdapter(
            path=FIXTURES / "gpc_report_synthetic_derived_column.json",
            source_name="s", retrieved_at=WHEN), GpcReportExtractor(), pool)


def test_an_undeclared_measurement_kind_is_refused_rather_than_assumed_measured():
    """The direction that fails safe. Assuming `measured` is the error
    that occurred."""
    documents = adapter().fetch()
    import json
    payload = json.loads(documents[0].content)
    for measurement in payload["measurements"]:
        measurement.pop("kind")

    import dataclasses
    poisoned = dataclasses.replace(documents[0], content=json.dumps(payload, sort_keys=True))

    @dataclasses.dataclass(frozen=True)
    class _Adapter:
        def fetch(self):
            return (poisoned,)

    with pytest.raises(GpcReportExtractionError, match="must declare that kind explicitly"):
        run_scout(_Adapter(), GpcReportExtractor(), EvidencePool())


def test_a_mislabelled_derived_column_is_still_caught_by_the_supplementary_net():
    """A caller declaring PDI `measured` is wrong, and the normalised
    name check catches it -- which is why the enumeration is kept as a
    supplement rather than deleted. It is not the protection."""
    with pytest.raises(GpcReportExtractionError, match="computed from other reported quantities"):
        acquire(kind_by_column={"Mw": "measured", "PDI": "measured"})


def test_a_derived_column_is_declined_visibly_rather_than_dropped():
    for o in observations():
        assert o.content["not_acquired_because_not_measured"] == "PDI"
        assert o.content["property"] != "PDI"


# =====================================================================
# What the source cannot state -- the four caller-declared fields
# =====================================================================

@pytest.mark.parametrize("field,bad", [
    ("data_provenance", "unknown"),
    ("sample_kind", ""),
    ("method", ""),
    ("unit_by_column", {}),
    ("kind_by_column", {}),
])
def test_nothing_the_source_cannot_state_is_defaulted(field, bad):
    """Four fields the contract requires and a vendor export does not
    carry. Each is caller-declared and each refusal is by name."""
    with pytest.raises(GpcSummaryExportFetchError):
        adapter(**{field: bad}).fetch()


def test_the_content_says_which_fields_the_acquirer_declared():
    """The difference between declaring and fabricating is that a
    consumer can tell."""
    for o in observations():
        declared = o.content["acquisition_declared"].split(",")
        assert declared == sorted(declared)
        assert set(declared) == {"data_provenance", "measurement_kind", "method",
                                 "sample_kind", "unit"}
