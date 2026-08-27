"""B.1's predictions, pinned before the anchors exist.

The pin makes a retrospective edit a visible second act rather than a
quiet one; the real guarantee is the commit order, which places this
before any anchor is in the tree. Stated rather than assumed -- a pin
described as tamper-proof would be the proxy-for-its-target shape.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "corpus_anchor_preregistration.yaml"
PREREG = loads(ARTIFACT.read_text())
PINNED = "855c88c43e37302cd0de8750a25cd1f265a0b4368df42745db68d63e18de067d"


def test_the_predictions_have_not_been_edited_since_they_were_recorded():
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == PINNED, (
        "if a prediction turned out wrong, the RESULT says so -- this file is not corrected "
        "to match. Changing it and this pin together is a deliberate act to be argued for."
    )


# ----------------------------------------------------------------------
# THE GUARD, REPAIRED. Its first form read a PROXY for its target.
#
# It searched fixture names for "omnisec", "wingpc" and "polyanalytik" --
# the two anchors B.1 expected. The anchor that actually arrived is a
# Waters EMPOWER report from EPA ChemView, a third vendor nobody listed,
# and a fixture transcribed from it would have landed with the guard
# green. The check enumerated the anchors it could name; its target is
# ANY anchor.
#
# Latent, not fired: no fixture has landed, so the guard has never given
# a false green over anything real. A proxy defect found before it fires
# is the good case and is still the same defect.
#
# The repair is a per-file declaration over the WHOLE fixture directory
# rather than a name pattern over part of it. Any new fixture is
# undeclared and fails; declaring one as an anchor fires the guard
# whatever the vendor is called. What it still cannot catch is a fixture
# transcribed from a real report and declared NOT_A_GPC_ANCHOR -- that is
# a false statement by a person, and no check reaches it. Stated because
# an unstated limit is how the first form got written.
# ----------------------------------------------------------------------

NOT_A_GPC_ANCHOR = "not_a_gpc_anchor"
A_GPC_ANCHOR = "a_gpc_anchor"

#: Every fixture in the tree, declared. Enumerating all of them rather
#: than filtering to `gpc_*` is deliberate: a filename prefix is the same
#: kind of proxy the first form used, and an anchor need not be named for
#: what it is. The list is a cost that ends when this guard is retired.
FIXTURE_PROVENANCE = {
    "arxiv_entry_missing_id.xml": NOT_A_GPC_ANCHOR,
    "arxiv_single_entry_v1.xml": NOT_A_GPC_ANCHOR,
    "arxiv_single_entry_v1_revised.xml": NOT_A_GPC_ANCHOR,
    "arxiv_two_entries.xml": NOT_A_GPC_ANCHOR,
    "edgar_daily_index_malformed.idx": NOT_A_GPC_ANCHOR,
    "edgar_daily_index_synthetic_20260701.idx": NOT_A_GPC_ANCHOR,
    "edgar_daily_index_synthetic_20260701_empty.idx": NOT_A_GPC_ANCHOR,
    "edgar_daily_index_synthetic_20260702.idx": NOT_A_GPC_ANCHOR,
    "edgar_daily_index_synthetic_20260703.idx": NOT_A_GPC_ANCHOR,
    "edgar_daily_index_synthetic_double_space_name.idx": NOT_A_GPC_ANCHOR,
    "edgar_index_listing_synthetic.json": NOT_A_GPC_ANCHOR,
    "gpc_report_synthetic_derived_column.json": NOT_A_GPC_ANCHOR,
    "gpc_report_synthetic_ps4471.json": NOT_A_GPC_ANCHOR,
    "gpc_report_synthetic_unlabelled_provenance.json": NOT_A_GPC_ANCHOR,
    "gpc_summary_export_synthetic_absences.csv": NOT_A_GPC_ANCHOR,
    "gpc_summary_export_synthetic_flag_says_valid.csv": NOT_A_GPC_ANCHOR,
    "gpc_summary_export_synthetic_no_injection_id.csv": NOT_A_GPC_ANCHOR,
    "gpc_summary_export_synthetic_vendor.csv": NOT_A_GPC_ANCHOR,
    "graph_dataset_structure_only.json": NOT_A_GPC_ANCHOR,
    "incremental_dataset_sample.json": NOT_A_GPC_ANCHOR,
    "incremental_dataset_sample_extended.json": NOT_A_GPC_ANCHOR,
    "late_arrival_extended.json": NOT_A_GPC_ANCHOR,
    "late_arrival_initial.json": NOT_A_GPC_ANCHOR,
    "local_dataset_sample.json": NOT_A_GPC_ANCHOR,
    "local_dataset_sample_revised.json": NOT_A_GPC_ANCHOR,
    "noaa_live_8454000_20240115_mllw.json": NOT_A_GPC_ANCHOR,
    "noaa_live_8454000_20240115_stnd.json": NOT_A_GPC_ANCHOR,
    "noaa_live_8454000_preliminary.json": NOT_A_GPC_ANCHOR,
    "noaa_window_malformed.json": NOT_A_GPC_ANCHOR,
    "noaa_window_synthetic_20260101_20260103.json": NOT_A_GPC_ANCHOR,
    "noaa_window_synthetic_20260101_20260103_revised.json": NOT_A_GPC_ANCHOR,
    "noaa_window_synthetic_20260102_20260104.json": NOT_A_GPC_ANCHOR,
    "usgs_event_detail_malformed.json": NOT_A_GPC_ANCHOR,
    "usgs_event_detail_synth00000001.json": NOT_A_GPC_ANCHOR,
    "usgs_event_detail_synth00000001_empty.json": NOT_A_GPC_ANCHOR,
    "usgs_event_detail_synth00000001_revised.json": NOT_A_GPC_ANCHOR,
    "usgs_event_detail_synth00000002.json": NOT_A_GPC_ANCHOR,
    "usgs_event_detail_synth00000003.json": NOT_A_GPC_ANCHOR,
    "usgs_listing_synthetic.json": NOT_A_GPC_ANCHOR,
    "wikidata_mechanical_property_terms.json": NOT_A_GPC_ANCHOR,
}


def anchor_guard(present, declared):
    """(undeclared fixtures, fixtures declared to be anchors).

    A function rather than inline assertions so the detector proof below
    can run the REAL path against planted inputs instead of a paraphrase
    of it."""
    undeclared = sorted(set(present) - set(declared))
    anchors = sorted(name for name in present if declared.get(name) == A_GPC_ANCHOR)
    return undeclared, anchors


def test_no_anchor_is_in_the_tree_at_the_commit_that_records_these():
    """What the commit order is supposed to establish, asserted rather
    than trusted. Expected to fail once an anchor lands, and to be
    RETIRED in that commit with the pre-registration digest unchanged."""
    present = {path.name for path in (REPO_ROOT / "tests" / "fixtures").iterdir()
               if path.is_file()}
    undeclared, anchors = anchor_guard(present, FIXTURE_PROVENANCE)
    assert undeclared == [], (
        f"undeclared fixtures: {undeclared}. Declare each as NOT_A_GPC_ANCHOR or A_GPC_ANCHOR. "
        "An undeclared fixture is how the first form of this guard missed a vendor nobody listed."
    )
    assert anchors == [], (
        f"an anchor fixture exists: {anchors}. Retire this assertion in the commit that adds "
        "it, with the pre-registration digest unchanged."
    )


def test_the_guard_fires_on_a_vendor_nobody_listed_and_the_first_form_did_not():
    """DETECTOR PROOF, planted on the case that motivated the repair.

    The first form searched names for three vendors. The anchor that
    arrived is a fourth. Both forms are run here against the same planted
    fixture, and only one of them fires -- which is the defect made
    executable rather than described."""
    planted = "empower_p22_0051_slice_table.json"

    retired_form = [vendor for vendor in ("omnisec", "wingpc", "polyanalytik")
                    if vendor in planted.lower()]
    assert retired_form == [], (
        "the retired form must NOT fire on this name, or it was never the defect claimed"
    )

    present = set(FIXTURE_PROVENANCE) | {planted}
    undeclared, anchors = anchor_guard(present, FIXTURE_PROVENANCE)
    assert undeclared == [planted], "an undeclared fixture must fail the guard"

    declared = dict(FIXTURE_PROVENANCE, **{planted: A_GPC_ANCHOR})
    undeclared, anchors = anchor_guard(present, declared)
    assert undeclared == []
    assert anchors == [planted], "and a declared anchor must fire it whatever the vendor is called"

    honest_synthetic = dict(FIXTURE_PROVENANCE,
                            **{"gpc_report_synthetic_new.json": NOT_A_GPC_ANCHOR})
    _, none_fired = anchor_guard(set(honest_synthetic), honest_synthetic)
    assert none_fired == [], (
        "and a declared-synthetic fixture must NOT fire it, or the guard refuses every new "
        "fixture and would be disabled rather than obeyed"
    )


def test_every_prediction_declares_its_basis():
    for name, body in PREREG["predictions"].items():
        assert "prediction" in body, f"{name} states no prediction"
        assert any(word in body.get("basis", "") for word in ("OPEN", "MEASURED")), (
            f"{name} does not say whether it rests on measured behaviour"
        )
    assert any(b["basis"].startswith("OPEN") for b in PREREG["predictions"].values()), (
        "every prediction resting on measured behaviour would make this a description"
    )


def test_the_permeation_prediction_is_grounded_in_the_forward_model_measurement():
    """It came from measuring why an acceptance test failed, not from
    reading about chromatography."""
    permeation = PREREG["predictions"]["the_permeation_bound_is_computable_or_it_is_not"]
    assert "1.899" in permeation["where_it_came_from"]
    assert "no broadening at all" in permeation["where_it_came_from"]
    assert permeation["basis"] == "OPEN"
    assert "the_permeation_bound" in PREREG["the_prediction_most_likely_to_be_wrong"]


def test_the_uncertainty_vocabulary_really_has_no_repeatability_member():
    """The measurement that makes the sigma prediction checkable now
    rather than only against an anchor."""
    from science.admissibility import UNCERTAINTY_KINDS

    assert UNCERTAINTY_KINDS == ("stated", "estimated", "propagated", "absent")
    for member in UNCERTAINTY_KINDS:
        assert "repeat" not in member and "rsd" not in member and "replicate" not in member
    assert "None of those names a repeatability statistic" in PREREG["predictions"][
        "sigma_and_rsd_are_not_uncertainty"]["the_measurement_that_settles_it"]
