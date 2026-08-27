"""The absence vocabulary, exercised for the first time.

WO-4 measured it entirely unexercised: no acquisition path emitted
`value_absence`, so every code guarding it reported zero for a reason
that was not a measurement. A source that states its own absence reasons
now runs against it.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_summary_export import (GpcSummaryExportFetchError,  # noqa: E402
                                             GpcSummaryExportSourceAdapter)
from daf.extractors.gpc_report import GpcReportExtractionError, GpcReportExtractor  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from science.admissibility import no_context_free_property, quantity_is_typed  # noqa: E402
from science.table import ABSENCE_REASONS, observation_is_table_alignable  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

F = REPO_ROOT / "tests" / "fixtures" / "gpc_summary_export_synthetic_absences.csv"
WHEN = "2026-08-27T00:00:00Z"
FLAGS = {"DETECTOR_SATURATED": "above_range", "RUN_FAILED": "lost_in_acquisition",
         "MISSING": "not_measured", "BELOW_QUANT_LIMIT": "below_detection"}


def adapter(**over):
    base = dict(path=F, source_name="s", retrieved_at=WHEN,
                data_provenance="fabricated_fixture", sample_kind="sample", method="m",
                unit_by_column={"Mw": "g/mol", "Mn": "g/mol"},
                kind_by_column={"Mw": "measured", "Mn": "measured"},
                flag_by_column={"Mw": "Mw_Flag", "Mn": "Mn_Flag"},
                absence_reason_by_flag=dict(FLAGS))
    base.update(over)
    return GpcSummaryExportSourceAdapter(**base)


def observations(**over):
    pool = EvidencePool()
    run_scout(adapter(**over), GpcReportExtractor(), pool)
    return sorted(pool.all_observations(), key=lambda o: o.id)


def test_the_absence_vocabulary_is_no_longer_unexercised():
    """Four of five reasons now arrive from a source that stated them."""
    seen = {o.content["value_absence"] for o in observations() if "value_absence" in o.content}
    assert seen == {"above_range", "below_detection", "not_measured", "lost_in_acquisition"}
    assert set(ABSENCE_REASONS) - seen == {"withheld"}, (
        "the unexercised remainder must be named, not left as a gap nobody counted"
    )


def test_an_absent_cell_is_alignable_and_is_not_a_typed_quantity():
    """Both gates are right and they disagree, which is the point: a
    table can carry an absent cell, and an absence is not admissible as a
    canonical property assertion."""
    absent = [o for o in observations() if "value_absence" in o.content]
    assert absent
    for o in absent:
        assert observation_is_table_alignable(o.content).admissible
        assert "MISSING_VALUE" in quantity_is_typed(o.content).reasons


def test_an_unexplained_blank_is_refused_rather_than_given_a_reason():
    """A blank cell says THAT a value is missing and never WHY. Guessing
    the reason is the fabrication the vocabulary exists to prevent."""
    with pytest.raises(GpcSummaryExportFetchError, match="no absence reason is declared"):
        adapter(absence_reason_by_flag={}).fetch()


def test_unknown_absence_reason_is_now_reachable_from_acquisition():
    """It was in WO-4's `content cannot express the violation` set. A
    caller mapping a flag onto a reason outside the closed vocabulary
    reaches it -- and the extractor deliberately does NOT validate
    membership, because that is science/table.py's judgement."""
    poisoned = dict(FLAGS, DETECTOR_SATURATED="detector_broke")
    codes = set()
    for o in observations(absence_reason_by_flag=poisoned):
        codes |= set(observation_is_table_alignable(o.content).reasons)
    assert "UNKNOWN_ABSENCE_REASON" in codes


def test_value_and_absence_together_is_refused_at_the_extractor():
    """Still pre-empted, and by name."""
    from evidence.types import make_record
    import json

    payload = json.loads(adapter().fetch()[0].content)
    payload["measurements"][0]["value_absence"] = "not_measured"
    payload["measurements"][0]["value"] = 1.0
    record = make_record(document_id="d", locator="l", raw_content=json.dumps(payload))
    with pytest.raises(GpcReportExtractionError, match="both a value and an absence"):
        GpcReportExtractor().extract(record)


def test_the_in_range_sentinel_is_still_admitted_as_a_measurement():
    """THE STOP CONDITION, measured rather than argued.

    Row 6 reports Mn = -999 with its flag set to OK: the source asserts
    the sentinel IS a measurement. Every gate admits it with no code. The
    flag is the only thing that could have distinguished it and the flag
    says the opposite.

    Left admitted deliberately. Coercing it to absent would be
    fabrication in the direction that looks helpful, and a sentinel
    denylist is the enumeration shape PDI already showed the cost of."""
    sentinels = [o for o in observations() if o.content.get("value") == -999.0]
    assert len(sentinels) == 1, "the fixture must carry exactly one sentinel-flagged-OK row"
    content = sentinels[0].content
    assert observation_is_table_alignable(content).admissible
    assert quantity_is_typed(content).admissible
    assert no_context_free_property(content).admissible


def test_the_flag_disambiguates_the_other_sentinel():
    """Row 4 also reports -999, flagged MISSING. The flag is believed and
    the number is discarded -- so a sentinel IS distinguishable when the
    source itself says so, and only then."""
    absent_not_measured = [o for o in observations()
                           if o.content.get("value_absence") == "not_measured"]
    assert len(absent_not_measured) == 1
    assert absent_not_measured[0].content["value"] is None
