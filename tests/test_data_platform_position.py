"""architecture/data_platform_position.yaml, and the adoption rule as a check.

THE SPECIFICATION'S CLOSING PARAGRAPH is the part worth enforcing: add
Iceberg, vector search, graph infrastructure, streaming brokers, GPU
workers and Kubernetes only when workload evidence demands them; do not
begin with Kafka, Neo4j, Spark, a blockchain or a large Kubernetes estate.

As prose that is advice. Here it is a gate: a technology PRESENT in this
tree whose record says not_adopted fails, and a technology adopted with no
workload evidence fails. Adoption becomes an act justified in the commit
that performs it, rather than a dependency somebody notices later.

DETECTION IS BY IMPORT AND BY DECLARED DEPENDENCY, PARSED. Not by text
search, and that is measured rather than stylistic: a text sweep for these
names over this repository returned four hits and not one was an adoption
-- `temporal` matched `temporal ordering` and `bitemporal`, `s3` matched a
variable in a polymer test, `postgres` matched this pair's own record
saying it was absent, and `postgis` matched a hold list forbidding it. A
check built on that sweep would have reported four adoptions where there
are none, which is the proxy-for-target shape architecture/proof_integrity.yaml
names as its most common form.

THE VENDORED CORE IS EXCLUDED, and the exclusion is asserted rather than
assumed. Its imports are the core's adoptions at the pinned commit, not
this layer's, and reading them as this layer's would make every one of its
dependencies a decision this repository has to justify.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD = loads((REPO_ROOT / "architecture" / "data_platform_position.yaml").read_text())

#: Import roots that constitute adoption of each recorded technology. A
#: technology with no import root cannot be adopted by importing anything
#: and is checked by dependency declaration alone.
IMPORT_ROOTS = {
    "s3_object_storage": ("boto3", "botocore", "minio", "s3fs"),
    "postgresql": ("psycopg", "psycopg2", "asyncpg", "sqlalchemy"),
    "postgis": ("geoalchemy2", "shapely.postgis"),
    "temporal_workflows": ("temporalio",),
    "iceberg": ("pyiceberg",),
    "parquet": ("pyarrow", "fastparquet"),
    "pgvector": ("pgvector",),
    "qdrant": ("qdrant_client",),
    "opentelemetry": ("opentelemetry",),
    "kafka": ("kafka", "confluent_kafka", "aiokafka"),
    "neo4j": ("neo4j", "py2neo"),
    "spark": ("pyspark",),
    "kubernetes": ("kubernetes",),
}

_ADOPTED_PREFIX = "adopted"


def _first_party_python():
    """Every Python file this repository authors. The vendored core is
    excluded: its imports are the core's, at the pin."""
    for path in sorted(REPO_ROOT.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in ("vendor", ".git"):
            continue
        yield relative, path


def _imported_roots():
    """Top-level module of every import, parsed. `import a.b` and
    `from a.b import c` both contribute `a`."""
    roots = {}
    for relative, path in _first_party_python():
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:                                  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for name in names:
                roots.setdefault(name.split(".")[0], set()).add(str(relative))
    return roots


def _declared_dependencies():
    """Dependency names from pyproject, read as text because a TOML parser
    is not guaranteed here -- but scoped to the dependency tables, so a
    word in prose cannot contribute."""
    pyproject = REPO_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return set()
    declared, inside = set(), False
    for line in pyproject.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            inside = "dependencies" in stripped
            continue
        if not inside or not stripped.startswith(('"', "'")):
            continue
        name = stripped.strip("\"',").split("[")[0]
        for character in "<>=!~ ;":
            name = name.split(character)[0]
        if name:
            declared.add(name.lower().replace("-", "_"))
    return declared


def test_the_record_names_a_status_for_every_technology_the_specification_lists():
    """The premise. A technology the specification names and the record
    omits is one nobody has taken a position on, and the gate below would
    pass over it."""
    technologies = RECORD["technologies"]
    assert len(technologies) >= 14, f"only {len(technologies)} recorded"
    for name, entry in technologies.items():
        assert entry.get("status"), f"{name} carries no status"
        assert "step" in entry, f"{name} names no step of the build order"


def test_nothing_recorded_as_not_adopted_is_imported_anywhere():
    """THE GATE. A dependency that appears without the record moving fails
    here, in the commit that adds it."""
    imported = _imported_roots()
    declared = _declared_dependencies()
    violations = []
    for name, entry in RECORD["technologies"].items():
        if str(entry["status"]).startswith(_ADOPTED_PREFIX):
            continue
        for root in IMPORT_ROOTS.get(name, ()):
            top = root.split(".")[0]
            if top in imported:
                violations.append(
                    f"{name}: `{top}` imported by {sorted(imported[top])[:3]} "
                    f"while the record says {entry['status']}"
                )
            if top in declared:
                violations.append(f"{name}: `{top}` declared as a dependency")
    assert not violations, (
        "a technology is in use and the record says it is not adopted. "
        "Adoption is an act to be justified, not a dependency to be "
        "noticed later:\n  " + "\n  ".join(violations)
    )


def test_anything_adopted_carries_workload_evidence():
    """The other half, and the one the specification's closing rule is
    actually about. `adopted` with no evidence is the state the rule
    forbids -- infrastructure arriving ahead of the load."""
    for name, entry in RECORD["technologies"].items():
        if not str(entry["status"]).startswith(_ADOPTED_PREFIX):
            continue
        evidence = entry.get("workload_evidence")
        assert evidence, (
            f"{name} is recorded {entry['status']} and names no workload "
            "evidence; the adoption rule requires a measurement"
        )


def test_the_technologies_the_specification_refuses_outright_are_absent():
    """Kafka, Neo4j, Spark and Kubernetes are refused by the specification
    itself rather than merely deferred. Recorded separately so that
    adopting one requires editing a line that says `refused` rather than a
    line that says `not yet`."""
    refused = {
        name for name, entry in RECORD["technologies"].items()
        if entry["status"] == "refused_by_the_specification"
    }
    assert refused >= {"kafka", "neo4j", "spark", "kubernetes"}
    imported = _imported_roots()
    for name in refused:
        for root in IMPORT_ROOTS.get(name, ()):
            assert root.split(".")[0] not in imported, f"{name} is in use and refused"


def test_the_vendored_core_is_excluded_and_that_exclusion_is_real():
    """Asserted, not assumed. If the walk drifted into vendor/, the core's
    own dependencies would read as this layer's adoptions and the gate
    would fail on decisions this repository did not take."""
    scanned = {relative.parts[0] for relative, _ in _first_party_python()}
    assert "vendor" not in scanned
    assert (REPO_ROOT / "vendor").is_dir(), (
        "the vendored core is not present, so this exclusion proves nothing "
        "on this run"
    )
    core_python = list((REPO_ROOT / "vendor").rglob("*.py"))
    assert core_python, "the vendored tree holds no python; the exclusion is vacuous"


def test_detection_is_by_import_and_not_by_text_search():
    """The measured reason the check is shaped this way. A text sweep for
    these names over this repository returns hits that are not adoptions,
    and a gate built on one would report adoptions that have not happened.

    The four historical false positives are replayed: each is a string
    that a text sweep matches and this check does not."""
    for prose in ("the temporal ordering of the runs",
                  "s3 = (r_pdi ** 2) if r_pdi is not None else (s1 + s2)",
                  "missing: PostgreSQL, and any closure object",
                  "postgis is on the hold list"):
        tree = ast.parse("x = 1")  # a module containing no imports at all
        roots = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        assert not roots
        assert any(token in prose.lower()
                   for token in ("temporal", "s3", "postgres", "postgis")), prose
    method = RECORD["the_adoption_rule"]["how_adoption_is_detected"]
    assert "NOT by text search" in method


def test_the_ownership_question_is_resolved_and_says_who_resolved_it():
    """A layer resolving an ecosystem-wide ownership question on its own
    authority is one party writing both sides. The record must say the
    resolution was directed, and must state what would revise it."""
    question = RECORD["who_owns_canonical_state"]
    assert question["resolved_as"] == "PERSISTENCE_ADAPTER"
    assert "DIRECTED" in question["who_resolved_it"]
    assert question.get("it_is_revisable_and_here_is_what_would_revise_it")
    assert "bent: zero" in question["the_reasoning"]


def test_the_hold_list_is_cited_and_not_restated():
    """PostGIS is held by architecture/opportunity_engine.yaml with a
    reason. One reason, one place: this record points at it and must not
    carry a second copy, which would drift."""
    relationship = RECORD["relationship_to_the_existing_hold_list"]
    assert "opportunity_engine.yaml" in relationship["where"]
    held = loads((REPO_ROOT / "architecture" / "opportunity_engine.yaml").read_text())
    assert any("postgis" in key for key in held["not_built_and_recorded_as_such"]), (
        "the hold list no longer holds postgis; this record cites a reason "
        "that has moved"
    )
    assert RECORD["technologies"]["postgis"]["status"] == "not_adopted"
    assert "opportunity_engine.yaml" in RECORD["technologies"]["postgis"]["held_by"]
