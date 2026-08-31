"""The two Physical Commerce architecture records, bound to the tree.

WHY THIS FILE EXISTS. It was not planned. The repository's own deferral
guard (`test_the_deferral_on_the_doctrine_source_list_still_holds`) failed
the moment `architecture/canadabuys_recon.yaml` and
`architecture/physical_commerce_founding.yaml` were added, because both
were covered by neither the doctrine projection nor any test. The guard
was correct: a record that nothing reads is prose, and its numbers drift
from the tree silently.

So these tests re-measure the records' own claims against the artifacts
they describe. A figure in a recon record that no longer matches the
fixture now fails by name rather than aging quietly into fiction.
"""

from __future__ import annotations

import csv
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

from commerce.canadabuys import PERSON_COLUMN_PREFIX, REQUIRED_COLUMNS, person_columns  # noqa: E402
from commerce.tender import REQUESTED_FIELDS  # noqa: E402

ARCHITECTURE = REPO_ROOT / "architecture"
RECON = loads((ARCHITECTURE / "canadabuys_recon.yaml").read_text())
FOUNDING = loads((ARCHITECTURE / "physical_commerce_founding.yaml").read_text())
FIXTURE = REPO_ROOT / "commerce" / "fixtures" / "canadabuys_open_sample.csv"


def _header() -> list:
    with FIXTURE.open(encoding="utf-8") as handle:
        return [name.lstrip("﻿") for name in next(csv.reader(handle))]


# =====================================================================
# The recon record's numbers, re-measured
# =====================================================================

def test_the_field_count_the_recon_claims_matches_the_captured_fixture():
    claimed = RECON["reachable"]["open_tender_notices"]["fields"]
    assert len(_header()) == claimed, (
        f"the recon record claims {claimed} fields and the captured sample has {len(_header())}"
    )


def test_the_person_column_count_the_recon_claims_matches_the_header():
    claimed = RECON["natural_person_data_in_the_feed"]["measured"]
    assert "13 of the 67" in claimed
    assert len(person_columns(_header())) == 13


def test_the_five_fields_the_recon_calls_absent_really_have_no_column():
    """The claim that decides PC-3's shape, checked against the real
    header rather than trusted."""
    header = " ".join(_header()).lower()
    absent = RECON["fields_the_order_asks_for_that_have_no_column"]
    assert set(absent) == {"quantity", "incoterms", "origin", "equipment",
                           "contract_value_or_currency"}
    for term in ("quantit", "incoterm", "origin", "equipment", "currenc"):
        assert term not in header, (
            f"the recon record says no column matches {term!r}; the header disagrees"
        )


def test_every_column_the_adapter_requires_is_in_the_captured_header():
    header = set(_header())
    for column in REQUIRED_COLUMNS:
        assert column in header, f"{column} is required by the adapter and absent from the fixture"


def test_the_person_prefix_the_adapter_excludes_is_the_one_the_record_names():
    assert PERSON_COLUMN_PREFIX == "contactInfo"
    assert "contactInfo" in RECON["natural_person_data_in_the_feed"]["measured"]


def test_the_recon_records_the_empty_first_probe_without_resolving_it():
    """The class-7 case met live. The record must NOT have decided which
    nothing it was, because the probe could not."""
    empty = RECON["the_empty_feed_on_the_first_probe"]
    assert empty["which_nothing_it_actually_was"] == "not_established"
    assert RECON["reachable"]["new_tender_notices"]["rows"] == 0


def test_the_recon_names_the_endpoint_it_guessed_wrong():
    """Two of three plausible word orders 404. The rule that the endpoint
    comes from the catalogue is worth nothing if the failure is not kept."""
    discovery = RECON["endpoint_discovery"]
    assert len(discovery["guessed_and_wrong"]) == 2
    assert discovery["catalogue_supplied_and_correct"] == (
        "openTenderNotice-ouvertAvisAppelOffres.csv")


# =====================================================================
# The founding record's claims, re-measured
# =====================================================================

def test_the_founding_record_states_pc0_is_not_discharged():
    """The most important line in the file. If this ever passes because
    someone edited the record rather than ran a transaction, the test
    below about what was built will still be here."""
    assert FOUNDING["pc_0_the_gate"]["status"] == "not_discharged"
    for held in ("operations core", "route engine", "bid engine"):
        assert held in FOUNDING["pc_0_the_gate"]["what_was_deliberately_not_built"]


def test_nothing_on_the_hold_list_was_built():
    """The holds, checked against the tree rather than against the record's
    own promise."""
    commerce = REPO_ROOT / "commerce"
    modules = {path.stem for path in commerce.rglob("*.py")}
    for forbidden in ("route", "route_engine", "twin", "trading", "position", "operations_core"):
        assert forbidden not in modules, f"commerce/{forbidden}.py exists and is on the hold list"


def test_the_modules_the_founding_record_names_all_exist():
    for key in ("pc_1_three_stores", "pc_2_canadabuys", "pc_3_tender_extraction",
                "pc_4_landed_cost", "pc_5_authority", "addition_2_cash_conversion",
                "addition_3_carrier_vetting"):
        module = FOUNDING[key]["module"]
        assert (REPO_ROOT / module).exists(), f"{key} names {module}, which does not exist"


def test_the_load_board_half_is_recorded_as_unprobed():
    """A licensing decision, not an engineering one. Probing to find out
    would be taking the decision by doing it."""
    addition = FOUNDING["addition_1_two_halves_of_the_opportunity_engine"]
    assert addition["status"] == "recorded_not_built"
    assert "NOT probed" in addition["what_was_done"]
    sources = " ".join(p.read_text() for p in (REPO_ROOT / "commerce").rglob("*.py"))
    for board in ("dat.com", "truckstop", "loadlink"):
        assert board not in sources.lower(), f"{board} is referenced in commerce/ and must not be"


def test_the_ten_requested_fields_are_the_orders_list_not_the_extractors():
    """An extractor graded on the fields it chose to produce scores full
    marks. The record and the code must agree on whose list it is."""
    assert len(REQUESTED_FIELDS) == 11  # ten named plus duration split from delivery_window
    for field in ("quantity", "origin", "incoterms", "equipment"):
        assert field in REQUESTED_FIELDS


def test_the_self_corrections_are_recorded_with_what_was_measured():
    """Both corrections came from measurement contradicting something
    already written and tested. The record keeps the wrong belief."""
    correction = FOUNDING["self_correction_the_fields_i_wrongly_called_prose"]
    assert "SEVEN distinct values" in correction["what_was_measured"]
    assert "SEVENTEEN atoms" in correction["what_was_measured"]
    assert "MIRROR" in correction["why_it_mattered"]


def test_the_award_join_is_recorded_with_the_number_that_looks_wrong():
    """38 of 966 looks like a broken join and is the right answer. A
    record that quietly omitted it would invite someone to 'fix' it."""
    award = FOUNDING["the_award_feed_is_the_outcome_store"]
    assert "38" in award["the_join_was_tested_not_assumed"]
    assert "RIGHT answer" in award["the_join_was_tested_not_assumed"]
    assert award["not_built"].startswith("the award adapter")
