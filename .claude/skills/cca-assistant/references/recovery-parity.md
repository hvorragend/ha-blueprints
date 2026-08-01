# Recovery ↔ Live Parity: the semantic contract and the decision matrix

Read this before touching: the live opening/closing branch entry conditions, the
recovery's caught-up base flip, `base_gates`, `closing_position_hold`,
`caught_up_closing_hold` — or before adding ANY new gate to the live opening or
closing branch (the contract below tells you where it must also land).

---

## The semantic contract

**Recovery is a reconciliation from the currently observable state — not a
historical replay of the outage.**

> Given the same current inputs (sensors, schedule phases, positions) and the same
> persisted helper state, the recovery must reach the same base-transition
> decision, the same drive/no-drive decision and the same helper mutations that
> the live opening/closing path would reach at that moment.

Perfect historical replay is impossible and is **not** claimed: transient sensor
states that crossed and un-crossed during the outage, `for:` durations, arbitrary
user conditions and the ordering of events inside the outage are unknowable.
Where that matters, the recovery evaluates the *present* and the deviation from a
hypothetical replay is documented in the "intentional recovery semantics" table
below — each with the reason the present-state reading was chosen.

**Two separable concepts, and every recovery step belongs to exactly one:**

1. **State hygiene / repair** — no live counterpart by design, can never move the
   cover by itself: clearing an expired override (`override_expired`), dropping a
   stale-day shading (`stale_day` → `recovered_shade`), clearing a dead pending
   (`pending_is_stale`), re-reading `win`/`res`/`frc` from the live entities.
2. **Current-state reconciliation** — evaluates the *shared* live decision model:
   the `base_gates` projections decide the base flip, the cascade
   (`recovered_state`, parity-locked to `effective_state` by `TestCascadeParity`)
   decides the target, `state_targets` supplies the drive parameters, and the
   drive holds (`caught_up_closing_hold`) suppress the movements the live branch
   would have suppressed.

---

## One source of truth: the shared projections

Business predicates live in named action-level projections consumed by **both**
paths. Never copy one of these formulas inline — extend the projection, and both
paths follow:

| Projection | Live consumer | Recovery consumer |
|---|---|---|
| `base_gates.opening.override_ok` | "Check for opening" entry | opening flip (`… or override_expired`) |
| `base_gates.opening.once_ok` | "Check for opening" entry | opening flip |
| `base_gates.opening.schedule_ok` | "Check for opening" entry | opening flip (verbatim — the flip context makes the extra clauses neutral, see below) |
| `base_gates.closing.override_ok` | "Check for closing" entry | closing flip (`… or override_expired`) |
| `base_gates.closing.once_ok` | "Check for closing" entry | closing flip |
| `base_gates.closing.schedule_ok` | "Check for closing" entry | closing flip (`not is_evening_phase or …` — the night clause) |
| `closing_position_hold` | "Only status change if cover is shaded…" branch | `caught_up_closing_hold` |
| `environment_allows_opening/closing` | inside `schedule_ok` | inside `schedule_ok` (same instance) |
| `state_targets` / `state_labels` | every drive branch | recovery drive |
| `effective_state` ↔ `recovered_state` | the cascade | the same cascade on `new_base`/`live_force` (Invariant 13, `TestCascadeParity`) |

**`!input` conditions cannot move into Jinja projections** (they only evaluate at
fixed YAML positions). `auto_up_condition` / `auto_down_condition` are therefore
**anchored YAML nodes**: defined at the recovery flip (`&auto_up_condition_check`,
`&auto_down_condition_check` — first occurrence in document order) and aliased by
the live branch entries. `TestSharedProjectionStructure::
test_the_input_condition_is_the_same_yaml_node` asserts object identity (`is`),
so the correspondence cannot silently fork. Anchors are used **only** for such
truly identical YAML nodes — they are not a substitute for named projections.

**Why the flip may consume `schedule_ok` verbatim.** The projection contains
clauses the flip context already decides: `recovered_base == 'opn'` implies
`is_daytime_phase` and (phases are disjoint) `not is_evening_phase`, and a flip
never happens with `is_time_control_disabled` (then `recovered_base` keeps the
helper base). Under those implications `schedule_ok` reduces to exactly the
pre-refactor flip gate (`is_time_up_late or environment_allows_opening`; closing
analogously). `TestEnvironmentGatesTheCaughtUpBaseFlip` renders the projection
under the flip context and pins this reduction.

**Drift protection:** `tests/test_recovery_live_parity.py` —
`TestSharedProjectionStructure` fails when either side re-inlines a predicate
(`override_blocks.`, `prevent_flags.`, `environment_allows` are forbidden strings
in both branch-entry condition sets), and the paired scenario classes render both
paths end-to-end on the same inputs and compare outcomes.

---

## The decision/effect matrix

### Closing: live "Check for closing" vs. recovery caught-up closing

Entry gates:

| Gate | Live | Recovery | Classification |
|---|---|---|---|
| `is_down_enabled` | entry condition | `recovered_base == 'cls'` requires it | equivalent by construction |
| trigger identity | `t_close_*` / `t_calendar_event_*` | `t_recovery` + the claims | the event-vs-reconciliation split (contract) |
| `auto_down_condition` | `*auto_down_condition_check` | `&auto_down_condition_check` | **same YAML node** |
| manual override | `base_gates.closing.override_ok` | same `or override_expired` | shared + intentional semantic I1 |
| once a day | `base_gates.closing.once_ok` | same | shared |
| schedule + environment | `base_gates.closing.schedule_ok` | `not is_evening_phase or` same | shared + intentional semantic I6 (night clause) |

Sub-branch outcomes and mutations:

| Situation | Live outcome | Recovery outcome | Classification |
|---|---|---|---|
| window fully open | C-A: status only (no drive); `win: 'opn'` | `recovered_state = 'lock'` → drives to `effective_lockout_position`; `win` = live sensor | intentional I4 + I5 |
| window tilted + `lockout_tilted_when_closing` | C-A via `lockout_now.closing`: status only | `caught_up_closing_hold` (vnt + option): status only | shared outcome |
| window tilted, no option | C-B: drive to ventilate (gated on `auto_ventilate_condition`) | `recovered_state = 'vnt'` → drive to ventilate (same `state_targets.vnt`) | shared target; condition = intentional I3 |
| already at close position | C-C: base-only update | tolerance guard / `recovery_in_position` | equivalent mechanism |
| `closing_position_hold` (prevent options) | C-D: status only | `caught_up_closing_hold`: status only | **shared projection** |
| normal closing | C-E: drive to close, `man: 0` on drive | drive to close, `man: 0` when it actually moves | equivalent; drive gate differences = I2 |
| helper mutations | `bas: 'cls'`, `shd: 0`, `pnd: 'non'`, `ts.cls: now`, `ts.due/arm: 0` in **every** sub-branch | `new_base`, `recovered_shade: false` (flip-scoped), `caught_up_closing` clears `pnd`/`ts.due`/`ts.arm`, `ts.cls: 'now'` on flip | shared (flip-scoped) |
| `win` mutation | C-A stamps `'opn'` as a lockout marker (even when only tilted+option) | persists the live sensor reading | intentional I5 |

### Opening: live "Check for opening" vs. recovery caught-up opening

| Situation | Live outcome | Recovery outcome | Classification |
|---|---|---|---|
| entry gates | `base_gates.opening.*` + anchored `auto_up_condition` | same projections + `override_expired` composition | shared |
| shading warranted at opening time | O-A arms a pending and defers (#555/#651) | `recovered_pending` re-evaluates and arms; `defer_to_shading` defers the drive (#555, Bug AG lockout exemption) | shared concept, re-evaluation semantic I8 |
| already open | O-B position guard | tolerance guard | equivalent |
| shading active | O-C: drive to shading position, `shd` survives | opening flip keeps `recovered_shade` → `recovered_state = 'shd'` → same target | shared |
| normal opening | O-E: `resident_flags.allow_open` + force gate; lockout target when `effective_state == 'lock'` | cascade (`allow_open` → cls; `lock` beats base) + `force_allows_open` | equivalent |
| mutations | `bas: 'opn'`, `shd` per sub-branch, `ts.opn: now` | `new_base`, `recovered_shade` untouched, `ts.opn: 'now'` on flip | shared |

### Recovery-only (hygiene/repair — deliberately no live counterpart)

| Step | Repairs | Why it cannot move the cover |
|---|---|---|
| `stale_day` → `recovered_shade`, `ts.opn/cls` zeroed | the 23:55 reset that never ran | write only; the drive follows the cascade *after* the repair |
| `pending_is_stale` | execution trigger consumed by the outage | clearing is terminal, nothing drives |
| `override_expired` → `man: 0` + `auto_override_reset_action` | latched reset triggers | clearing moves nothing (Invariant 7 exception); the *drive* is a reconciliation decision, see I1 |
| `res` / `frc` (`live_force`) / `win` re-read | stale fallback values | pure persistence |

---

## Intentional recovery semantics (documented deviations)

Each row is asserted **as a deviation** by a test — changing one is a semantic
decision, not a bug fix.

| # | Deviation | Chosen semantic and rationale | Test |
|---|---|---|---|
| I1 | `override_ok or override_expired` on the flip | **Post-repair reconciliation.** Whether the swallowed movement fell before or after the override's expiry is unknowable (and irrelevant to the present): live's fixed-time/timeout reset (BRANCH 10 default) clears `man` without driving or syncing `bas`, so a live timeline with event-before-expiry leaves the cover unmoved *only because nothing re-triggers* — a gap, not a decision. The recovery repairs first, then reconciles against the repaired state. | `TestOverrideAndOnceParity::test_an_expired_override_is_an_intentional_recovery_semantic` |
| I2 | `recovery_allowed` blocks the drive on **any** `man == 1` | Stricter than live's per-function `override_blocks`: after an outage/restart a recorded manual intervention is respected wholesale (#603 — do not fight the user's move within seconds of a resume). The flip *write* follows the live per-function granularity; only the drive is conservative. | `TestRecoveryDrive::test_a_manual_override_blocks_the_drive` |
| I3 | `auto_ventilate_condition` is not evaluated for a `vnt` cascade target | The cascade cannot evaluate `!input` conditions, and the ventilation floor is a state, not an event: the condition gates *event-driven* ventilation moves. (Note: live's own `effective_state` has the same property — the branch and the cascade already disagree in live when the condition is false.) | `TestWindowParity::test_tilted_window_goes_to_ventilation_in_both_paths` (target parity; the condition stays unevaluated) |
| I4 | Caught-up closing with the window fully open **drives to the lockout position** where live's closing branch skips the movement | Reconciliation: the (equally swallowed) contact-opened handler would have established exactly that target; the movement is upward and safe. | `TestWindowParity::test_open_window_lockout_is_an_intentional_recovery_semantic` |
| I5 | `win` is persisted as the live sensor reading, never as C-A's `'opn'` lockout marker | The helper's `win` is the Tier-2 fallback truth for the next outage — poisoning it with a marker breaks the fallback. The no-movement outcome is achieved by the drive hold instead. | covered by `TestRecoveryPersists` |
| I6 | The closing flip's night clause (`not is_evening_phase or …`) is unconditional | Between midnight and the opening time the previous evening's *ultimate* closing is being carried forward — the normal flow has no environment gate after `time_down_late` either. | `TestEnvironmentGatesTheCaughtUpBaseFlip::test_the_night_clause_stays_unconditional` |
| I7 | `is_time_control_disabled` → no base flip at all | A pure brightness/sun schedule has no time axis to re-derive from; the current environment reading sits inside a hysteresis band whose crossing direction is unknowable. Known limitation: a closing swallowed under time-control-off stays missed until the next crossing. | `TestRecoveredBase` |
| I8 | Shading is **re-evaluated, not replayed** | `recovered_pending` arms from the *current* conditions; the execution flow (whose entry gates evaluate `auto_shading_*_condition`, `override_blocks.shading`, the window) does the movement. A condition that crossed and un-crossed is not replayed — same reasoning as the environment gate on the flip. | `TestRecoveredPending` |
| I9 | Transient environment crossings are not replayed | "If the conditions do not warrant it *now*, do not replay it"; the ultimate late times remain the backstop. | `TestEnvironmentGatesTheCaughtUpBaseFlip` |

---

## The checklist for a new live gate

Adding a condition to the live opening/closing branch entry? Then:

1. Put the predicate into `base_gates.<direction>` (or a new named projection) —
   not inline.
2. Decide its recovery composition: consumed verbatim, composed with a repair
   term (like `override_expired`), or intentionally live-only (then add a row to
   the deviations table above *with a rationale and a test*).
3. Extend `TestSharedProjectionStructure` (forbidden-string list) and add a
   paired scenario in `tests/test_recovery_live_parity.py`.
4. A new *no-movement* outcome of the closing branch belongs in
   `closing_position_hold` (shared) or `caught_up_closing_hold` (recovery
   composition), never in a third place.
