"""The query surface, exercised over a real acquisition.

Every case here runs the actual pipeline over a transcribed anchor rather
than constructing observations by hand. A query surface tested against
hand-built objects would be testing its own fixtures.
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import GpcReportSourceAdapter  # noqa: E402
from daf.extractors.gpc_report import GpcReportExtractor  # noqa: E402
from daf.query import (NO_OBSERVATION_CARRIES_THIS_KEY, NOTHING_MATCHED,  # noqa: E402
                       OBSERVATION_NOT_HELD, POOL_IS_EMPTY,
                       WARRANT_CHAIN_BROKEN_AT, QueryRefusal, census,
                       holdings_matching, warrant_for)
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

ANCHOR = (REPO_ROOT / "tests" / "fixtures"
          / "physchem_study_anchor_wil_505902_water_solubility.json")


def _acquire(path=None):
    pool = EvidencePool()
    run_scout(GpcReportSourceAdapter(
        path=path or ANCHOR, source_name="regulations-gov",
        retrieved_at="2026-08-30T00:00:00Z", data_provenance="instrument_measurement",
        sample_id="CDC-003", sample_kind="sample"), GpcReportExtractor(), pool)
    return pool


# =====================================================================
# P1 -- the warrant comes back whole
# =====================================================================

def test_a_value_comes_back_with_everything_that_justifies_it():
    pool = _acquire()
    observation = next(iter(pool.all_observations()))
    warrant = warrant_for(pool, observation.id)

    assert warrant.measured_property == "eluate_concentration"
    assert warrant.content["property"] == "eluate_concentration", (
        "the raw content key is unchanged; only the caller-facing field is renamed"
    )
    assert warrant.unit == "mg/L"
    assert warrant.value in {9.43, 9.61, 9.66, 9.68, 9.69, 9.70, 9.71, 9.72,
                             9.73, 9.74, 9.75, 9.76, 9.80}
    assert warrant.uncertainty_kind == "absent"
    assert not warrant.is_absent

    assert len(warrant.provenance) == 1
    hop = warrant.provenance[0]
    assert hop.source_name == "regulations-gov"
    assert hop.retrieval_method == "file:gpc_report_v1"
    assert hop.retrieved_at == "2026-08-30T00:00:00Z"
    assert hop.document_id and hop.record_id


def test_the_acquirers_hand_is_separated_from_the_documents():
    """The distinction an external model most needs. The report states
    its method; the acquirer supplied the other three."""
    pool = _acquire()
    warrant = warrant_for(pool, next(iter(pool.all_observations())).id)
    assert set(warrant.declared_by_the_acquirer) == {
        "data_provenance", "sample_id", "sample_kind"}
    assert "method" not in warrant.declared_by_the_acquirer, (
        "the report cites OECD 105 itself; claiming the acquirer declared it would "
        "invert who said what"
    )
    assert warrant.data_provenance == "instrument_measurement"


def test_a_broken_chain_raises_rather_than_returning_a_partial_warrant():
    """Fails in the state where the surface hands back a number with a
    hop missing -- which is the unwarranted value this layer exists to
    refuse."""
    pool = _acquire()
    observation = next(iter(pool.all_observations()))

    class Amputated:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def has_document(self, _document_id):
            return False

    with pytest.raises(QueryRefusal) as caught:
        warrant_for(Amputated(pool), observation.id)
    assert caught.value.code == WARRANT_CHAIN_BROKEN_AT


def test_an_observation_the_pool_does_not_hold_is_refused_by_name():
    pool = _acquire()
    with pytest.raises(QueryRefusal) as caught:
        warrant_for(pool, "0" * 64)
    assert caught.value.code == OBSERVATION_NOT_HELD


# =====================================================================
# P2 -- the identifier problem, surfaced
# =====================================================================

def test_the_same_file_by_two_paths_gives_two_observation_ids_and_one_document_id():
    """THE FINDING THE SURFACE HAS TO LIVE WITH, held as a property.

    Fails in the state where the locator stops carrying the caller's path
    -- at which point the observation id is stable, the warning this
    surface prints is stale, and this test is the thing to retire.
    """
    here = os.getcwd()
    os.chdir(REPO_ROOT)
    try:
        relative = pathlib.Path(
            "tests/fixtures/physchem_study_anchor_wil_505902_water_solubility.json")
        by_relative = _acquire(relative)
        by_absolute = _acquire(ANCHOR)
    finally:
        os.chdir(here)

    def warrants(pool):
        return sorted((warrant_for(pool, o.id) for o in pool.all_observations()),
                      key=lambda w: (w.value, w.run_identity or ""))

    left, right = warrants(by_relative), warrants(by_absolute)
    assert [w.value for w in left] == [w.value for w in right], "the same measurements"

    assert {w.observation_id for w in left} != {w.observation_id for w in right}, (
        "the observation id is invocation-dependent; if that has been repaired, the "
        "surface's warning and architecture/query_surface_preregistration.yaml are stale"
    )
    assert {w.document_id for w in left} == {w.document_id for w in right}, (
        "the document id is the stable one, and is what a caller must de-duplicate on"
    )
    assert [w.run_identity for w in left] == [w.run_identity for w in right], (
        "the run identity is the part of the locator that is about the measurement"
    )


def test_the_run_identity_excludes_the_machine_and_names_the_run():
    pool = _acquire()
    warrant = warrant_for(pool, next(iter(pool.all_observations())).id)
    assert warrant.run_identity is not None
    assert warrant.run_identity.startswith("wil-505902-nkk1304-water-solubility/")
    assert "/home/user" not in warrant.run_identity
    assert warrant.identifier_is_invocation_dependent, (
        "the locator still carries a path prefix, so the flag must say so"
    )


# =====================================================================
# P3 and P4 -- cost, and which kind of nothing
# =====================================================================

def test_a_content_query_reports_what_it_examined_and_not_only_what_matched():
    pool = _acquire()
    found = holdings_matching(pool, property="eluate_concentration")
    assert len(found.matched) == 20
    assert found.examined == 20
    assert found.refusal is None


def test_the_three_empty_results_are_three_different_facts():
    """An empty tuple for all three would report a question as an answer."""
    empty = holdings_matching(EvidencePool())
    assert empty.is_empty and empty.refusal == POOL_IS_EMPTY

    pool = _acquire()
    nothing_matched = holdings_matching(pool, property="vapour_pressure")
    assert nothing_matched.is_empty
    assert nothing_matched.refusal == NOTHING_MATCHED
    assert nothing_matched.examined == 20, "it says what it cost to find out"

    bad_key = holdings_matching(pool, wavelength_nm=254)
    assert bad_key.is_empty
    assert bad_key.refusal == NO_OBSERVATION_CARRIES_THIS_KEY, (
        "a filter on a key nothing carries is a CALLER error and a different fact "
        "from 'nothing matched'"
    )
    assert "wavelength_nm" in bad_key.detail and "property" in bad_key.detail


def test_the_census_splits_by_provenance_before_it_totals():
    """A pool mixing measured and fabricated figures is one whose totals
    mean nothing."""
    counted = census(_acquire())
    assert counted["by_property"] == {"eluate_concentration": 20}
    assert counted["by_source"] == {"regulations-gov": 20}
    assert counted["by_data_provenance"] == {"instrument_measurement": 20}


# =====================================================================
# P5 -- the stop condition
# =====================================================================

def test_the_surface_is_read_only_and_adds_nothing_to_acquisition():
    source = (REPO_ROOT / "daf" / "query.py").read_text()
    for writing in ("put_observation", "put_record", "put_document", "put_source"):
        assert writing not in source, f"the query surface calls {writing}"
    # And it may not reach across the layer rule daf lives under.
    for forbidden in ("import science", "import materials", "import boundary",
                      "from science", "from materials", "from boundary"):
        assert forbidden not in source


def test_the_prediction_record_and_the_module_agree_on_what_was_measured():
    prereg = loads((REPO_ROOT / "architecture"
                    / "query_surface_preregistration.yaml").read_text())
    basis = prereg["measured_basis_taken_before_predicting_anything"]
    finding = basis["the_observation_id_depends_on_how_acquisition_was_INVOKED"]
    # The two ids the record names are the two the surface returns.
    assert "be533c20" in finding["measured"] and "db455994" in finding["measured"]
    assert "document_id" in (REPO_ROOT / "daf" / "query.py").read_text()
