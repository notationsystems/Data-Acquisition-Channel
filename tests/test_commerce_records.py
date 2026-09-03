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
import re
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


# =====================================================================
# architecture/opportunity_engine.yaml, bound to the tree
# =====================================================================

ENGINE = loads((ARCHITECTURE / "opportunity_engine.yaml").read_text())


def test_the_engine_record_names_modules_that_all_exist():
    for key in ("truck_legal_routing", "facility_resolution", "pc_6_carrier_vetting"):
        module = ENGINE[key]["module"]
        assert (REPO_ROOT / module).exists(), f"{key} names {module}, which does not exist"
    for module in ENGINE["the_manual_adapter"]["modules"]:
        assert (REPO_ROOT / module).exists()


def test_the_measured_route_numbers_match_the_constants_the_code_reasons_from():
    """The record and the module must not drift. Both carry the same
    measurement and it is the one the design turns on."""
    from commerce.mileage import __doc__ as mileage_doc
    sweep = ENGINE["truck_legal_routing"]["urban_lane_height_sweep"]
    assert sweep["at_4_11_m"] == "18.261 km / 1102 s"
    assert sweep["at_4_60_m"] == "18.202 km / 1851 s"
    assert mileage_doc is not None
    for figure in ("18.261", "1102", "18.202", "1851", "544.93", "545.96"):
        assert figure in mileage_doc, f"{figure} is in the record and not in the module"


def test_the_record_states_what_the_measurement_corrects_in_the_brief():
    """Two of the brief's own recommendations were changed by measurement.
    A record that kept only the conclusion would lose the reason."""
    corrections = ENGINE["truck_legal_routing"]["what_it_corrects_in_the_brief"]
    assert "prove nothing" in corrections["on_the_validation_plan"]
    assert "MILEAGE IS THE QUANTITY THAT BARELY MOVES" in corrections["on_the_pricing_input"]


def test_the_facility_floor_in_the_record_matches_the_code():
    from commerce.facility import CANONICAL_DUPLICATE_SIMILARITY, NEAR_MATCH_FLOOR
    from commerce.facility import CONSERVATIVE as C, STATISTICAL as S
    calibration = ENGINE["facility_resolution"]["the_measured_calibration"]
    assert "0.50" in calibration["what_happened"]
    assert abs(CANONICAL_DUPLICATE_SIMILARITY - 0.50) < 1e-9
    assert f"{NEAR_MATCH_FLOOR[C]}" in calibration["the_repair"]
    assert f"{NEAR_MATCH_FLOOR[S]}" in calibration["the_repair"]


def test_nothing_on_the_engine_hold_list_was_built():
    modules = {path.stem for path in (REPO_ROOT / "commerce").rglob("*.py")}
    for forbidden in ("vroom", "h3", "tile38", "postgis", "mobilitydb", "auto_sea_way"):
        assert forbidden not in modules, f"commerce/{forbidden}.py is on the hold list"


def test_the_ors_key_decision_is_recorded_rather_than_taken():
    ors = ENGINE["truck_legal_routing"]["ors_public_api"]
    assert "401" in ors["measured"]
    assert "Not signed up for" in ors["consequence"]
    sources = " ".join(p.read_text() for p in (REPO_ROOT / "commerce").rglob("*.py"))
    assert "api_key" not in sources.lower(), "no API key may be embedded in this package"


# =====================================================================
# architecture/carrier_vetting_recon.yaml, bound to the code it corrected
# =====================================================================

LADDER = loads((ARCHITECTURE / "carrier_vetting_recon.yaml").read_text())


def test_the_recon_records_that_the_briefs_premise_was_refuted():
    """The brief said QCMobile is down. Measured, every endpoint answered
    and the auth backend is live and stateful. A ladder that recorded rung
    1 as unavailable would have written a durable claim about the SOURCE
    when the observable was a fact about OUR CREDENTIALS."""
    finding = LADDER["qcmobile_is_not_down"]
    assert "Webkey not found" in finding["measured"]
    assert "PENDING_CREDENTIAL" in finding["the_reclassification"]
    assert "wrong_attribution" in " ".join(finding).lower() or \
        "wrong attribution" in finding["why_this_is_the_wrong_attribution_class_again"].lower()


def test_the_freeze_date_in_the_record_matches_the_code():
    """Compared as DATES, not as strings. The record quotes the source's
    own `05/14/2026` verbatim and the code carries ISO `2026-05-14`; those
    are the same day in two formats, and a string comparison would have
    failed on a correct record. Quoting the source verbatim is the right
    call and converting for comparison is this test's job."""
    import datetime
    from commerce.vetting import FROZEN_AT, RUNG_BULK_HISTORY
    freeze = LADDER["bulk_history_is_the_primary_and_the_reason_is_sharper"]["the_freeze"]
    quoted = re.search(r"(\d{2})/(\d{2})/(\d{4})", freeze["measured"])
    assert quoted is not None, "the record must quote the source's own freeze notice verbatim"
    month, day, year = (int(g) for g in quoted.groups())
    assert datetime.date(year, month, day) == datetime.date.fromisoformat(
        FROZEN_AT[RUNG_BULK_HISTORY])
    assert "139,580" in freeze["the_successor_is_not_a_drop_in"]
    assert "4,941,925" in freeze["the_successor_is_not_a_drop_in"]


def test_the_per_kind_history_correction_is_recorded_with_what_forced_it():
    from commerce.vetting import (AUTHORITY_GRANTED_AT, RUNG_OFFICIAL_SNAPSHOT, SMS_PERCENTILE,
                                  rung_answers_history_for)
    split = LADDER["rung_three_must_be_split"]
    assert "189" in split["sms_carries_history"]
    assert "no grant-date column" in split["sms_still_has_no_grant_date"]
    # The record's claim and the code must agree.
    assert rung_answers_history_for(RUNG_OFFICIAL_SNAPSHOT, SMS_PERCENTILE)
    assert not rung_answers_history_for(RUNG_OFFICIAL_SNAPSHOT, AUTHORITY_GRANTED_AT)


def test_the_ontario_hypothesis_is_recorded_as_refuted_not_quietly_dropped():
    """PC-6 Part F asked whether a CVOR abstract is consent-gated and said
    the answer materially changes the design. It is not, and a record that
    kept only the new design would lose that a hypothesis was tested."""
    ontario = LADDER["ontario_is_not_consent_gated"]
    assert ontario["measured_answer"].startswith("no.")
    assert "the_trap_that_was_avoided" in ontario
    assert ontario["carries_history"] == "no", (
        "bare `no` parses as boolean False under one parser and the string 'no' under the "
        "other; the always-quote rule exists for exactly this"
    )


def test_the_canadian_gap_is_recorded_as_per_province_not_one_adapter():
    federal = LADDER["no_federal_canadian_registry_exists"]
    assert "49 datasets" in federal["measured"]
    assert "one adapter per province" in federal["the_consequence"]
    assert "TWO of thirteen" in federal["the_consequence"]
    # And the code's remedy says the same thing.
    from commerce.opportunity import Opportunity  # noqa: F401
    from commerce.vetting import Carrier, jurisdiction_coverage
    result = jurisdiction_coverage(Carrier("c", "Domestique", cvor_number="CV-1"),
                                   domestic_only=True)
    assert "one adapter per province" in result.detail


def test_the_round_stopped_on_terms_rather_than_probing_through_them():
    vendors = LADDER["commercial_wrappers"]
    assert "stopped probing that host entirely" in vendors["where_the_round_stopped"]
    assert "reachability_is_a_client_fact" in vendors


def test_the_verification_pass_actually_refuted_something():
    """A verification stage that never refutes is a rubber stamp."""
    verification = LADDER["adversarial_verification"]
    assert verification["refuted"] >= 1, "two independent verifiers per claim and nothing refuted"
    assert verification["what_the_refutations_caught"]


def test_the_successor_refutation_is_recorded_with_the_numbers_that_refuted_it():
    """The most important finding of the recon round: an inference every
    probe made, none measured, and the verification pass refuted by
    testing. It fails as a FALSE PASS, which is the dangerous direction."""
    finding = LADDER["the_successor_does_not_close_the_seam"]
    assert "ZERO rows for 12 of 12" in finding["the_critic_tested_it"]
    assert "6.7 percent" in finding["what_the_successor_actually_is"]
    assert "out of service for three days" in finding[
        "the_failure_mode_is_a_false_pass_and_it_reproduces"]
    assert "is fiction" in finding["the_honest_entry"]
    # And the code refuses to union it in.
    from commerce.vetting import NO_SUCCESSOR_ESTABLISHED_AFTER, RUNG_BULK_HISTORY
    assert RUNG_BULK_HISTORY in NO_SUCCESSOR_ESTABLISHED_AFTER


def test_the_linear_ladder_is_recorded_as_replaced_not_merely_amended():
    from commerce.vetting import channel_for
    shape = LADDER["the_linear_ladder_is_the_wrong_shape"]
    assert "routing table" in shape["the_replacement"]
    assert callable(channel_for)


def test_the_round_records_where_its_own_probes_dressed_recall_as_measurement():
    """A verification pass that never refutes is a rubber stamp, and the
    demotions must be recorded so they do not propagate as settled."""
    demoted = LADDER["recall_dressed_as_measurement"]
    assert "BLANK encrypted form" in demoted["the_weakest_presentation"]
    assert "neither reproduced" in demoted["third_party_proxies_are_not_the_origin"]
    assert demoted["two_probes_disagree_on_a_verbatim"]


def test_the_caching_prohibition_is_held_rather_than_designed_against():
    """Quebec's terms prohibit storing, and the probe that measured the
    prohibition recommended a store in the same report. The code's remedy
    must not repeat it."""
    hold = LADDER["hold_until_a_person_clears_it"]
    assert "stocker" in hold["redistribution_and_caching"]
    assert "do not build a local mirror" in hold["the_rule"].lower()
    from commerce.vetting import Carrier, jurisdiction_coverage
    remedy = jurisdiction_coverage(Carrier("c", "D", cvor_number="1"),
                                   domestic_only=True).remedy or ""
    assert "prohibit storing" in remedy
    assert "snapshot-and-diff" not in remedy


def test_the_biggest_unasked_question_is_named_as_unasked():
    hold = LADDER["hold_until_a_person_clears_it"]
    assert "Canadian carrier insurance status" in hold["the_biggest_unasked_question"]
    assert "nine of thirteen" in hold["jurisdictions_unprobed"]
