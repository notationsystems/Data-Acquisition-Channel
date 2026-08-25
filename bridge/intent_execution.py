"""`operationalize_intent(...) -> AcquisitionPlan` -- the one decision that
belongs to neither side.

WHAT THE AUDIT FOUND, before any of this was written:

  * `AcquisitionIntent` carries `subject_natural_key`, `subject_kind`,
    `property`, `role`, `target_context` -- and deliberately no
    `source_id` and no adapter parameters (Phase 20).
  * `SourceDefinition` carries `source_id`, `name`, `domain`,
    `adapter_id`, `configuration`, `capabilities`, `required_parameters`,
    `enabled` -- and NO metadata about which subjects or properties a
    source can supply.

Neither side knows what the other needs, and nothing in the repository
could bridge them. In particular **a source cannot be selected
automatically**: there is no data anywhere from which "which source
supplies `tensile_strength` for `formulation-f1`?" could be answered.
Inventing that metadata would be inventing autonomous source selection,
which this phase forbids. So the source is a CALLER DECISION, passed in.

WHAT THIS DELIBERATELY DOES NOT DUPLICATE. `daf.catalog.plan.validate_plan`
-- already called by `execute_plan` -- checks unknown source, disabled
source, unknown adapter, disabled plan, and missing required parameters.
Re-checking any of that here would duplicate DAF orchestration logic.
This module adds exactly the one check DAF cannot perform, because DAF
never sees an intent:

    is the intent's SCIENTIFIC CONDITIONING CONTEXT representable in this
    source's request parameters, or would it be silently dropped?

That question matters because a water level measured under datum MLLW
does not answer a question about STND, and a tensile strength measured
at 60 C does not answer a question about 25 C. An acquisition that
quietly ignored `target_context` would return evidence that looks
responsive and is not.

WHY `context_parameters` IS REQUIRED AND EXPLICIT. The tempting shortcut
is `parameters = dict(intent.target_context)`. It is wrong: an intent's
context uses the SOURCE'S OWN SCIENTIFIC VOCABULARY (`temperature`,
`temperature_unit`), while a source's `required_parameters` use its
ACQUISITION vocabulary (`station`, `begin_date`, `path`). The two
coincide only by accident. So the caller states the correspondence, once,
and this module verifies it rather than guessing:

    every key of `intent.target_context`
        must appear in `context_parameters`      -> else it would vanish
    every value of `context_parameters`
        must be one of `source.required_parameters` -> else the source
                                                       does not accept it

Both failures raise `IntentNotOperationalizable`. An intent that cannot
be expressed for a given source is a real and reportable state -- not an
error to be papered over, and not a reason to drop the context.

NO EXECUTION HERE. This function builds a plan and returns it. It opens
no network connection, reads no clock, touches no `EvidencePool`, mutates
no registry, and acquires nothing. `daf.scheduling.runner.execute_plan`
is already the execution interface and is used unchanged; wrapping it
here would add a function that only forwards its arguments.

DETERMINISM. Pure function of its arguments. `plan_id` and
`requested_at` stay caller-supplied -- deriving `plan_id` from
`intent.id` would tie checkpoint identity to scientific identity, which
Phase 20 established must stay separate.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from boundary.acquisition_intent import AcquisitionIntent
from daf.catalog.plan import AcquisitionPlan
from daf.orchestration.source_registry import SourceDefinition


class IntentNotOperationalizable(ValueError):
    """Raised when an `AcquisitionIntent` cannot be expressed as an
    `AcquisitionPlan` for a particular source without losing or
    fabricating scientific meaning."""


def operationalize_intent(
    intent: AcquisitionIntent,
    source: SourceDefinition,
    *,
    plan_id: str,
    parameters: Optional[Mapping[str, Any]] = None,
    context_parameters: Optional[Mapping[str, str]] = None,
    mode: str = "snapshot",
) -> AcquisitionPlan:
    """Deterministic, side-effect-free.

    `parameters` are the source's own acquisition parameters, chosen by
    the caller. `context_parameters` maps each key of
    `intent.target_context` onto the source parameter that carries it.

    Raises `IntentNotOperationalizable` when a context key has no mapping
    (it would be silently discarded), when a mapping names a parameter
    the source does not declare, or when a mapping would overwrite a
    caller-supplied parameter with a different value -- that last case is
    an ambiguity only the caller can resolve, so it is reported rather
    than guessed."""
    parameters = dict(parameters or {})
    context_parameters = dict(context_parameters or {})

    unmapped = sorted(set(intent.target_context) - set(context_parameters))
    if unmapped:
        raise IntentNotOperationalizable(
            f"intent {intent.id[:12]}... cannot be operationalized for source "
            f"{source.source_id!r}: conditioning context {unmapped!r} has no parameter "
            f"mapping, and acquiring without it would return evidence that does not "
            f"answer the question"
        )

    unknown = sorted(
        {name for key, name in context_parameters.items() if key in intent.target_context}
        - set(source.required_parameters)
    )
    if unknown:
        raise IntentNotOperationalizable(
            f"source {source.source_id!r} does not declare parameter(s) {unknown!r}; "
            f"its required_parameters are {list(source.required_parameters)!r}"
        )

    resolved: Dict[str, Any] = dict(parameters)
    for context_key, parameter_name in sorted(context_parameters.items()):
        if context_key not in intent.target_context:
            continue
        value = intent.target_context[context_key]
        if parameter_name in resolved and resolved[parameter_name] != value:
            raise IntentNotOperationalizable(
                f"parameter {parameter_name!r} was supplied as {resolved[parameter_name]!r} "
                f"but the intent's context {context_key!r} requires {value!r}; "
                f"only the caller can decide which is correct"
            )
        resolved[parameter_name] = value

    return AcquisitionPlan(
        plan_id=plan_id, source_id=source.source_id, parameters=resolved, mode=mode
    )
