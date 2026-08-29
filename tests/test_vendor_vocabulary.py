"""The two Phase B findings measurable without the anchors.

Both are measurements OF THIS TREE, using the counterparty's corpus
observations as inputs. Neither anchor is present in this repository and
nothing here transcribes one.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import GpcReportSourceAdapter  # noqa: E402
from daf.extractors.gpc_report import (DERIVED_VARIABLES, GpcReportExtractor,  # noqa: E402
                                       _normalised)
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from science.admissibility import no_context_free_property  # noqa: E402
from science.table import observation_is_table_alignable  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "vendor_vocabulary.yaml").read_text())
F1 = REPO_ROOT / "tests" / "fixtures" / "gpc_report_synthetic_ps4471.json"

#: Spellings the counterparty reports observing across Waters, OMNISEC,
#: WinGPC and Agilent. Used as INPUTS to a measurement of this tree.
OBSERVED_PDI_SPELLINGS = ("PDI", "Polydispersity", "Polydispersity Index",
                          "Mw/Mn", "Mw/Mn (PDI)", "D", "PD")
OBSERVED_MOMENTS = ("Mz", "Mz+1", "Mz1", "Mv", "Mp")


def _admits(variable):
    report = json.loads(F1.read_text())
    for run in report["runs"]:
        run["measurements"] = [dict(run["measurements"][0], variable=variable)]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(report, fh)
        path = pathlib.Path(fh.name)
    try:
        pool = EvidencePool()
        run_scout(GpcReportSourceAdapter(path=path, source_name="s",
                                         retrieved_at="2026-08-27T00:00:00Z"),
                  GpcReportExtractor(), pool)
        observation = next(iter(pool.all_observations()))
        return (observation_is_table_alignable(observation.content).admissible
                and no_context_free_property(observation.content).admissible)
    finally:
        path.unlink(missing_ok=True)


def test_the_normalised_denylist_catches_three_of_seven_observed_spellings():
    """B.2.1 CONFIRMED, and worse than stated: the WO-3 normalisation
    repair still misses four of seven real spellings. Normalisation
    cannot close a set the domain keeps extending."""
    caught = {s for s in OBSERVED_PDI_SPELLINGS if _normalised(s) in DERIVED_VARIABLES}
    assert caught == {"PDI", "Polydispersity Index", "Mw/Mn"}, (
        f"the caught set moved to {sorted(caught)}; the record's count needs re-measuring"
    )
    missed = set(OBSERVED_PDI_SPELLINGS) - caught
    assert missed == {"Polydispersity", "Mw/Mn (PDI)", "D", "PD"}
    assert "THREE of the seven" in RECORD["pdi_has_no_canonical_spelling"]["measured_against_this_tree"]


def test_the_denylist_is_not_the_protection_and_the_declared_kind_is():
    """A vendor spelling nobody listed cannot enter as `measured` by
    default -- it cannot enter at all."""
    from daf.extractors.gpc_report import GpcReportExtractionError

    report = json.loads(F1.read_text())
    for run in report["runs"]:
        for measurement in run["measurements"]:
            measurement["variable"] = "PD"          # an unlisted spelling
            measurement.pop("kind")                  # and no declared kind
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(report, fh)
        path = pathlib.Path(fh.name)
    try:
        with pytest.raises(GpcReportExtractionError, match="must declare that kind explicitly"):
            run_scout(GpcReportSourceAdapter(path=path, source_name="s",
                                             retrieved_at="2026-08-27T00:00:00Z"),
                      GpcReportExtractor(), EvidencePool())
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.parametrize("moment", OBSERVED_MOMENTS)
def test_no_moment_is_rejected_because_there_is_no_moment_schema(moment):
    """B.2.2 CONTRADICTED for this repository. The question was whether
    the vocabulary REJECTS Mz/Mp or ADMITS them untyped. Neither -- there
    is no vocabulary. Every moment is admitted with both gates clean."""
    assert _admits(moment), f"{moment} is refused; the record says nothing rejects it"


def test_the_variable_identity_is_an_open_string_by_design():
    source = (REPO_ROOT / "science" / "table.py").read_text()
    for schema_name in ("VARIABLE_VOCABULARY", "KNOWN_VARIABLES", "MOMENTS", "PERMITTED_VARIABLES"):
        assert schema_name not in source, (
            f"science/table.py now names {schema_name}; a moment schema exists and B.2.2's "
            "premise may hold after all"
        )
    # Asserted on the VALUE. The first draft looked for text that appears
    # in the KEY -- the second time in this program a check has read its
    # own index instead of its content, both times by the same author in
    # the same construction.
    verdict = RECORD["the_moment_schema"]["so_the_finding_does_not_describe_this_tree"]
    assert "DAQ does not" in verdict
    assert "checked for presence and type and never for membership" in verdict


def test_mp_and_mv_are_admitted_as_peers_of_the_power_average_moments():
    """The defect that IS live: nothing records that Mp is a mode rather
    than a power-average moment, or that Mv is method-dependent through
    Mark-Houwink alpha. A consumer computing a ratio over them gets a
    number with no complaint from any gate."""
    assert _admits("Mp") and _admits("Mn") and _admits("Mv")
    assert "arriving through admission rather than through a schema" in RECORD[
        "the_moment_schema"]["which_changes_which_defect_is_live"]


def test_no_anchor_has_been_transcribed():
    """The phase rests on two real reports this repository does not have.
    A transcription of a document DAQ has not read would be fabricated
    provenance -- worse than a plausible convention, because it would
    carry a named real source."""
    fixtures = {p.name.lower() for p in (REPO_ROOT / "tests" / "fixtures").iterdir()}
    for anchor in ("omnisec", "wingpc", "polyanalytik", "pss", "cir"):
        assert not any(anchor in name for name in fixtures), (
            f"a fixture named for the {anchor} anchor exists; if it is a real transcription this "
            "test should be retired, and if it is not, it must not be named for a real source"
        )
    assert "fabricated provenance" in RECORD["what_daq_has_not_done"]
