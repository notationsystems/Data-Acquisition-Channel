"""THE SWEEP'S ONE REPAIR: an enumeration that stands for a set nobody
checks it against.

D-3 asked which checks in this repository could report a verdict about
something other than the artifact in use, and named three candidate
shapes. Two came back clean. This is the third: `daf/storage/durable_pool.py`
enumerates the evidence categories it fingerprints as two literal tuples,
and the set they stand for lives in the VENDORED pool, which moves.

MEASURED, AND THE HAZARD IS LATENT RATHER THAN FIRED. The submodule pin
moved once inside the window this order concerns -- 3e5bea9 to 5e146d5 --
and EvidencePool's collections are identical across both, so the
enumeration has never yet been wrong. That is a fact about the two pins,
not a property of the arrangement, and nothing was checking it.

`fingerprint_history` is excluded and must stay excluded: it is where the
fingerprints are kept, and including it would fingerprint the record of
the fingerprints.
"""

from __future__ import annotations

import inspect
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.storage import durable_pool  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402

#: Collections of the vendored pool that are deliberately NOT
#: fingerprinted, each with the reason. A new exclusion has to be
#: argued here rather than added to a tuple.
NOT_FINGERPRINTED = {
    "fingerprint_history": "it is where the fingerprints are kept; including it would "
                           "fingerprint the record of the fingerprints",
}


def pool_collections():
    """Derived from the vendored class, not listed. If the pin moves and
    the pool grows a collection, this grows with it."""
    source = inspect.getsource(EvidencePool)
    return set(re.findall(r"self\._([a-z_]+)\s*[:=]", source))


def test_the_fingerprinted_categories_cover_every_collection_the_pool_holds():
    """THE DERIVATION. An enumeration that silently omits a collection
    produces a durable fingerprint that is correct about what it examined
    and silent about what it did not."""
    fingerprinted = (set(durable_pool._INDEXED_FINGERPRINT_CATEGORIES)
                     | set(durable_pool._SCANNED_FINGERPRINT_CATEGORIES))
    collections = pool_collections()

    unaccounted = collections - fingerprinted - set(NOT_FINGERPRINTED)
    assert unaccounted == set(), (
        f"the pool holds {sorted(unaccounted)}, which is neither fingerprinted nor listed as a "
        "deliberate exclusion. A pin that adds a collection must fail here rather than produce a "
        "fingerprint that quietly omits it."
    )

    stale = set(NOT_FINGERPRINTED) - collections
    assert stale == set(), (
        f"{sorted(stale)} is excluded and no longer exists in the pool; an exclusion outliving "
        "its subject is a rule about nothing"
    )

    overreach = fingerprinted - collections
    assert overreach == set(), f"fingerprinting {sorted(overreach)}, which the pool does not hold"


def test_the_domain_is_non_empty_and_the_exclusion_is_real():
    """Asserted before the coverage claim. A derivation that found no
    collections would report full coverage of nothing."""
    collections = pool_collections()
    assert len(collections) >= 8, f"only found {sorted(collections)}"
    assert "observations" in collections and "records" in collections
    assert set(NOT_FINGERPRINTED) < collections, (
        "the exclusion must name a collection that actually exists"
    )
    for reason in NOT_FINGERPRINTED.values():
        assert len(reason) > 30, "an exclusion without a reason is a tuple entry with a comment"


def test_the_hazard_is_recorded_as_latent_rather_than_as_a_defect():
    """The pin moved once in the window and the collections did not
    change, so this guard has never yet caught anything. Stated, because
    a guard described as having closed a live defect when it closed a
    latent one is the attribution failure this repository files."""
    import subprocess

    def collections_at(sha):
        source = subprocess.run(
            ["git", "-C", str(REPO_ROOT / "vendor" / "scout-retrieval-agent"),
             "show", f"{sha}:evidence/pool.py"], capture_output=True, text=True).stdout
        return set(re.findall(r"self\._([a-z_]+)\s*[:=]", source))

    before = collections_at("3e5bea973d0e801eadfb9d472aa3d07c930616c3")
    after = collections_at("5e146d5924675cd7b6e1d1ed44fb39f5da012610")
    if not before or not after:
        import pytest
        pytest.skip("the submodule objects for both pins are not available in this clone")
    assert before == after, (
        "the pin move DID change the pool's collections, so this hazard fired rather than "
        "remaining latent -- re-report it as a defect that landed"
    )
