# Recovery ↔ Live Parity: the semantic contract and the decision matrix

Read this before touching: the live opening/closing branch entry conditions, the
recovery's caught-up base flip, `base_gates`, `closing_position_hold`,
`caught_up_closing_hold`, `manual_holds_reposition`, `recovered_vent_ok` /
`recovered_cascade_window` — or before adding ANY new gate to the live opening
or closing branch (the checklist at the end tells you where it must also land).

---

## The semantic contract

**Recovery is a reconciliation from the currently observable state — not a
historical replay of the outage.**

> Given the same current inputs (sensors, schedule phases, positions, `!input`
> condition verdicts) and the same persisted helper state, the recovery reaches
> the same base-transition decision, the same drive/no-drive decision and the
> same helper mutations the live opening/closing path reaches at that moment.

Perfect historical replay is impossible and is **not** claimed: transient sensor
states that crossed and un-crossed during the outage, `for:` durations and the
ordering of events inside the outage are unknowable. Where that matters, the
recovery evaluates the *present*; the short list of remaining deviations (R1–R5
below) is exactly that class, each with the reason and the test that asserts it
**as** a deviation.

**Two separable concepts, and every recovery step belongs to exactly one:**

1. **State hygiene / repair** — no live counterpart by design, can never move
   the cover by itself: clearing an expired override (`override_expired`),
   dropping a stale-day shading (`stale_day`), clearing a dead pending
   (`pending_is_stale`), re-reading `win`/`res`/`frc` from the live entities.
2. **Current-state reconciliation** — the *shared* live decision model: the
   `base_gates` projections decide the base flip, the anchored `!input`
   condition nodes carry the user conditions, the cascade (`recovered_state`,
   parity-locked to `effective_state`) decides the target, `state_targets`
   supplies the drive parameters, and the holds suppress exactly the movements
   the live branch suppresses.

---

## One source of truth: the shared projections and anchored nodes

Business predicates live in named action-level projections consumed by **both**
paths; `!input` conditions (not expressible in Jinja) are **anchored YAML
nodes** defined at the recovery (first occurrence in document order) and aliased
by every live consumer. Never copy either kind inline.

| Shared element | Live consumer(s) | Recovery consumer |
|---|---|---|
| `base_gates.{opening,closing}.{override_ok,once_ok,schedule_ok}` | "Check for opening"/"Check for closing" entries | the flip conditions (compositions below) |
| `closing_position_hold` | "Only status change if cover is shaded…" | `caught_up_closing_hold` |
| `&auto_up_condition_check` / `&auto_down_condition_check` | branch entries (alias) | flip conditions (anchor) |
| `&auto_ventilate_condition_check` | all 7 live ventilation leaves (closing C-B, shading-end vent, contact tilt ×2, resident ×2, force-disable vent) | captures `recovered_vent_ok` for the caught-up closing fallback and the lockout drive hold |
| `environment_allows_opening/closing` | inside `schedule_ok` | same instance |
| `state_targets` / `state_labels` | every drive branch | recovery drive |
| `effective_state` ↔ `recovered_state` | the cascade | the same cascade on `new_base` / `live_force`; only a caught-up closing may project a refused tilted VENT leaf to `cls` (Invariant 13 + branch composition) |
| `lockout_now.closing` shape (opened, or tilted+option) | closing C-A | the tilted clause of `caught_up_closing_hold` |

**Recovery-only composition on top of the shared elements** (each deliberate,
each pinned): `or override_expired` on the override gates (R1), the closing
night clause `not is_evening_phase or …` (previous evening's ultimate closing —
no environment gate in the normal flow at night either), and the flip-direction
condition (`recovery_catch_up and recovered_base == … and helper base != …`).

**Why the flip may consume `schedule_ok` verbatim:** `recovered_base == 'opn'`
implies `is_daytime_phase` and (phases are disjoint) `not is_evening_phase`, and
a flip never happens with `is_time_control_disabled` — under those implications
the projection reduces to the direction's late-or-environment gate.
`TestEnvironmentGatesTheCaughtUpBaseFlip` pins the reduction.

**The ventilation condition.** The cascade cannot evaluate `!input`, so the
recovery evaluates the anchored node **once, before the flip** (a `choose:`
whose two branches share the flip step as the `&recovery_flip` anchor — HA
variables do not escape branches, so the remainder must live inside both).
The verdict is branch-specific, not a cascade property:

- only a **caught-up closing** may map a tilted `recovered_window` to `'cls'`
  for target selection, matching C-B falling through to C-E;
- outside a caught-up opening, a refused condition holds a recovery LOCKOUT
  drive, matching the live contact-opened leaf that owns that movement; O-E
  does not consume this condition and therefore keeps its lockout target;
- every other cascade calculation keeps the real window state. In particular,
  the shading-start ventilation floor has no such live condition and must not
  be removed by recovery.

`recovered_window` itself always remains sensor truth for lockout logic, holds
and persisted `win`.

**Drift protection is closed, not token-based:**
`TestClosedEntryStructure` asserts the live entries and the flip conditions are
**exactly** the known term lists — any new inline condition (a hypothetical
`{{ holiday_allows_closing }}` included) fails until routed through the shared
projections — and asserts node *identity* (`is`) for every anchored `!input`
condition, including all 8 tree positions of the ventilate node.

---

## The paired execution suite (`tests/test_recovery_live_parity.py`)

Not a hand-written oracle: a small evaluator interprets the **parsed YAML** of
both paths — real branch conditions in order, injected verdicts for every
`!input` condition (an un-stubbed one raises), real `variables:` chains
(`will_drive`, `drive_plan`, `update_values`), stopping at the shared
apply-transition anchor (identified by object identity). Every paired scenario
compares: transition accepted/rejected, resulting `bas`, drive/no-drive (through
the shared actuation tolerance), target position **and tilt**, `action_set`, and
the persisted `shd`/`pnd`/`man`/`ts.opn`/`ts.cls`/`ts.due`/`ts.arm`. `win` is
the declared hygiene field (checked against the live sensor state). Scenario
axes: the exact #656 case, hysteresis boundaries, AND/OR environment modes,
ultimate-late, once-per-day, manual override (all four configurations), open /
tilted windows, ventilation condition true/false, tilted-lockout option,
shading active/pending, prevent options, force, pause, resident privacy.

---

## The decision/effect matrix

### Closing: live "Check for closing" vs. recovery caught-up closing

| Gate / situation | Live | Recovery | Status |
|---|---|---|---|
| `is_down_enabled` | entry condition | inside `recovered_base` | equivalent by construction |
| `auto_down_condition` | alias | anchor | same node |
| override / once / schedule | `base_gates.closing.*` | same (+`override_expired`, night clause) | shared |
| window fully open, condition allowed | C-A: status only; cover normally reached lockout through the contact handler | `lock` → same target; no movement at the target | shared **system** outcome (see R3 for the away-from-target case) |
| window fully open, condition refused | C-A: status only; the live contact-opened leaf also refuses its drive | `lock`, but `recovery_vent_condition_hold` suppresses the drive | shared drive decision |
| window tilted + lockout option | C-A (via `lockout_now.closing`): status only, regardless of the vent condition | `caught_up_closing_hold` tilted clause: status only | shared outcome (R4 for the `win` stamp) |
| window tilted, condition allowed | C-B: drive to ventilate | `vnt` → same `state_targets.vnt` | shared |
| window tilted, condition refused | C-B skipped → C-E closes fully | masked cascade → `cls` → same close | **shared** (was the worst deviation; fixed) |
| already at close position | C-C: base-only update | tolerance guard | equivalent |
| `closing_position_hold` | C-D: status only | hold: status only | shared projection |
| normal closing | C-E: drive, `man: 0` on drive | same target/action_set, `man: 0` on movement | shared |
| mutations | `bas/shd/pnd/ts.cls/ts.due/ts.arm` in every sub-branch | flip-scoped `recovered_shade: false`, `caught_up_closing` clears pnd/due/arm, `ts.cls: 'now'` | shared |

### Opening: live "Check for opening" vs. recovery caught-up opening

| Situation | Live | Recovery | Status |
|---|---|---|---|
| entry gates | `base_gates.opening.*` + anchored condition | same + compositions | shared |
| manual override, ignore option active | base transition persists, drive is suppressed and `man` remains | flip persists the same transition; drive gate consumes `override_ok` | shared |
| manual override, no ignore option | O-E drives and clears `man` | caught-up transition drives and clears `man` | shared |
| shading warranted (O-A) / pending (O-D) | arm/defer | `recovered_pending` re-evaluates; `defer_to_shading` | re-evaluation semantic (R5) |
| shading active (O-C) | drive to shading position, `shd` kept, **no `ts.opn` stamp** | opening flip keeps `recovered_shade` → `shd` target; `ts.opn` stamp suppressed when `recovered_state == 'shd'` | shared (the stamp omission was found by the paired suite) |
| normal opening (O-E) | `allow_open` + force gate; lockout target on `lock`, opening action set | cascade + `force_allows_open`; lock keeps O-E's `up` action set | shared |
| cascade produces a non-opening target (`cls`/`vnt`, or force-only `shd`) | O-C/O-E does not authorize that drive | `caught_up_opening_hold` suppresses it | shared drive decision |

### Recovery-only hygiene (deliberately no live counterpart, never moves the cover)

`stale_day` cleanup, `pending_is_stale` cleanup, `override_expired` repair
(`man: 0` + the user's reset action; the live reset reconciles the already-current
background `effective_state`, #655),
`win`/`res`/`frc` re-read and persistence.

---

## Remaining deviations (each asserted AS a deviation by a test)

| # | Deviation | Why it stays, and what the live reference says | Test |
|---|---|---|---|
| R1 | `… or override_expired` lets the recovery drive after the override's reset moment fell into the outage | Whether the swallowed movement fell before or after the expiry is unknowable. Live continuously persists background transitions and its reset reconciles the current `effective_state`; recovery repairs the expired override and performs the equivalent reconciliation after deriving any transition whose event the outage swallowed. | `TestManualOverrideParity::test_an_expired_override_is_the_post_repair_reconciliation` |
| R2 | `manual_holds_reposition`: a recovery run **without** a base transition does not drive over `man == 1` | There is no live event to compare — nothing happened; a pure re-position is recovery-only motion, and driving over a recorded intervention without a caught-up event would *fight* the user. A caught-up transition is exempt only after its live subbranch has authorized that target; `caught_up_opening_hold` and `caught_up_closing_hold` reject unrelated cascade targets. | `TestRecoveryDrive::test_a_manual_override_holds_a_pure_reposition` / `TestManualOverrideParity` / `TestForceAndPauseParity` |
| R3 | With the condition allowed, a caught-up closing with the window fully open and the cover **away** from the lockout position drives to the lockout position (live C-A drives nothing) | The live *system* put the cover there via the contact-opened handler before the closing ran; a cover elsewhere means that contact event was swallowed too, and the recovery catches both up — to the same target the live handler owns. When the user's condition refuses that contact drive, recovery holds too. | `TestWindowParity::test_open_window_away_from_lockout_position_is_reconciled` / `…does_not_recover_to_lockout` |
| R4 | `win` is persisted as the live sensor reading; C-A's `'opn'` stamp for a tilted window with the lockout option is not replicated | The helper's `win` is the Tier-2 fallback truth for the next outage; the contact handler — the normal owner of persisted window state — writes sensor truth, and the next contact event re-syncs live to it anyway. The no-movement outcome is identical (the hold). Narrow scope: tilted + option + caught-up closing only. | `TestWindowParity::test_tilted_lockout_option_holds_both_paths` (outcome parity; `win` declared hygiene) |
| R5 | Shading and transient environment crossings are **re-evaluated, not replayed**; `is_time_control_disabled` has no base flip | `recovered_pending` arms from current conditions and the execution flow (whose entry gates evaluate the shading conditions/overrides) moves; a crossing that un-crossed is not warranted *now*; a pure-environment schedule has no time axis to re-derive and the current reading sits inside the hysteresis band. | `TestRecoveredPending`, `TestEnvironmentGatesTheCaughtUpBaseFlip`, `TestRecoveredBase` |

Former deviations now **eliminated**: the caught-up closing's
`auto_ventilate_condition` bypass (evaluated via the anchored node + scoped
fallback), the any-`man` drive block for live-authorized caught-up targets,
the missing tilted-lockout hold, and the `ts.opn` stamp on an opening that
lands in shading.

---

## The checklist for a new live gate

1. Put the predicate into `base_gates.<direction>` (or a new named projection);
   a `!input` condition becomes an anchored node defined at the recovery and
   aliased live.
2. Decide its recovery composition: verbatim, composed with a repair term, or a
   genuine R-row (then: rationale + a test that asserts the deviation).
3. `TestClosedEntryStructure` WILL fail on any inline addition — extend its
   expected shape deliberately, in the same commit as the paired scenario that
   proves the recovery side.
4. A new no-movement outcome of the closing branch belongs in
   `closing_position_hold` (shared) or `caught_up_closing_hold` (composition),
   never in a third place.
