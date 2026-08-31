"""PC-6 Parts C, D and E — the vetting record model, its validWhile
predicates, and the three-state gate.

PART C. Carriers are ENTITIES; vetting facts are OBSERVATIONS with a
`known_at`; nothing is a boolean field on the carrier. The difference is
not stylistic. `carrier.insured = True` cannot answer "was it insured on
the ninth", cannot be superseded without losing what it said before, and
cannot carry which rung served it. An observation can answer all three,
and those are the three questions a liability turns on.

PART D. The validWhile predicates are the substrate's own mechanism
pointed at liability rather than at a deferred decision. The case that
matters is a predicate that lapses BETWEEN BOOKING AND PICKUP: the
certificate was valid when you tendered and is not valid when the truck
arrives, and only a record separating `known_at` from the period can tell
you which of those you are looking at.

REFRESH INTERVAL IS ITSELF A PREDICATE. A vetting record older than its
interval does not mean the carrier is bad. It means you do not currently
know, and that is the third state rather than a failure.

PART E. Three states, because a boolean collapses `undetermined` into
whichever way the code happens to fail. Fail-closed and an unreachable
registry looks like a fraudulent carrier; fail-open and it looks like a
clean one. Both report a fact about the CARRIER when the observable was a
fact about the CHECK.

THE GATE IS DETERMINISTIC AND SITS ABOVE THE AGENT LAYER. No agent may
override it and no agent may issue a tender against a carrier that is not
cleared. That is PC-5 with teeth in the place where teeth matter, and it
is enforced by a source scan rather than by this paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------
# The acquisition ladder. Every observation carries the rung that served
# it, and a verdict served from a snapshot states its age.
# ---------------------------------------------------------------------

#: A licensed commercial wrapper. Current, costs money, works today.
RUNG_COMMERCIAL = 0
#: The official API. Written and dormant while it is unavailable.
RUNG_OFFICIAL_API = 1
#: Bulk and historical datasets. THE PRIMARY for anything time-based,
#: because a current snapshot cannot support a validWhile predicate and a
#: historical series can.
RUNG_BULK_HISTORY = 2
#: Official web systems, current-snapshot only.
RUNG_OFFICIAL_SNAPSHOT = 3
#: A committed snapshot, with its age stated.
RUNG_COMMITTED_SNAPSHOT = 4

RUNG_NAMES: Mapping[int, str] = {
    RUNG_COMMERCIAL: "commercial_wrapper",
    RUNG_OFFICIAL_API: "official_api",
    RUNG_BULK_HISTORY: "bulk_history",
    RUNG_OFFICIAL_SNAPSHOT: "official_snapshot",
    RUNG_COMMITTED_SNAPSHOT: "committed_snapshot",
}



# Source classes. `sourceClass` matters more here than in commodities
# because the interested party is in the room.
REPORTED = "reported"
SELF_REPORTED = "self_reported"
ESTIMATED = "estimated"

#: Routes that may satisfy a check alone. A carrier-supplied certificate
#: is a claim; a cloned identity forwards a real document.
INDEPENDENT_CLASSES: FrozenSet[str] = frozenset({REPORTED})

AUTHORITY_STATUS = "authority_status"
SAFETY_RATING = "safety_rating"
INSURANCE_COVERAGE = "insurance_coverage"
OOS_ORDER = "oos_order"
INSPECTION_RESULT = "inspection_result"
SMS_PERCENTILE = "sms_percentile"
AUTHORITY_GRANTED_AT = "authority_granted_at"

OBSERVATION_KINDS: FrozenSet[str] = frozenset({
    AUTHORITY_STATUS, SAFETY_RATING, INSURANCE_COVERAGE, OOS_ORDER,
    INSPECTION_RESULT, SMS_PERCENTILE, AUTHORITY_GRANTED_AT,
})

#: HISTORY IS A PROPERTY OF (RUNG, OBSERVATION KIND), NOT OF THE RUNG.
#:
#: The first version of this file declared history as a property of the
#: rung alone and put only the bulk rung in the set. Recon measured that
#: wrong in both directions:
#:
#:   * The SMS website -- rung 3, "current snapshot only" in the brief --
#:     serves 189 MONTHLY SNAPSHOTS from Nov 2010 to Jul 2026. It carries
#:     genuine history for percentile scores.
#:   * It carries NO grant date. No probed FMCSA surface outside the bulk
#:     datasets answers "when was authority granted".
#:
#: So a rung answers one time-based question and not another, and a
#: single boolean per rung would have granted SMS the authority-grant
#: question it cannot answer -- which is the reincarnation check, the one
#: a chameleon carrier passes when it goes unevaluated.
HISTORY_BY_RUNG: Mapping[int, FrozenSet[str]] = {
    RUNG_BULK_HISTORY: frozenset({
        AUTHORITY_GRANTED_AT, AUTHORITY_STATUS, INSURANCE_COVERAGE, OOS_ORDER,
    }),
    RUNG_OFFICIAL_SNAPSHOT: frozenset({SMS_PERCENTILE}),
}


def rung_answers_history_for(rung: int, kind: str) -> bool:
    return kind in HISTORY_BY_RUNG.get(rung, frozenset())


#: WHEN A RUNG'S DATA STOPS. Recon measured that the legacy FMCSA
#: Licensing & Insurance datasets -- the ones that make rung 2 the primary
#: -- carry the note "last refreshed on 05/14/2026 and will no longer be
#: updated", and the cliff was verified in the rows rather than trusted
#: from the description. The successor is not a drop-in: 139,580 rows
#: against 4,941,925, and a carrier with a full legacy timeline is absent
#: from it.
#:
#: A frozen dataset does not stop being useful -- it stops being CURRENT,
#: and those are different. It still answers "was this carrier authorised
#: in 2024" perfectly. It cannot answer anything after the freeze, and a
#: predicate that reads it as though it could is answering about a world
#: that ended in May.
FROZEN_AT: Mapping[int, str] = {
    RUNG_BULK_HISTORY: "2026-05-14",
}

#: AND NOTHING SUCCEEDS IT. This is the correction the verification pass
#: produced, and it is the one that matters most.
#:
#: Every probe in the recon round independently noticed the successor
#: dataset was thin and then wrote a design in which it closes the seam
#: anyway -- an inference doing load-bearing work while its own supporting
#: measurements pointed the other way. The critic tested it: for the
#: twelve most recent out-of-service orders, the successor authority table
#: held ZERO rows for 12 of 12 and the successor insurance table ZERO for
#: 12 of 12, while the legacy table held rows for 11 of 12. The successor
#: covers 110,752 distinct carriers against the legacy 1,654,227 -- 6.7% --
#: because it is the NEW-REGISTRATION pipeline, not the existing base.
#:
#: THE FAILURE MODE IS A FALSE PASS AND IT REPRODUCES. One measured
#: carrier's legacy record ends `REINSTATED` with no disposition; a design
#: that unions legacy with the successor reads "reinstated, in force" for
#: a carrier that has been out of service for three days.
#:
#: So the honest entry is not "use the successor". It is that there is NO
#: MEASURED PUBLIC CHANNEL carrying authority or insurance history for the
#: existing carrier base after this date.
NO_SUCCESSOR_ESTABLISHED_AFTER: Mapping[int, str] = {
    RUNG_BULK_HISTORY: "2026-05-14",
}

#: Rungs that cannot cover a carrier without a US docket AT ALL. Not
#: "unwired" -- absent by construction. For a Canadian domestic carrier
#: the ladder's primary rung is empty, which a linear ladder cannot say.
US_DOCKET_ONLY: FrozenSet[int] = frozenset({RUNG_BULK_HISTORY, RUNG_OFFICIAL_API,
                                            RUNG_OFFICIAL_SNAPSHOT})

SERVED_FROM_A_FROZEN_DATASET = "SERVED_FROM_A_FROZEN_DATASET"
NO_CHANNEL_ESTABLISHED_FOR_THIS_WINDOW = "NO_CHANNEL_ESTABLISHED_FOR_THIS_WINDOW"
RUNG_IS_EMPTY_FOR_THIS_JURISDICTION = "RUNG_IS_EMPTY_FOR_THIS_JURISDICTION"


def channel_for(rung: int, kind: str, asof: str) -> Optional[str]:
    """Can this rung answer this kind of question, as at this date?

    Returns a refusal code, or None when it can. This replaces the linear
    ladder for time-based questions: the evidence supports a routing table
    keyed on (predicate, jurisdiction, time window), not an ordering.
    """
    if not rung_answers_history_for(rung, kind):
        return HISTORY_NOT_AVAILABLE_AT_THIS_RUNG
    horizon = NO_SUCCESSOR_ESTABLISHED_AFTER.get(rung)
    if horizon is not None and asof > horizon:
        return NO_CHANNEL_ESTABLISHED_FOR_THIS_WINDOW
    return None

CLEARED = "cleared"
BLOCKED = "blocked"
UNDETERMINED = "undetermined"

# Refusal / reason codes. Each names an OBSERVABLE.
NO_OBSERVATION_OF_THIS_KIND = "NO_OBSERVATION_OF_THIS_KIND"
OBSERVATION_OLDER_THAN_ITS_REFRESH_INTERVAL = "OBSERVATION_OLDER_THAN_ITS_REFRESH_INTERVAL"
COVERAGE_BELOW_THE_REQUIREMENT = "COVERAGE_BELOW_THE_REQUIREMENT"
COVERAGE_LAPSES_INSIDE_THE_MOVEMENT = "COVERAGE_LAPSES_INSIDE_THE_MOVEMENT"
COVERAGE_LAPSED_BEFORE_BOOKING = "COVERAGE_LAPSED_BEFORE_BOOKING"
CONFIRMED_ONLY_BY_THE_CARRIER = "CONFIRMED_ONLY_BY_THE_CARRIER"
AUTHORITY_NOT_ACTIVE = "AUTHORITY_NOT_ACTIVE"
OPEN_OUT_OF_SERVICE_ORDER = "OPEN_OUT_OF_SERVICE_ORDER"
AUTHORITY_GRANTED_TOO_RECENTLY = "AUTHORITY_GRANTED_TOO_RECENTLY"
HISTORY_NOT_AVAILABLE_AT_THIS_RUNG = "HISTORY_NOT_AVAILABLE_AT_THIS_RUNG"
NO_USDOT_RECORD_AND_NO_PROVINCIAL_SOURCE = "NO_USDOT_RECORD_AND_NO_PROVINCIAL_SOURCE"
CARRIER_DOCUMENT_DISAGREES_WITH_THE_INSURER = "CARRIER_DOCUMENT_DISAGREES_WITH_THE_INSURER"

#: Class 7 on the vetting run itself.
NO_VERDICT_BECAUSE_NO_PREDICATE_WAS_EVALUATED = "NO_VERDICT_BECAUSE_NO_PREDICATE_WAS_EVALUATED"


@dataclass(frozen=True)
class Carrier:
    """An entity. Note there is no `insured`, `authorised` or `safe` field:
    those are observations with dates, not properties of a company."""

    carrier_id: str
    legal_name: str
    dot_number: Optional[str] = None
    mc_number: Optional[str] = None
    cvor_number: Optional[str] = None
    neq_number: Optional[str] = None

    @property
    def has_us_authority_identifier(self) -> bool:
        return bool(self.dot_number or self.mc_number)

    @property
    def has_provincial_identifier(self) -> bool:
        return bool(self.cvor_number or self.neq_number)


@dataclass(frozen=True)
class VettingProvenance:
    source_id: str
    source_class: str
    rung: int
    retrieved_at: str
    artifact_id: Optional[str] = None

    @property
    def independent(self) -> bool:
        return self.source_class in INDEPENDENT_CLASSES

    def answers_history_for(self, kind: str) -> bool:
        """History is per (rung, kind). See HISTORY_BY_RUNG."""
        return rung_answers_history_for(self.rung, kind)


@dataclass(frozen=True)
class VettingObservation:
    """A vetting fact, with when it describes and when we learned it."""

    subject: str
    kind: str
    value: object
    unit: Optional[str]
    #: What the observation DESCRIBES.
    period_start: str
    period_end: Optional[str]
    #: When it became knowable to us. Distinct from period_start, and the
    #: distinction is the entire point of the record.
    known_at: str
    provenance: VettingProvenance
    supersedes: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in OBSERVATION_KINDS:
            raise ValueError(f"{self.kind!r} is not a vetting observation kind; "
                             f"known: {sorted(OBSERVATION_KINDS)}")

    def age_days(self, asof: str) -> int:
        """Whole days between known_at and asof, on ISO dates."""
        return _days_between(self.known_at, asof)


def _days_between(earlier: str, later: str) -> int:
    """Days between two ISO dates, without importing a clock.

    Deliberately arithmetic on the date text rather than `date.today()`:
    nothing in this module may ask what time it is now. The `asof` is
    always passed in, so a vetting decision can be replayed exactly as it
    stood on the day it was taken.
    """
    from datetime import date
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


@dataclass(frozen=True)
class PredicateResult:
    name: str
    status: str
    code: Optional[str] = None
    detail: str = ""
    remedy: Optional[str] = None
    evidence: Tuple[str, ...] = ()
    #: The rung that served the observations behind this result.
    served_by_rung: Optional[int] = None
    #: Age in days of the oldest observation used.
    evidence_age_days: Optional[int] = None


def _latest(observations: Sequence[VettingObservation], kind: str,
            asof: str) -> Optional[VettingObservation]:
    """The most recently KNOWN observation of a kind that was knowable by
    `asof`. Filtering on known_at rather than on period is what makes a
    replay honest -- a record that arrived on Friday must not inform a
    decision taken on Tuesday."""
    candidates = [o for o in observations if o.kind == kind and o.known_at <= asof]
    if not candidates:
        return None
    return max(candidates, key=lambda o: o.known_at)


def insurance_current(observations: Sequence[VettingObservation], *, required: float,
                      currency: str, booking_date: str, pickup_date: str,
                      delivery_date: str, asof: str,
                      refresh_interval_days: int = 30) -> PredicateResult:
    """validWhile: coverage covers the WHOLE movement, meets the
    requirement, is confirmed by the insurer, and is fresher than the
    refresh interval."""
    latest = _latest(observations, INSURANCE_COVERAGE, asof)
    if latest is None:
        return PredicateResult(
            "insurance_current", UNDETERMINED, NO_OBSERVATION_OF_THIS_KIND,
            "no insurance observation has been recorded for this carrier as at "
            f"{asof}. Nothing is known about coverage; this is not a finding that there is none.",
            "obtain a certificate and confirm the policy number with the named insurer.")

    age = latest.age_days(asof)
    if age > refresh_interval_days:
        return PredicateResult(
            "insurance_current", UNDETERMINED, OBSERVATION_OLDER_THAN_ITS_REFRESH_INTERVAL,
            f"the most recent insurance observation is {age} days old against a "
            f"{refresh_interval_days}-day interval. A stale record does not mean the carrier is "
            "uninsured; it means we do not currently know, which is a third state and not a "
            "failure.",
            "re-confirm coverage with the insurer before tendering.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    if not latest.provenance.independent:
        return PredicateResult(
            "insurance_current", UNDETERMINED, CONFIRMED_ONLY_BY_THE_CARRIER,
            f"coverage is attested {latest.provenance.source_class!r}. A carrier's word about its "
            "own insurance is evidence of what the carrier says, and a cloned identity forwards a "
            "real document.",
            "confirm the policy number directly with the named insurer, not with the carrier.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    coverage = float(latest.value)  # type: ignore[arg-type]
    if latest.unit != currency:
        return PredicateResult(
            "insurance_current", UNDETERMINED, "COVERAGE_IN_ANOTHER_CURRENCY",
            f"coverage is {coverage} {latest.unit} against a requirement in {currency}; comparing "
            "them needs a rate and a date, and this predicate was given neither.",
            f"restate the requirement in {latest.unit}, or convert at a stated rate and date.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    if coverage < required:
        return PredicateResult(
            "insurance_current", BLOCKED, COVERAGE_BELOW_THE_REQUIREMENT,
            f"{coverage} {latest.unit} against a requirement of {required}.",
            "raise the coverage, or reduce the cargo value on this movement.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    expiry = latest.period_end
    if expiry is None:
        return PredicateResult(
            "insurance_current", UNDETERMINED, NO_OBSERVATION_OF_THIS_KIND,
            "the coverage observation states no expiry, so whether it survives the movement "
            "cannot be evaluated. An open-ended certificate is not the same as a current one.",
            "obtain the policy expiry date from the insurer.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    if expiry < booking_date:
        return PredicateResult(
            "insurance_current", BLOCKED, COVERAGE_LAPSED_BEFORE_BOOKING,
            f"coverage expired {expiry}, before this load was booked on {booking_date}. The "
            "carrier was already uninsured when it was tendered.",
            "do not tender. Obtain current coverage before any further load.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    if expiry < delivery_date:
        side = "after pickup" if expiry >= pickup_date else "before pickup"
        return PredicateResult(
            "insurance_current", BLOCKED, COVERAGE_LAPSES_INSIDE_THE_MOVEMENT,
            f"coverage expires {expiry}, which is inside the movement "
            f"({booking_date} booked, {pickup_date} pickup, {delivery_date} delivery) and "
            f"{side}. It was valid when the load was tendered and is not valid when the truck "
            "arrives; only a record separating known_at from the period can tell those apart.",
            "obtain a renewed certificate covering the delivery date before the truck moves.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    return PredicateResult(
        "insurance_current", CLEARED, detail=f"{coverage} {latest.unit} to {expiry}, "
        f"{latest.provenance.source_class} via rung {latest.provenance.rung}",
        evidence=(latest.provenance.source_id,),
        served_by_rung=latest.provenance.rung, evidence_age_days=age)


def authority_active(observations: Sequence[VettingObservation], *, asof: str,
                     refresh_interval_days: int = 7) -> PredicateResult:
    """validWhile: regulator status active, no open OOS order, and the
    record is fresher than the interval."""
    latest = _latest(observations, AUTHORITY_STATUS, asof)
    if latest is None:
        return PredicateResult(
            "authority_active", UNDETERMINED, NO_OBSERVATION_OF_THIS_KIND,
            f"no authority observation has been recorded as at {asof}. This is a fact about the "
            "check and not about the carrier: it is not evidence that authority is absent, and "
            "it is not evidence that it is present.",
            "query the regulator, or record a dated printout obtained from it.")

    age = latest.age_days(asof)
    if age > refresh_interval_days:
        return PredicateResult(
            "authority_active", UNDETERMINED, OBSERVATION_OLDER_THAN_ITS_REFRESH_INTERVAL,
            f"the authority record is {age} days old against a {refresh_interval_days}-day "
            "interval. Authority can be revoked between checks, so a stale pass is not a pass.",
            "re-query the regulator before tendering.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    if not latest.provenance.independent:
        return PredicateResult(
            "authority_active", UNDETERMINED, CONFIRMED_ONLY_BY_THE_CARRIER,
            f"authority is attested {latest.provenance.source_class!r} rather than by the "
            "regulator.",
            "obtain the status from the regulator's own record.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    oos = _latest(observations, OOS_ORDER, asof)
    if oos is not None and bool(oos.value) and oos.period_end is None:
        return PredicateResult(
            "authority_active", BLOCKED, OPEN_OUT_OF_SERVICE_ORDER,
            f"an out-of-service order recorded {oos.period_start} has no lift date. Whether it "
            "was later lifted is a HISTORY question, and this record does not answer it.",
            "confirm with the regulator whether the order was lifted; a lifted order should be "
            "recorded with its period_end rather than deleted.",
            evidence=(oos.provenance.source_id,),
            served_by_rung=oos.provenance.rung)

    if latest.value is not True:
        return PredicateResult(
            "authority_active", BLOCKED, AUTHORITY_NOT_ACTIVE,
            f"the regulator reports authority {latest.value!r} as at {latest.period_start}.",
            "do not tender. Reinstatement is the carrier's to obtain and to evidence.",
            evidence=(latest.provenance.source_id,),
            served_by_rung=latest.provenance.rung, evidence_age_days=age)

    return PredicateResult(
        "authority_active", CLEARED,
        detail=f"active per {latest.provenance.source_id} at {latest.known_at}",
        evidence=(latest.provenance.source_id,),
        served_by_rung=latest.provenance.rung, evidence_age_days=age)


def no_recent_reincarnation(observations: Sequence[VettingObservation], *, asof: str,
                            minimum_age_days: int = 180,
                            exception_reason: Optional[str] = None) -> PredicateResult:
    """validWhile: authority granted longer ago than N days, OR an explicit
    exception is recorded with a reason.

    THIS IS THE PREDICATE THAT NEEDS HISTORY. A current snapshot says the
    carrier is authorised; only a historical record says WHEN it became
    authorised, which is what distinguishes an established carrier from a
    chameleon that re-registered last month under a new name. If the
    serving rung cannot carry history, the predicate returns undetermined
    rather than quietly passing.
    """
    if exception_reason:
        return PredicateResult(
            "no_recent_reincarnation", CLEARED,
            detail=f"exception recorded: {exception_reason}")

    granted = _latest(observations, AUTHORITY_GRANTED_AT, asof)
    if granted is None:
        return PredicateResult(
            "no_recent_reincarnation", UNDETERMINED, HISTORY_NOT_AVAILABLE_AT_THIS_RUNG,
            "no grant date has been recorded. A current-snapshot source reports that authority "
            "exists and never reports when it began, so this predicate cannot be evaluated from "
            "one -- and an unevaluated reincarnation check is exactly how a chameleon carrier "
            "passes vetting.",
            "serve this predicate from a rung carrying history (the bulk/historical datasets), "
            "or record an explicit exception with a reason.")

    if not rung_answers_history_for(granted.provenance.rung, AUTHORITY_GRANTED_AT):
        return PredicateResult(
            "no_recent_reincarnation", UNDETERMINED, HISTORY_NOT_AVAILABLE_AT_THIS_RUNG,
            f"a grant date was supplied from rung {granted.provenance.rung} "
            f"({RUNG_NAMES.get(granted.provenance.rung, 'unknown')}), which does not answer "
            f"{AUTHORITY_GRANTED_AT}. Measured: the SMS website carries 189 monthly snapshots and "
            "still has no grant-date column, so carrying history in general is not carrying THIS "
            "history. A grant date from such a source is the date the record was taken wearing "
            "the date the authority began.",
            "serve this predicate from the bulk/historical datasets.",
            evidence=(granted.provenance.source_id,),
            served_by_rung=granted.provenance.rung)


    age = _days_between(str(granted.value), asof)
    if age < minimum_age_days:
        return PredicateResult(
            "no_recent_reincarnation", BLOCKED, AUTHORITY_GRANTED_TOO_RECENTLY,
            f"authority was granted {granted.value} — {age} days ago, against a "
            f"{minimum_age_days}-day floor. Recent registration is not itself wrongdoing; it is "
            "the signal that has to be explained before a first load rather than after one.",
            "record an explicit exception with a reason, or wait. Cross-check the equipment count "
            "against the claimed fleet.",
            evidence=(granted.provenance.source_id,),
            served_by_rung=granted.provenance.rung)

    # THE FREEZE, checked AFTER recency and deliberately so. A grant date
    # that IS recent is a positive finding and blocks whatever the source's
    # currency: the observation is there. What a frozen source cannot
    # support is the NEGATIVE -- "this carrier was granted long ago and
    # nothing has changed since" -- because a revocation and re-grant after
    # the freeze is invisible in it, and invisible is exactly how a
    # reincarnated carrier appears.
    frozen = FROZEN_AT.get(granted.provenance.rung)
    if frozen is not None and asof > frozen:
        return PredicateResult(
            "no_recent_reincarnation", UNDETERMINED, NO_CHANNEL_ESTABLISHED_FOR_THIS_WINDOW,
            f"the grant date came from rung {granted.provenance.rung}, whose datasets were last "
            f"refreshed {frozen} and will not be updated. Asked as at {asof}, this reads a world "
            "that stopped in May. A carrier that registered after the freeze is ABSENT from it, "
            "and absent is exactly how a newly-reincarnated carrier appears -- so the frozen "
            "source fails silently in the direction that matters. AND NOTHING SUCCEEDS IT: the "
            "successor holds zero rows for 12 of the 12 most recently out-of-service carriers "
            "and covers 6.7 percent of the base, because it is the new-registration pipeline "
            "rather than the existing one.",
            "there is NO established public channel for this question after the horizon. Do not "
            "union the successor in: measured, that union reads `reinstated, in force` for a "
            "carrier that has been out of service for three days. Either obtain a dated "
            "regulator printout and record an explicit exception, or treat this carrier as "
            "unvetted for reincarnation.",
            evidence=(granted.provenance.source_id,),
            served_by_rung=granted.provenance.rung)

    return PredicateResult("no_recent_reincarnation", CLEARED,
                           detail=f"authority granted {granted.value}, {age} days ago",
                           evidence=(granted.provenance.source_id,),
                           served_by_rung=granted.provenance.rung)


def coverage_divergence(observations: Sequence[VettingObservation],
                        asof: str) -> Optional[PredicateResult]:
    """A carrier-supplied certificate against an insurer confirmation:
    two claims about one coverage.

    Returned as a DIVERGENCE, never as an overwrite. A carrier whose
    documents persistently disagree with the insurer is a finding with a
    name, and overwriting one with the other destroys the only signal.
    """
    supplied = [o for o in observations
                if o.kind == INSURANCE_COVERAGE and o.known_at <= asof
                and o.provenance.source_class == SELF_REPORTED]
    confirmed = [o for o in observations
                 if o.kind == INSURANCE_COVERAGE and o.known_at <= asof
                 and o.provenance.source_class == REPORTED]
    if not supplied or not confirmed:
        return None
    a, b = max(supplied, key=lambda o: o.known_at), max(confirmed, key=lambda o: o.known_at)
    if a.value == b.value and a.period_end == b.period_end:
        return None
    return PredicateResult(
        "coverage_divergence", BLOCKED, CARRIER_DOCUMENT_DISAGREES_WITH_THE_INSURER,
        f"the carrier's document states {a.value} {a.unit} to {a.period_end}; the insurer "
        f"confirms {b.value} {b.unit} to {b.period_end}. Two claims about one coverage, kept as "
        "a divergence rather than resolved by overwriting one with the other.",
        "resolve with the insurer before tendering, and record the divergence either way — a "
        "carrier whose documents persistently disagree is the finding.",
        evidence=(a.provenance.source_id, b.provenance.source_id))


def jurisdiction_coverage(carrier: Carrier, *, domestic_only: bool,
                          provincial_source_available: bool = False) -> PredicateResult:
    """PC-6 Part F, scoped precisely.

    Cross-border carriers hold USDOT authority, so the federal US record
    applies to them wherever they are domiciled. The blind spot is
    DOMESTIC-CANADA moves, and until the provincial recon lands a
    domestic-only carrier with no USDOT record is undetermined rather than
    cleared -- which is the correct output and what makes the gap visible
    instead of silent.
    """
    if carrier.has_us_authority_identifier:
        return PredicateResult(
            "jurisdiction_coverage", CLEARED,
            detail="the carrier holds a USDOT/MC identifier, so the federal US record applies "
                   "regardless of domicile.")
    if domestic_only and not provincial_source_available:
        # Stated before the general branch because the reason differs: the
        # bulk rungs are not merely unwired here, they are EMPTY BY
        # CONSTRUCTION. L&I covers carriers with a US docket; a Canadian
        # domestic carrier without one is absent by definition, so the
        # ladder's own primary rung has nothing in it for the client's
        # core population. A linear ladder cannot express that.
        return PredicateResult(
            "jurisdiction_coverage", UNDETERMINED, RUNG_IS_EMPTY_FOR_THIS_JURISDICTION,
            "this is a domestic-Canada movement by a carrier with no US docket. The bulk and "
            "snapshot rungs are not unwired for it -- they are EMPTY BY CONSTRUCTION, because "
            "they index carriers by US docket and this carrier has none. Measured: NO FEDERAL "
            "CANADIAN CARRIER REGISTRY EXISTS -- the Transport Canada catalogue holds 49 datasets "
            "and none is one, and the NSC number is province-issued with no central copy. So the "
            "gap is one adapter per province, and two of thirteen are reconned.",
            "Ontario: a free public CVOR abstract exists and is NOT consent-gated -- four "
            "unauthenticated services answer, under Crown copyright rather than an open licence. "
            "Quebec: the public lists are a NEGATIVE screen and a censored denominator, but the "
            "decisions search is open, keyed on NIR, and takes a date range. NOTE BEFORE "
            "BUILDING EITHER: redistribution and caching rights are unresolved for both, and "
            "Quebec's terms prohibit storing without prior authorisation -- so a local mirror is "
            "a decision for a person, not a build step.")
    if not domestic_only:
        return PredicateResult(
            "jurisdiction_coverage", UNDETERMINED, NO_USDOT_RECORD_AND_NO_PROVINCIAL_SOURCE,
            "the movement crosses the border and the carrier has no USDOT or MC identifier on "
            "file. Any carrier hauling into the US holds one, so its absence means the record is "
            "incomplete rather than that the carrier is exempt.",
            "obtain the carrier's USDOT number and re-run the authority check.")
    if provincial_source_available and carrier.has_provincial_identifier:
        return PredicateResult(
            "jurisdiction_coverage", CLEARED,
            detail="domestic movement served by a provincial source.")
    return PredicateResult(
        "jurisdiction_coverage", UNDETERMINED, NO_USDOT_RECORD_AND_NO_PROVINCIAL_SOURCE,
        "this is a domestic-Canada movement by a carrier with no USDOT record, and no provincial "
        "source is wired up. Measured: NO FEDERAL CANADIAN CARRIER REGISTRY EXISTS -- the "
        "Transport Canada open-data catalogue holds 49 datasets and none is a carrier registry, "
        "and the NSC number is province-issued with no central copy. So this gap is not one "
        "adapter, it is one per province, and two of thirteen have been reconned.",
        "Ontario: a free public CVOR abstract exists and is NOT consent-gated (the recon's "
        "hypothesis was wrong) -- four unauthenticated services answer, under Crown copyright "
        "rather than an open licence, with a stated 21-searches-a-day cap. Quebec: the public "
        "lists are a NEGATIVE screen only and a censored denominator -- only carriers whose "
        "rating was modified appear -- but the decisions search is open, keyed on NIR, and takes "
        "a date range, so it is the historical channel. Wire whichever province this movement is "
        "in; until then undetermined, not cleared.")


@dataclass(frozen=True)
class Verdict:
    """cleared / blocked / undetermined, with the evidence behind it."""

    carrier: str
    status: str
    predicates: Tuple[PredicateResult, ...]
    asof: str
    missing: Tuple[str, ...] = ()
    remedy: Optional[str] = None
    valid_until: Optional[str] = None
    empty_because: Optional[str] = None

    @property
    def blocking(self) -> Tuple[PredicateResult, ...]:
        return tuple(p for p in self.predicates if p.status == BLOCKED)

    @property
    def undetermined(self) -> Tuple[PredicateResult, ...]:
        return tuple(p for p in self.predicates if p.status == UNDETERMINED)

    @property
    def served_from_snapshot(self) -> bool:
        return any(p.served_by_rung == RUNG_COMMITTED_SNAPSHOT for p in self.predicates)

    @property
    def oldest_evidence_days(self) -> Optional[int]:
        ages = [p.evidence_age_days for p in self.predicates if p.evidence_age_days is not None]
        return max(ages) if ages else None


def decide(carrier: Carrier, predicates: Sequence[PredicateResult], *,
           asof: str, valid_until: Optional[str] = None) -> Verdict:
    """The deterministic gate. Blocked outranks undetermined outranks cleared.

    A real failure is not made ambiguous by a second check that could not
    run, which is why the ordering is fixed here rather than left to a
    caller's `all()`.
    """
    predicates = tuple(p for p in predicates if p is not None)
    if not predicates:
        return Verdict(
            carrier.carrier_id, UNDETERMINED, (), asof,
            missing=("every predicate",),
            remedy="run the vetting predicates. A carrier with no evaluated predicate is not a "
                   "clean carrier.",
            empty_because=(f"{NO_VERDICT_BECAUSE_NO_PREDICATE_WAS_EVALUATED}: nothing was "
                           "checked, so nothing is known. An empty predicate list reads as a "
                           "clean sheet and is the opposite of one."))
    blocked = [p for p in predicates if p.status == BLOCKED]
    undetermined = [p for p in predicates if p.status == UNDETERMINED]
    if blocked:
        return Verdict(carrier.carrier_id, BLOCKED, predicates, asof,
                       remedy="; ".join(p.remedy for p in blocked if p.remedy))
    if undetermined:
        return Verdict(carrier.carrier_id, UNDETERMINED, predicates, asof,
                       missing=tuple(p.name for p in undetermined),
                       remedy="; ".join(p.remedy for p in undetermined if p.remedy))
    return Verdict(carrier.carrier_id, CLEARED, predicates, asof, valid_until=valid_until)


def render(verdict: Verdict) -> str:
    lines = [f"CARRIER {verdict.carrier} — {verdict.status.upper()} as at {verdict.asof}"]
    if verdict.empty_because:
        lines.append(f"  (nothing evaluated) {verdict.empty_because}")
    for predicate in verdict.predicates:
        rung = (f" [rung {predicate.served_by_rung} "
                f"{RUNG_NAMES.get(predicate.served_by_rung or -1, '?')}]"
                if predicate.served_by_rung is not None else "")
        lines.append(f"  {predicate.name:<26} {predicate.status.upper()}"
                     + (f" ({predicate.code})" if predicate.code else "") + rung)
        if predicate.detail:
            lines.append(f"  {'':<26} {predicate.detail}")
        if predicate.remedy:
            lines.append(f"  {'':<26} remedy: {predicate.remedy}")
    if verdict.oldest_evidence_days is not None:
        lines.append(f"  oldest evidence: {verdict.oldest_evidence_days} days")
    if verdict.status == UNDETERMINED:
        lines.append("  ! UNDETERMINED is not a pass and not a failure. Missing: "
                     f"{list(verdict.missing)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------
# The tender barrier. THE acceptance criterion: no tender may be issued
# against a carrier that is not cleared, asserted structurally.
# ---------------------------------------------------------------------

TENDER_AGAINST_A_CARRIER_THAT_IS_NOT_CLEARED = "TENDER_AGAINST_A_CARRIER_THAT_IS_NOT_CLEARED"
TENDER_AGAINST_A_STALE_VERDICT = "TENDER_AGAINST_A_STALE_VERDICT"


class TenderRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def authorise_tender(verdict: Verdict, *, at: str) -> Verdict:
    """The only gate a tender may pass through.

    It returns the verdict rather than a boolean so a caller cannot write
    `if authorise_tender(...)` and have a falsy-but-present value read as
    a refusal, or wrap it in a try/except that swallows the reason.
    """
    if verdict.status != CLEARED:
        raise TenderRefusal(
            TENDER_AGAINST_A_CARRIER_THAT_IS_NOT_CLEARED,
            f"{verdict.carrier} is {verdict.status} as at {verdict.asof}. "
            + (f"Missing: {list(verdict.missing)}. " if verdict.missing else "")
            + (f"Remedy: {verdict.remedy}" if verdict.remedy else ""),
        )
    if verdict.valid_until is not None and at > verdict.valid_until:
        raise TenderRefusal(
            TENDER_AGAINST_A_STALE_VERDICT,
            f"{verdict.carrier} was cleared until {verdict.valid_until} and this tender is dated "
            f"{at}. A verdict that has aged out is not a verdict; re-run the predicates.",
        )
    return verdict
