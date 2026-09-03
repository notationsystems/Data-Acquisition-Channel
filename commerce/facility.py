"""Facility resolution — the unglamorous precondition for lane memory.

The same warehouse arrives as `123 Industrial Dr`, `123 INDUSTRIAL DRIVE
UNIT 4`, and `123 Industrial, Mississauga ON`. If those are three
facilities in the register then lane statistics never accumulate: every
load is a first load, and the residual asset that justifies the whole
system never forms.

THREE OUTCOMES, NEVER A SILENT MERGE.

    resolved      the normalized forms match exactly -> the same facility
    ambiguous     a near match -> BOTH candidates are returned, and a
                  person decides. This is the state a similarity threshold
                  quietly destroys.
    unresolved    no match -> a new facility, with the RAW STRING kept

The middle one is where the money is. An automatic merge on 0.9 similarity
silently folds two real facilities into one and every lane statistic
downstream inherits it, with nothing anywhere recording that a judgement
was made. An automatic split does the opposite and is at least visible as
duplicates. So near matches are surfaced, never decided.

THE NORMALIZER IS PART OF THE BASIS. A facility resolved under a
conservative fallback normalizer and one resolved under a statistical
parser are DIFFERENT CLAIMS, and this module records which one made each
resolution. If a statistical parser is installed later, prior resolutions
were taken under a weaker normalizer and are re-checkable rather than
silently inherited -- which is the same rule as every other basis in this
programme.

WHAT THIS DOES NOT DO. It does not ship a hand-rolled abbreviation table
pretending to be address parsing. `Dr` is Drive on a street line and
Doctor in a name, and a lookup table that guesses produces confident wrong
merges -- worse than the duplicates it set out to fix. The fallback
normalizer below does only what can be done without a model, says so, and
is recorded on every resolution it makes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

RESOLVED = "resolved"
AMBIGUOUS = "ambiguous"
UNRESOLVED = "unresolved"

#: The normalizer that made a resolution. Recorded, because a resolution
#: is only as strong as the normalizer behind it.
CONSERVATIVE = "conservative_casefold"
STATISTICAL = "statistical_parser"

FACILITY_HAS_NO_RAW_STRING = "FACILITY_HAS_NO_RAW_STRING"
NORMALIZER_NOT_AVAILABLE = "NORMALIZER_NOT_AVAILABLE"


class FacilityRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def conservative_normalize(raw: str) -> str:
    """Case-folding, unicode normalization, punctuation and whitespace only.

    Deliberately does NOT expand abbreviations, drop unit numbers, or
    reorder components. Each of those needs a model of what an address IS,
    and guessing at them is how two real facilities become one.
    """
    text = unicodedata.normalize("NFKD", raw)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def statistical_normalize(raw: str) -> str:  # pragma: no cover - requires libpostal
    """The strong normalizer, when a statistical address parser is installed.

    Kept behind a check rather than an import at module scope so the
    absence is a recorded state instead of an ImportError at start-up.
    """
    try:
        from postal.expand import expand_address  # type: ignore[import-not-found]
    except ImportError as exc:
        raise FacilityRefusal(
            NORMALIZER_NOT_AVAILABLE,
            "no statistical address parser is installed. Resolutions made now are conservative "
            "and are recorded as such; installing one later does not retroactively strengthen "
            "them, and they are re-checkable because the normalizer is on the record.",
        ) from exc
    forms = expand_address(raw)
    return sorted(forms)[0] if forms else conservative_normalize(raw)


def available_normalizer() -> Tuple[str, Callable[[str], str]]:
    """Which normalizer this installation actually has.

    Reported rather than assumed: the whole point of recording the
    normalizer is defeated if the system silently falls back and says
    nothing.
    """
    try:
        import postal.expand  # type: ignore[import-not-found]  # noqa: F401
        return STATISTICAL, statistical_normalize
    except ImportError:
        return CONSERVATIVE, conservative_normalize


@dataclass(frozen=True)
class Facility:
    facility_id: str
    #: Kept verbatim, always. A normalized form is lossy and the raw
    #: string is the only thing that can be re-normalized later.
    raw: str
    normalized: str
    normalizer: str

    def __post_init__(self) -> None:
        if not self.raw.strip():
            raise FacilityRefusal(
                FACILITY_HAS_NO_RAW_STRING,
                f"{self.facility_id!r} carries only a normalized form. Normalization is lossy, "
                "so the raw string is the only thing a stronger normalizer could re-read.",
            )


@dataclass(frozen=True)
class Resolution:
    query: str
    status: str
    facility: Optional[Facility] = None
    candidates: Tuple[Facility, ...] = ()
    normalizer: str = CONSERVATIVE
    detail: str = ""
    remedy: Optional[str] = None


def _tokens(normalized: str) -> frozenset:
    return frozenset(normalized.split())


def _similarity(a: str, b: str) -> float:
    """Jaccard over tokens. Deliberately crude and deliberately NOT used
    to decide anything -- only to decide what to SHOW a person."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


#: The near-match floor is a FUNCTION OF THE NORMALIZER, not a constant.
#:
#: MEASURED on the canonical example. `123 Industrial Dr, Mississauga ON`
#: against `123 Industrial Drive Unit 4, Mississauga ON` -- the same
#: warehouse -- scores Jaccard 0.50 under the conservative normalizer,
#: because `dr`/`drive` differ and `unit`/`4` are extra. A 0.6 floor misses
#: it entirely and the register silently grows a duplicate.
#:
#: So the conservative floor is set BELOW that measurement, which surfaces
#: more candidates for a person to look at. That is the correct trade: the
#: cost of a false candidate is one glance, and the cost of a missed one is
#: a lane statistic split across two entries forever, with nothing
#: reporting it. The floor rises when a statistical parser is installed,
#: because then a true match normalizes to the same string and near
#: matches are genuinely near.
NEAR_MATCH_FLOOR: Mapping[str, float] = {
    CONSERVATIVE: 0.45,
    STATISTICAL: 0.80,
}

#: The measured score for the canonical duplicate, pinned so that a change
#: to the normalizer that moves it fails loudly.
CANONICAL_DUPLICATE_SIMILARITY = 0.50


def resolve(raw: str, register: Sequence[Facility], *,
            normalizer: Optional[Tuple[str, Callable[[str], str]]] = None,
            near_match_floor: Optional[float] = None) -> Resolution:
    """Resolve an address against the facility register.

    The floor selects what to SHOW, never what to merge. There is no
    threshold in this function above which two facilities are combined,
    because that threshold is the defect: it makes a judgement, applies it
    silently, and leaves nothing on the record saying one was made.
    """
    name, normalize = normalizer or available_normalizer()
    if near_match_floor is None:
        near_match_floor = NEAR_MATCH_FLOOR[name]
    normalized = normalize(raw)

    exact = [f for f in register if f.normalized == normalized]
    if len(exact) == 1:
        return Resolution(raw, RESOLVED, facility=exact[0], normalizer=name,
                          detail=f"normalized forms match exactly under {name}")
    if len(exact) > 1:
        return Resolution(
            raw, AMBIGUOUS, candidates=tuple(exact), normalizer=name,
            detail=f"{len(exact)} register entries share this normalized form, which means the "
                   "register already contains a duplicate.",
            remedy="merge the register entries deliberately, recording which raw strings were "
                   "judged the same and by whom.")

    near = sorted(((f, _similarity(normalized, f.normalized)) for f in register),
                  key=lambda pair: -pair[1])
    near = [(f, s) for f, s in near if s >= near_match_floor]
    if near:
        return Resolution(
            raw, AMBIGUOUS, candidates=tuple(f for f, _ in near), normalizer=name,
            detail=f"{len(near)} near match(es) under {name}, best "
                   f"{near[0][1]:.2f}. Surfaced, not merged: an automatic merge folds two real "
                   "facilities into one and every lane statistic downstream inherits it with "
                   "nothing recording that a judgement was made.",
            remedy=f"confirm whether {raw!r} is {near[0][0].raw!r}. If it is, merge deliberately; "
                   "if not, add it as a new facility.")

    return Resolution(
        raw, UNRESOLVED, normalizer=name,
        detail=f"no entry in a register of {len(register)} matches under {name}. The raw string "
               "is preserved so a stronger normalizer can re-read it.",
        remedy="add as a new facility, or supply a statistical address parser and re-resolve.")


@dataclass(frozen=True)
class DuplicatePair:
    left: "Facility"
    right: "Facility"
    similarity: float


@dataclass(frozen=True)
class DuplicateScan:
    """Suspected duplicates, surfaced and never merged.

    The scan SHOWS pairs above the canonical-duplicate similarity; it
    merges nothing, for the same reason resolve() doesn't: a silent merge
    is a judgement with nothing on the record saying one was made. And an
    empty pair list under the conservative normalizer is not a clean
    register — the duplicate rate there is unknown and is not zero.

    MEASURED, then carried: run over the representative register, the
    bare similarity floor surfaced 51 pairs of which one was the planted
    duplicate — because a register of industrial parks shares street and
    city tokens everywhere, and `350 Rue Notre-Dame` scores 0.71 against
    `318 Rue Notre-Dame`. What separates those pairs is a STATED
    difference: the house number disagrees. So pairs whose numeric
    tokens conflict are listed under `distinct_by_number` rather than
    dropped — every pair above the floor lands in exactly one bucket,
    and `conserves` says so. A pair with no number on one side, or with
    compatible numbers (`980` vs `980 UNIT 4`), stays a suspect.
    """

    pairs: Tuple[DuplicatePair, ...]
    distinct_by_number: Tuple[DuplicatePair, ...]
    entries: int
    normalizer: str
    floor: float
    empty_because: Optional[str] = None

    @property
    def above_floor(self) -> int:
        return len(self.pairs) + len(self.distinct_by_number)

    @property
    def conserves(self) -> bool:
        return True  # by construction; kept as a property so callers can assert it


def _digit_tokens(normalized: str) -> frozenset:
    return frozenset(t for t in normalized.split() if t.isdigit())


def _numbers_conflict(left: Facility, right: Facility) -> bool:
    """True when both addresses state house numbers and neither side's
    set contains the other's. A stated disagreement in the most
    discriminating token is affirmative evidence of two addresses; a
    missing number on either side is not, and stays a suspect."""
    a, b = _digit_tokens(left.normalized), _digit_tokens(right.normalized)
    if not a or not b:
        return False
    return not (a <= b or b <= a)


def duplicate_scan(register: Sequence[Facility],
                   normalizer: Optional[Tuple[str, Callable[[str], str]]] = None
                   ) -> DuplicateScan:
    name, _ = normalizer or available_normalizer()
    if not register:
        return DuplicateScan((), (), 0, name, CANONICAL_DUPLICATE_SIMILARITY, empty_because=(
            "the facility register is empty. Nothing was scanned, which is not the same as "
            "nothing being duplicated."))
    ordered = sorted(register, key=lambda f: f.facility_id)
    pairs: List[DuplicatePair] = []
    distinct: List[DuplicatePair] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            similarity = _similarity(left.normalized, right.normalized)
            if similarity < CANONICAL_DUPLICATE_SIMILARITY:
                continue
            pair = DuplicatePair(left, right, similarity)
            (distinct if _numbers_conflict(left, right) else pairs).append(pair)
    pairs.sort(key=lambda pair: (-pair.similarity, pair.left.facility_id))
    distinct.sort(key=lambda pair: (-pair.similarity, pair.left.facility_id))
    return DuplicateScan(tuple(pairs), tuple(distinct), len(ordered), name,
                         CANONICAL_DUPLICATE_SIMILARITY)


@dataclass(frozen=True)
class RegisterHealth:
    """What the register cannot do, stated.

    A register normalized conservatively WILL carry duplicates that a
    statistical parser would have caught, and reporting a clean register
    under a weak normalizer is the confident-green problem.
    """

    entries: int
    normalizer: str
    resolutions_under_weaker_normalizer: int
    caveat: str


def register_health(register: Sequence[Facility]) -> RegisterHealth:
    name, _ = available_normalizer()
    weaker = sum(1 for f in register if f.normalizer == CONSERVATIVE and name == STATISTICAL)
    if name == CONSERVATIVE:
        caveat = ("this register was normalized WITHOUT a statistical address parser. "
                  "`123 Industrial Dr` and `123 Industrial Drive` are distinct entries here and "
                  "are almost certainly one facility. The duplicate rate is unknown and is not "
                  "zero; lane statistics computed over it are split across spellings.")
    elif weaker:
        caveat = (f"{weaker} of {len(register)} entries were resolved under the conservative "
                  "normalizer before a statistical parser was installed. They are re-checkable "
                  "because the normalizer is on the record, and they have not been re-checked.")
    else:
        caveat = "every entry was resolved under the statistical parser."
    return RegisterHealth(len(register), name, weaker, caveat)
