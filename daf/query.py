"""Read-only questions an outside caller can ask of an evidence pool.

WHY THIS EXISTS. architecture/daq_agent_instruments.yaml declares what an
agent MAY do and daf/agents/candidate_filing.py validates what it emits.
Between the two there was nothing an agent could ASK. A contract over a
surface that does not exist is a permission with no verb.

WHAT IT RETURNS IS A VALUE WITH ITS WARRANT, NEVER A BARE VALUE. The
chain -- observation to Record to Document to Source -- resolves for
every observation the pipeline produces, measured before this module was
written. So a caller never has to accept a number on trust: the source
name, the retrieval method, when it was retrieved, the extraction method
and the acquirer's own declarations come back attached to it.

THE IDENTIFIER PROBLEM, SURFACED RATHER THAN PAPERED OVER. `Observation.id`
is not stable across acquisitions of the same file: `make_record` hashes
the locator, and the locator carries the path the caller happened to
pass, so the same fixture acquired by a relative and an absolute path
yields two different observation ids for the same measurement. Measured,
and recorded in architecture/query_surface_preregistration.yaml. It is
not repaired here -- `make_record` is in the vendored core and the fix
would move every id in every pool.

The consequence for a caller is real: an observation id cannot be used to
ask "do you already hold this". So `Warrant` returns BOTH ids, labelled
for what each is worth -- `observation_id`, which is invocation-dependent,
and `document_id`, which is not -- plus the run identity parsed out of the
locator. A caller that de-duplicates on the wrong one is then making a
visible mistake rather than an invisible one.

COST IS PART OF THE ANSWER. The pool has no index by content: `property`
and `sample_id` are not keys, only `referent` is. So every content query
walks the whole pool, and `Holdings.examined` reports how many
observations were looked at, not only how many matched. A method named
like an index lookup over a linear scan is a lie about cost.

WHICH KIND OF NOTHING. Three empty results are reachable and they are not
the same fact: an empty pool, a pool with nothing matching, and a filter
naming a content key no observation carries -- which is a caller error.
Returning an empty tuple for all three reports a question as an answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

#: Content keys that describe the ACQUISITION rather than the
#: measurement. Surfaced separately because the distinction is the one an
#: external caller most needs and most rarely gets: what the document
#: said, versus what the acquirer supplied on its behalf.
ACQUISITION_KEYS = ("acquisition_declared", "not_acquired_because_not_measured",
                    "data_provenance")

POOL_IS_EMPTY = "POOL_IS_EMPTY"
NOTHING_MATCHED = "NOTHING_MATCHED"
NO_OBSERVATION_CARRIES_THIS_KEY = "NO_OBSERVATION_CARRIES_THIS_KEY"
OBSERVATION_NOT_HELD = "OBSERVATION_NOT_HELD"
WARRANT_CHAIN_BROKEN_AT = "WARRANT_CHAIN_BROKEN_AT"


class QueryRefusal(ValueError):
    """The question cannot be answered honestly as asked."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Provenance:
    """One hop's worth of where a value came from."""

    source_name: str
    retrieval_method: str
    retrieved_at: str
    record_locator: str
    document_id: str
    record_id: str


@dataclass(frozen=True)
class Warrant:
    """A value and everything that justifies it.

    `observation_id` and `document_id` are BOTH returned and they are not
    interchangeable. The first identifies this observation in this pool
    and changes if the same file is acquired through a differently
    spelled path. The second is a hash of source, content and method and
    does not. `run_identity` is the part of the locator that names the
    run rather than the machine.
    """

    observation_id: str
    document_id: str
    run_identity: Optional[str]
    #: NAMED `measured_property` AND NOT `property`. The content key is
    #: `property`, and a dataclass field of that name shadows the builtin
    #: for the rest of the class body -- so the two @property methods
    #: below resolve to a str annotation rather than to the decorator.
    #: Runtime survives it, because a bare annotation binds no name, and
    #: only the type checker sees it. It would stop surviving the moment
    #: anyone gave the field a default. The raw key is still in `content`.
    measured_property: Optional[str]
    value: Optional[float]
    unit: Optional[str]
    uncertainty: Optional[float]
    uncertainty_kind: Optional[str]
    value_absence: Optional[str]
    declared_by_the_acquirer: Tuple[str, ...]
    declined_as_not_measured: Tuple[str, ...]
    data_provenance: Optional[str]
    provenance: Tuple[Provenance, ...]
    content: Mapping[str, Any]

    @property
    def is_absent(self) -> bool:
        """A structural absence, not a missing value. The two are
        different claims and only one of them is data."""
        return self.value_absence is not None

    @property
    def identifier_is_invocation_dependent(self) -> bool:
        """True whenever the locator carries more than the run identity.

        Stated as a property rather than a docstring so a caller reading
        the object sees it. See the module docstring.
        """
        return bool(self.provenance) and any(
            "#" in p.record_locator and p.record_locator.split("#", 1)[0]
            for p in self.provenance)


@dataclass(frozen=True)
class Holdings:
    """What a scan found, and what it cost to find it."""

    matched: Tuple[Warrant, ...]
    examined: int
    refusal: Optional[str]
    detail: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self.matched


def _split_locator(locator: str) -> Optional[str]:
    """The run identity, or None when the locator carries no `#`.

    Everything before the `#` is where the document was on some machine;
    everything after is which run inside it. Only the second half is a
    fact about the measurement.
    """
    if "#" not in locator:
        return None
    return locator.split("#", 1)[1] or None


def _tuple_from_csv(content: Mapping[str, Any], key: str) -> Tuple[str, ...]:
    raw = content.get(key)
    if not isinstance(raw, str) or not raw:
        return ()
    return tuple(part for part in raw.split(",") if part)


def warrant_for(pool: Any, observation_id: str) -> Warrant:
    """The value at `observation_id`, with everything that justifies it.

    Raises rather than returning a partial warrant. A chain that does not
    resolve is a broken pool, and returning the value without the hop
    that failed would hand a caller exactly the unwarranted number this
    whole layer exists to refuse.
    """
    if not pool.has_observation(observation_id):
        raise QueryRefusal(OBSERVATION_NOT_HELD, f"no observation {observation_id!r}")

    observation = pool.get_observation(observation_id)
    content = observation.content

    chain = []
    document_ids = set()
    for record_id in observation.record_ids:
        if not pool.has_record(record_id):
            raise QueryRefusal(WARRANT_CHAIN_BROKEN_AT,
                               f"record {record_id!r} named by {observation_id!r} is not held")
        record = pool.get_record(record_id)
        if not pool.has_document(record.document_id):
            raise QueryRefusal(WARRANT_CHAIN_BROKEN_AT,
                               f"document {record.document_id!r} named by record "
                               f"{record_id!r} is not held")
        document = pool.get_document(record.document_id)
        if not pool.has_source(document.source_id):
            raise QueryRefusal(WARRANT_CHAIN_BROKEN_AT,
                               f"source {document.source_id!r} named by document "
                               f"{document.id!r} is not held")
        source = pool.get_source(document.source_id)
        document_ids.add(document.id)
        chain.append(Provenance(
            source_name=getattr(source, "name", document.source_id),
            retrieval_method=document.retrieval_method,
            retrieved_at=document.retrieved_at,
            record_locator=record.locator,
            document_id=document.id,
            record_id=record_id,
        ))

    value = content.get("value")
    return Warrant(
        observation_id=observation_id,
        # An observation spanning two documents has no single stable id
        # either, and saying so beats picking one.
        document_id=next(iter(document_ids)) if len(document_ids) == 1 else "",
        run_identity=_split_locator(chain[0].record_locator) if chain else None,
        measured_property=content.get("property"),
        value=float(value) if isinstance(value, (int, float))
        and not isinstance(value, bool) else None,
        unit=content.get("unit"),
        uncertainty=content.get("uncertainty"),
        uncertainty_kind=content.get("uncertainty_kind"),
        value_absence=content.get("value_absence"),
        declared_by_the_acquirer=_tuple_from_csv(content, "acquisition_declared"),
        declined_as_not_measured=_tuple_from_csv(content, "not_acquired_because_not_measured"),
        data_provenance=content.get("data_provenance"),
        provenance=tuple(chain),
        content=content,
    )


def holdings_matching(pool: Any, **filters: Any) -> Holdings:
    """Every observation whose content matches, with what the scan cost.

    A SCAN, and named to say so. There is no index by `property` or
    `sample_id`; the pool indexes by id and by referent only, so this
    walks `all_observations` and `examined` reports how many it looked at.

    An empty result names which kind of nothing it is.
    """
    observations = list(pool.all_observations())
    examined = len(observations)

    if not observations:
        return Holdings((), 0, POOL_IS_EMPTY,
                        "the pool holds no observations; this is not a statement about "
                        "whether anything matches")

    if filters:
        carried = {key for observation in observations for key in observation.content}
        unknown = sorted(set(filters) - carried)
        if unknown:
            # A caller error, and a different fact from "nothing matched".
            return Holdings((), examined, NO_OBSERVATION_CARRIES_THIS_KEY,
                            f"no observation in this pool carries {unknown!r}; the keys "
                            f"present are {sorted(carried)!r}")

    matched = []
    for observation in observations:
        if all(observation.content.get(key) == want for key, want in filters.items()):
            matched.append(warrant_for(pool, observation.id))

    if not matched:
        return Holdings((), examined, NOTHING_MATCHED,
                        f"{examined} observation(s) examined and none matched {filters!r}")
    return Holdings(tuple(matched), examined, None)


def census(pool: Any) -> Dict[str, Dict[str, int]]:
    """What the pool holds, counted along the axes a caller can act on.

    Deliberately NOT a summary statistic. Counts by property, by source
    and by data_provenance -- the last because a pool mixing measured and
    fabricated figures is a pool whose totals mean nothing, and a caller
    asking what is held is entitled to see the split before the sum.
    """
    by_property: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    by_provenance: Dict[str, int] = {}
    for observation in pool.all_observations():
        content = observation.content
        key = str(content.get("property", "<no property>"))
        by_property[key] = by_property.get(key, 0) + 1
        provenance = str(content.get("data_provenance", "<undeclared>"))
        by_provenance[provenance] = by_provenance.get(provenance, 0) + 1
        for record_id in observation.record_ids:
            if not pool.has_record(record_id):
                continue
            record = pool.get_record(record_id)
            if not pool.has_document(record.document_id):
                continue
            document = pool.get_document(record.document_id)
            source = (pool.get_source(document.source_id)
                      if pool.has_source(document.source_id) else None)
            name = str(getattr(source, "name", document.source_id))
            by_source[name] = by_source.get(name, 0) + 1
    return {"by_property": by_property, "by_source": by_source,
            "by_data_provenance": by_provenance}
