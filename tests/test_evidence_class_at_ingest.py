"""The evidence class the extractor verifies, recorded and recovered.

Every claim in architecture/evidence_class_at_ingest.yaml is re-executed
here against the real acquisition path.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import GpcReportSourceAdapter  # noqa: E402
from daf.adapters.gpc_summary_export import GpcSummaryExportSourceAdapter  # noqa: E402
from daf.extractors.gpc_report import GpcReportExtractor  # noqa: E402
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy  # noqa: E402
from daf.storage.filesystem_store import FilesystemEvidenceStore  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from epistemics.evidence_class import (COMPUTED, MEASURED,  # noqa: E402
                                       ClassRegister, ClassReassignment,
                                       make_class_assignment)
from evidence.pool import EvidencePool  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "evidence_class_at_ingest.yaml").read_text())
FIXTURES = REPO_ROOT / "tests" / "fixtures"
F1 = FIXTURES / "gpc_report_synthetic_ps4471.json"
F2 = FIXTURES / "gpc_summary_export_synthetic_vendor.csv"
WHEN = "2026-08-27T00:00:00Z"
DECL = dict(data_provenance="fabricated_fixture", sample_kind="sample", method="m",
            unit_by_column={"Mw": "g/mol", "PDI": "dimensionless"},
            kind_by_column={"Mw": "measured", "PDI": "derived"})


def _classified(by_source_kind, adapter):
    root = pathlib.Path(tempfile.mkdtemp())
    pool = ClassifiedPool(
        FilesystemEvidenceStore(root / "ev"),
        SourceClassPolicy(id="source_policy:gpc", by_source_kind=by_source_kind),
    )
    run_scout(adapter, GpcReportExtractor(), pool)
    return pool


def report_adapter():
    return GpcReportSourceAdapter(path=F1, source_name="s", retrieved_at=WHEN)


def export_adapter():
    return GpcSummaryExportSourceAdapter(path=F2, source_name="s", retrieved_at=WHEN, **DECL)


@pytest.mark.parametrize("adapter_factory", [report_adapter, export_adapter])
def test_a_pooled_observations_class_is_recoverable(adapter_factory):
    """Demonstrated by reading one back, for BOTH sources -- the source
    kind is the same, so a policy that classified only one would be a
    fixture-shaped policy."""
    pool = _classified({"instrument_report": MEASURED}, adapter_factory())
    observations = list(pool.all_observations())
    assert observations

    by_evidence = {a.evidence_id: a for a in pool.classes.all_assignments()}
    for observation in observations:
        assignment = by_evidence.get(observation.id)
        assert assignment is not None, "an observation entered the pool unclassified"
        assert assignment.evidence_kind == "observation"
        assert assignment.evidence_class == MEASURED
        assert assignment.assigned_by == "source_policy:gpc", (
            "the declaring policy must travel with the class, or two policies disagreeing "
            "collapse into one that silently won"
        )


def test_classified_and_unclassified_are_distinguishable_in_the_pool():
    """THE DISCRIMINATING CASE. A test that only shows classification
    working passes whether or not the absence of it is detectable."""
    classified = _classified({"instrument_report": MEASURED}, report_adapter())
    unclassified = _classified({}, report_adapter())

    assert len(list(classified.all_observations())) == len(list(unclassified.all_observations()))
    assert list(classified.classes.all_assignments())
    assert not list(unclassified.classes.all_assignments()), (
        "an undeclared source kind must yield NO assignment rather than a guessed one -- a source "
        "nobody has classified is a source whose evidence nobody may assert"
    )


def test_a_recorded_class_disagreeing_with_another_is_refused_by_name():
    """DETECTOR PROOF for A.3."""
    register = ClassRegister()
    register.assign(make_class_assignment("a" * 64, "observation", MEASURED, "policy_one"))
    assert register.class_of("a" * 64) == MEASURED

    with pytest.raises(ClassReassignment, match="refusing to reclassify"):
        register.assign(make_class_assignment("a" * 64, "observation", COMPUTED, "policy_two"))


def test_the_same_class_from_a_different_policy_is_also_refused():
    """Sharper than the disagreement case: it refuses a second policy
    quietly AGREEING, which would otherwise erase that two declarations
    were in play. assigned_by participates in identity."""
    register = ClassRegister()
    register.assign(make_class_assignment("a" * 64, "observation", MEASURED, "policy_one"))
    with pytest.raises(ClassReassignment):
        register.assign(make_class_assignment("a" * 64, "observation", MEASURED, "policy_two"))

    # And re-ingest is not a reclassification.
    register.assign(make_class_assignment("a" * 64, "observation", MEASURED, "policy_one"))


def test_the_pdi_clause_is_blocked_by_the_absent_route_not_by_the_class_representation():
    """The acceptance criterion that cannot be met as stated, with the
    actual blocker measured rather than assumed."""
    # The class representation does NOT refuse the combination.
    assignment = make_class_assignment("b" * 64, "observation", COMPUTED, "p")
    assert assignment.evidence_class == COMPUTED

    # The blocker is that no such Observation is ever produced.
    from daf.extractors.gpc_report import GpcReportExtractionError
    with pytest.raises(GpcReportExtractionError, match="kind 'derived'"):
        run_scout(GpcReportSourceAdapter(
            path=FIXTURES / "gpc_report_synthetic_derived_column.json",
            source_name="s", retrieved_at=WHEN), GpcReportExtractor(), EvidencePool())

    assert "no such Observation exists to classify" in RECORD[
        "the_pdi_clause_cannot_be_satisfied_as_stated"]["the_actual_blocker"]


def test_using_a_classified_pool_moves_nothing_across_the_boundary():
    """The Phase A STOP condition, checked rather than assumed."""
    assert isinstance(_classified({"instrument_report": MEASURED}, report_adapter()), EvidencePool)

    from evidence.types import Observation
    assert "evidence_class" not in Observation.__dataclass_fields__, (
        "the class must be carried BESIDE the object, not added to the vendored type"
    )
    pipeline = (REPO_ROOT / "vendor" / "scout-retrieval-agent" / "scout" / "pipeline.py").read_text()
    assert "ClassifiedPool" not in pipeline and "EvidenceClassAssignment" not in pipeline, (
        "the vendored pipeline must remain untouched; it accepts any EvidencePool by type"
    )


def test_the_record_states_the_wo4_misattribution():
    """A measurement of what a PATH can do, taken against a harness that
    chose not to use the capability."""
    correction = RECORD["the_correction_to_wo4"]
    assert "about the GPC TEST HARNESS" in correction["what_is_actually_the_case"]
    assert "misattributed" in correction["why_the_error_is_worth_recording"]
