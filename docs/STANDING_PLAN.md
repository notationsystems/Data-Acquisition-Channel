# Notation Physical Commerce — standing development plan

A recursive plan. It does not list tasks; it defines a loop that generates
the next task from the state of the tree, and the conditions under which
it stops and asks a person.

Hand this to a session cold. It should not need context from any
conversation, including the one that produced it.

**Committed to the tree on 2026-08-31** so a cold session finds it by
looking rather than by being told. Enforced by
`tests/test_commerce_standing_plan.py`, which checks the plan's §1 against
the tree rather than trusting it.

---

## 0. How to use this document

Run §2 (the cycle). When the cycle asks what to do next, run §3 (the
precedence rule). When the precedence rule returns nothing executable, run
§4 (escalation) and stop. §5 is the phase arc; §6 is the doctrine you carry
into every cycle; §7 is how this document updates itself.

**This document is a pre-registration.** If the tree has moved far enough
that its instructions read as archaeology, re-derive from §5's entry
conditions rather than obeying the text. A pre-registration aged into
archaeology is re-taken, not obeyed.

---

## 1. Standing position

Verify all of this against the tree before acting on it. A test does.

- **DAQ `commerce/`** — canonical three-store split, CanadaBuys ingest,
  tender extraction, landed cost, agent authority barrier, carrier vetting
  on a routing table, opportunity engine items 1–5, insurance predicate
  from SOR/2005-180 s.7, award adapter, operator CLI.
- **Sea Dog Terminal** — frozen at `5a6def1`. Do not touch it. Class 8 is
  recorded in DAQ and cannot join the canonical register until that freeze
  resolves.
- **Blocked on a person:** QCMobile webKey, ORS registration, load board
  terms, AIS, LME, and the first real transaction.
- **Blocked on nothing but a transaction:** VROOM, H3, Tile38, PostGIS,
  MobilityDB, DuckDB.

---

## 2. The cycle

One cycle = one item. Do not batch.

```
1  ORIENT     read the tree, not the record. Run the gates. Read the
              ledger's open items and any fired guard.
2  SELECT     apply §3. If it returns nothing, go to §4.
3  PRE-REGISTER
              before building: write what you expect, and what result
              would show you wrong.
4  RECON      if the item touches an external source, probe it first and
              commit verbatim captures. Never build against an imagined
              shape.
5  BUILD      tests first where the item admits them.
6  PROBE      test the rule, not the tests. Plant the violation and watch
              the check fail by name before trusting it.
7  MEASURE    run it against real state. Report the number, not the intent.
8  GATE       all four gates, on the pushed tree. Local green is a
              hypothesis.
9  RECORD     ledger entry: what was measured, the verdict, what the work
              revealed that was not anticipated, and every self-correction.
10 REPORT     the above, plus exactly one next executable frontier.
11 REPEAT
```

A cycle with no self-correction is a cycle where nothing was probed. Say so
if that happens rather than presenting it as clean.

---

## 3. Precedence — the rule that makes this recursive

Take the first that applies. Do not weigh them against each other.

| # | Condition | Why it outranks the rest |
|---|---|---|
| 1 | A `validWhile` guard has fired | A deferred decision's premise has lapsed. Re-take it, or acknowledge it with a new trigger. Never exempt it. |
| 2 | A gate is red on the pushed tree | Everything below is unverified until this is green for a reason someone chose. |
| 3 | A live surface is producing a wrong answer | A wrong number in service outranks a missing capability. |
| 4 | A refusal in the queue has an executable, unblocked remedy | The system has told you what it needs, in its own words, with the remedy attached. |
| 5 | A miss-log entry names a registered source that has an adapter | Demand evidence beats reasoning about priorities. |
| 6 | The next item in the current phase (§5) | |
| 7 | Nothing | Go to §4. Do not invent work. |

**Ranking inside a tier:** by yield per unit effort. An item you cannot
price is not low-ranked — it is unranked, with the missing input named. Say
which input.

---

## 4. Escalation — stop and ask

Stop the cycle and report. Do not proceed, do not work around, do not
choose a default.

- **Credentials, registrations, terms of service.** Registering for an API
  accepts terms on the firm's behalf. This includes probing to discover
  terms.
- **Money.** Any purchase, subscription or commitment of funds.
- **Anything that binds the firm to a counterparty.** Quotes, tenders,
  bookings, filings, outbound messages to a carrier or shipper.
- **A declared invariant would have to change.**
- **A canonical schema would change backwards-incompatibly.**
- **A verified subsystem would be deleted or rewritten.**
- **The work requires a real-world event** — a load, a customer, a document
  someone must obtain.

When escalating: name what is blocked, what would unblock it, and what you
did instead. Then take the next item by §3. A blocked item does not stop
the cycle; it stops that item.

---

## 5. The phase arc — entry and exit conditions, not dates

Phases advance on measurement. Do not enter a phase whose entry condition
is unmet, however attractive its work is.

### Phase 0 — One transaction
**Entry:** now. **Exit:** one real load or one real quote recorded end to
end, by hand, with a commitment and an outcome recorded separately.

Nothing else in this plan is unblocked by anything but this. The form
exists, refuses a `known_at` equal to the typing time, and is reachable
from the shell: `python3 -m commerce form` then
`python3 -m commerce record <events.json>`.

**Must not:** build integrations to avoid needing the transaction.

### Phase 1 — Manual operations at volume
**Entry:** Phase 0 exit. **Exit:** twenty loads recorded; lane residuals
computable for at least one repeated lane.

**Must not:** build a load-board adapter, an optimizer, or a spatial layer.
Twenty loads of honest records outrank all three.

### Phase 2 — First integrations, chosen by evidence
**Entry:** Phase 1 exit, and a miss log with entries. **Exit:** at least one
adapter promoted from the gap list *because the miss log named it*.

**Must not:** build an adapter no miss has asked for.

### Phase 3 — Spatial
**Entry:** a facility register with enough resolved facilities that H3
aggregation is not a set of singletons. **Exit:** truck-legal duration on
every quote; facilities resolving rather than duplicating.

Duration, not distance — the restriction expresses itself in time. Address
normalization before anything else in this phase.

**Must not:** self-host a routing engine before a public endpoint has
proven the profile discriminates on a lane that binds.

### Phase 4 — Optimization
**Entry:** enough lane density that consolidation candidates exist in real
data. **Exit:** consolidation as a second ranking pass over priced
opportunities.

**Must not:** build a route engine beyond routing. VRP over real loads, not
a planner.

### Phase 5 — Tender pipeline at scale
**Entry:** the operations core has executed enough that a bid can be priced
from your own history rather than from a market reference. **Exit:** a bid
submitted with a landed cost the system computed and the validator did not
call overstated.

### Deferred until explicitly funded
The digital twin, spatial levels 3–5, asset-level temporal tracking, the
trading and position-taking layer, and the modality programme.

---

## 6. Doctrine — carry this into every cycle

**Commensurability.** Every comparison states basis, population, universe,
partition and completeness.

**Refuse, don't default.** Zero is a value; the absence of a computable
answer is not.

**Which kind of nothing is this.** An empty collection is a claim and needs
a warrant.

**Account for every drop.** Accepted, rejected with a reason, or filtered
with the predicate named and counted.

**A check must be evaluated everywhere its condition holds.**

**Vacuity.** A test that cannot fail is not validation. Plant the condition.

**Knowledge versus world.** `known_at` is when a value became available;
the period is what it describes.

**Attribution.** Name the observable, not the cause you infer.

**Measured, then designed against.** A constraint you correctly measured
must be carried into the design in the same pass.

**Deferrals are conditions.** Every deferred decision carries a
`validWhile` predicate evaluated on every test pass.

**Local green is a hypothesis** until the pushed tree agrees.

**Self-application is a step, not an insight.**

**Knowing a class does not inoculate against the next instance.**

---

## 7. Anti-drift, and how this document updates itself

**No new analytical dimensions.** The most effective way to erode a
deliberate decision is a good idea. When one arrives mid-cycle — and it
will — record it in the ledger as an unbuilt entry with a `validWhile`
predicate naming the condition under which it becomes necessary, and
continue. Do not build it because it is small.

**This document is amended by the same rule as everything else.** An
amendment is a dated entry stating what changed and why, with the reason
given as *the tree moved* rather than *the plan became inconvenient*. Never
edit a phase's exit condition after seeing that it will not be met.

**Re-read trigger.** Re-derive from §5 rather than obeying this text when:
a phase's entry condition is met by a route this document did not
anticipate; a guard fires against something this document asserts; six
cycles have passed without a phase advancing; or the tree contradicts §1.

**Stray messages.** Work arriving that references identifiers absent from
the tree belongs to a different session. Verify by grep, refuse to
reconstruct plausible continuity, and say so.

---

## 8. What done looks like

There is no done. There is a loop, a set of conditions under which it stops
and asks, and a ledger that records why each decision was taken so a future
reader can re-take it rather than inherit it.

The measure of whether this is working is not tests passing or phases
advancing. It is whether the ledger's self-corrections keep arriving. A run
of cycles with none means the probing stopped, and that is the only failure
this plan cannot detect for itself.

---

## Amendments

*(dated entries; reason stated as "the tree moved", never "the plan became
inconvenient")*

**2026-08-31 — §1 amended.** Added the award adapter and the operator CLI
to the standing position. Reason: the tree moved. Both were built before
this plan was committed; the award adapter is recorded in
`architecture/phase_zero_ledger.yaml` as an out-of-phase build under Phase
0's must-not, kept rather than deleted because §4 escalates on deleting a
verified subsystem.
