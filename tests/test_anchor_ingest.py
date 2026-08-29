"""The first real report against the unchanged acquisition path.

Every verdict in architecture/anchor_ingest_result.yaml is re-executed
here. The fixture is a faithful transcription and is REFUSED; the
variants that are admitted exist only to score the predictions, are built
in-memory, and are never written to tests/fixtures/.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import (GpcReportFetchError,  # noqa: E402
                                     GpcReportSourceAdapter)
from daf.extractors.gpc_report import (DERIVED_VARIABLES,  # noqa: E402
                                       GpcReportExtractionError, GpcReportExtractor,
                                       _normalised)
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from science.admissibility import (no_context_free_property,  # noqa: E402
                                   quantity_is_typed)
from science.table import observation_is_table_alignable  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

ANCHOR = REPO_ROOT / "tests" / "fixtures" / "gpc_report_anchor_epa_p22_0051.json"
RESULT = loads((REPO_ROOT / "architecture" / "anchor_ingest_result.yaml").read_text())
PREREG = loads((REPO_ROOT / "architecture"
                / "anchor_ingest_preregistration.yaml").read_text())
LIMIT = 14000.0


def _acquire(document):
    """Run the UNCHANGED path over an in-memory variant."""
    path = ANCHOR.with_name("tmp_anchor_variant.json")
    path.write_text(json.dumps(document))
    pool = EvidencePool()
    try:
        _, failures = run_scout(
            GpcReportSourceAdapter(path=path, source_name="epa-chemview",
                                   retrieved_at="2026-08-28T00:00:00Z"),
            GpcReportExtractor(), pool)
        return sorted(pool.all_observations(),
                      key=lambda o: o.content["property"]), failures
    finally:
        path.unlink(missing_ok=True)


def _with_fields(kind="measured"):
    """The variant that CAN be acquired -- by stating four fields the
    report does not carry. It exists to score P1, P3 and P4 and is the
    misread, named as one."""
    document = copy.deepcopy(json.loads(ANCHOR.read_text()))
    document.update({"data_provenance": "instrument_measurement",
                     "sample_kind": "sample", "sample_id": "REDACTED-in-source",
                     "method": "sec_thf_40c_polystyrene_calibrated_iso2201"})
    for measurement in document["runs"][0]["measurements"]:
        if measurement["variable"] == "polydispersity":
            measurement["kind"] = kind
    return document


# =====================================================================
# The fixture is faithful, and faithful means refused
# =====================================================================

def test_the_fixture_states_nothing_the_report_does_not():
    """THE MISREAD, held as a property. An earlier version of this file
    carried four fields the source has none of, and the ingest succeeded
    because of it."""
    document = json.loads(ANCHOR.read_text())
    for invented in ("data_provenance", "sample_kind", "method", "sample_id"):
        assert invented not in document, (
            f"{invented!r} is back in the fixture. The report states it nowhere, and a fixture "
            "that supplies it is widening a clause one layer earlier than any test looks."
        )
    assert "NOTHING THE DOCUMENT DOES NOT STATE IS PRESENT" in document["_transcription_note"]
    assert len(document["runs"][0]["distribution_table"]) == 100


def test_the_faithful_anchor_is_refused_and_the_refusal_names_the_field():
    with pytest.raises(GpcReportFetchError, match="data_provenance"):
        _acquire(json.loads(ANCHOR.read_text()))


@pytest.mark.parametrize("field", ["data_provenance", "sample_kind", "method", "sample_id"])
def test_each_required_field_is_refused_individually(field):
    """P2's mechanism. Four separate refusals, each naming its field --
    not one composite complaint."""
    document = _with_fields()
    document.pop(field)
    with pytest.raises(GpcReportFetchError, match=field):
        _acquire(document)


def test_this_adapter_has_no_caller_declaration_channel_and_the_other_one_does():
    """The two adapters answer `who states what the document cannot` in
    incompatible ways, and the second one is right."""
    import inspect

    from daf.adapters.gpc_summary_export import GpcSummaryExportSourceAdapter

    first = set(inspect.signature(GpcReportSourceAdapter).parameters)
    second = set(inspect.signature(GpcSummaryExportSourceAdapter).parameters)
    assert first == {"path", "source_name", "retrieved_at"}
    for declaration in ("data_provenance", "sample_kind", "method"):
        assert declaration in second
        assert declaration not in first, (
            "if the first adapter grows a declaration channel, P2's finding is closed and this "
            "record must say so rather than the test being deleted"
        )


# =====================================================================
# The predictions, scored on the variant that can be acquired
# =====================================================================

def test_p1_the_hundred_row_slice_table_produces_nothing_and_says_nothing():
    observations, failures = _acquire(_with_fields())
    assert failures == ()
    assert [o for o in observations if "slice" in o.content["property"]] == []
    assert len(observations) == 6, "six moments in, six out, and a hundred slice rows dropped"
    assert observations[0].content.get("not_acquired_because_not_measured") is None, (
        "the drop is SILENT -- if a decline is ever recorded, P1's `worse than predicted` half "
        "is closed and the record must say so"
    )


def test_p3_a_mode_enters_as_a_peer_of_the_moments():
    observations, _ = _acquire(_with_fields())
    properties = {o.content["property"]: o.content["value"] for o in observations}
    assert properties["peak_molar_mass"] == 15334.0
    mode = next(o for o in observations if o.content["property"] == "peak_molar_mass")
    moment = next(o for o in observations
                  if o.content["property"] == "weight_average_molar_mass")
    differing = {key for key in set(mode.content) | set(moment.content)
                 if mode.content.get(key) != moment.content.get(key)}
    assert differing == {"property", "value"}, (
        f"{differing} distinguishes a mode from a moment; if anything beyond the name and the "
        "number does, P3 is closed"
    )


def test_p4_two_values_the_report_calls_invalid_are_admitted_with_no_code():
    observations, _ = _acquire(_with_fields())
    above = {o.content["property"]: o.content["value"] for o in observations
             if o.content.get("unit") == "g/mol" and o.content["value"] > LIMIT}
    assert above == {"peak_molar_mass": 15334.0,
                     "z_plus_one_average_molar_mass": 15577.0}
    for observation in observations:
        for gate in (no_context_free_property, quantity_is_typed,
                     observation_is_table_alignable):
            assert not gate(observation.content).reasons

    carried = observations[0].content["conditions"]["validity_statement_as_reported"]
    assert "not valid" in carried and "14000" in carried, (
        "the sentence that invalidates them travels with them and nothing reads it"
    )


# =====================================================================
# The unpredicted finding
# =====================================================================

def test_the_reports_own_spelling_is_not_in_the_derived_denylist():
    """The seventh vendor spelling, and the first from a real document."""
    assert _normalised("Polydispersity") == "polydispersity"
    assert "polydispersity" not in DERIVED_VARIABLES, (
        "if it has been added, this anchor passes and the eighth spelling's problem is "
        "unchanged -- the declared-kind requirement is the protection, not the list"
    )


def test_one_declaration_decides_between_losing_everything_and_admitting_a_derived_value():
    with pytest.raises(GpcReportExtractionError, match="kind 'derived'"):
        _acquire(_with_fields(kind="derived"))

    observations, _ = _acquire(_with_fields(kind="measured"))
    dispersity = next(o for o in observations
                      if o.content["property"] == "polydispersity")
    assert dispersity.content["value"] == pytest.approx(2.412342)
    assert dispersity.content["unit"] == "dimensionless"
    assert not quantity_is_typed(dispersity.content).reasons


# =====================================================================
# The record and the pre-registration
# =====================================================================

def test_the_record_reports_the_misread_before_the_results():
    text = (REPO_ROOT / "architecture" / "anchor_ingest_result.yaml").read_text()
    assert text.index("the_misread_was_in_the_fixture") < text.index("the_predictions_scored")
    misread = RESULT["the_misread_was_in_the_fixture_and_it_was_mine"]
    assert "it did not fail" in misread["why_it_is_the_serious_kind"]
    assert "one layer earlier" in misread["the_general_shape"]


def test_every_prediction_has_a_verdict_and_all_four_held():
    scored = RESULT["the_predictions_scored"]
    assert set(scored) == set(PREREG["predictions"])
    for name, body in scored.items():
        assert body["verdict"].startswith("HELD"), f"{name} is not scored HELD"


def test_no_clause_was_widened():
    """The order's own constraint, asserted rather than promised."""
    assert "polydispersity" not in DERIVED_VARIABLES
    assert set(RESULT["what_no_clause_was_widened_means_here"].split()) >= {"unchanged."}
    assert "REFUSED document" in RESULT["what_no_clause_was_widened_means_here"]
