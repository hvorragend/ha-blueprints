# CCA Design Decisions (intentional deviations)

Every entry here looks like an inconsistency but is deliberate. Read this before
"harmonizing", unifying, or cleaning up anything that seems asymmetric —
especially resident/manual-override gates, pending preserve/discard asymmetries,
and invalid-sensor-state handling. Restart/outage handling has its own file:
`recovery.md`.

---

## Design Decisions (intentional deviations from the general patterns)

### Resident transitions replace earlier manual intent

The resident sensor handler always persists `res` and deliberately does **not**
consume `manual_allows_event` / `override_flags.*` for its target movement.
Presence transitions are configured ownership-changing events: when the
resident leaves or arrives, the cover follows the newly applicable
resident-derived target even while `man == 1`.

This does not weaken the state/effect split. Pause, Force and additional
conditions can still suppress the drive while `res` advances. An already
reached target is a no-op. Only an actual dispatched resident movement clears
`man`; a state-only resident update preserves it.

`manual_allows_event` is deliberately named for the **event policy**, not the
destination state. A shading event can move to the ventilation floor and still
uses `.shd`; a contact event can restore shading and still uses `.vnt`.

The `ignore_*_after_manual` options govern their owning scheduled,
environmental and contact-ventilation event classes, not resident transitions.
This is intentional. Do not "harmonize" the resident handler by routing it
through the ordinary Manual gates.

### Opening handler preserves shading-start pending **only while still warranted**; closing handler discards it

When the opening trigger fires while a shading-start pending is active (`pnd == 'beg'`) **and shading is still warranted**, the opening handler **preserves** `pnd`, `ts.due`, and `ts.arm` and defers to the `t_shading_start_execution` trigger (which fires 1 second later at `ts.due = window_start + 1`). "Still warranted" is the variable `shading_start_warranted` = `shading_start_conditions_met or (independent-temperature path active)` — it mirrors the execution gate exactly.

When the closing trigger fires while a shading-start pending is active, the closing branches **discard** `pnd`/`ts.due`/`ts.arm` by setting them to `non`/`0`/`0`.

**Rationale:** At closing time, a shading-start intent from earlier in the day is no longer relevant — the cover is about to close regardless. Driving it to the shading position only to immediately close it would be wrong. At opening time, the intent is still valid **provided the conditions are still met** — the execution trigger should handle the drive.

**Stale-pending guard (Issue #514):** A pending can be armed before the opening time (brightness briefly exceeds the threshold) and then go stale when the conditions fall back below the threshold *before* the opening time. The `t_shading_start_execution` trigger only ever drives into the shading position or retries/aborts — it **never opens the cover**. So if the opening handler deferred unconditionally, a stale pending would leave the cover stuck closed all morning. The "Opening skipped: Shading start pending" branch therefore gates on `shading_start_warranted`; when the pending is stale the branch is skipped, execution falls through to "Normal opening", which drives the cover open and clears `pnd`/`ts.due`/`ts.arm`.

This asymmetry is intentional. Do not "harmonize" the closing handler to preserve pending — it must discard it. Do not remove the `shading_start_warranted` gate from the opening "skip" branch — that reintroduces #514.

**Branch order (#651):** The re-arm branch "Opening: Shading warranted, arm pending" (#555) sits **before** the "Already in open position" shortcut. Invariant 15 now preserves pending through manual detection, but other legitimate no-pending states still need this handoff; with the shortcut first, an already-open cover can consume the run before warranted shading is armed (Bug Pattern AR). Do not move the shortcut back in front of the arm branch.

### Midnight reset (BRANCH 11) sets `man: 0` without driving

The "Reset shading status that is no longer required" branch writes `man: 0` even though it does not drive the cover. This is an intentional exception to Invariant 7.

**Rationale:** Midnight is the natural reset point for the daily automation cycle. Clearing `man` here ensures stale manual overrides do not block the next day's automation. In practice the branch only fires when shading was active (or pending) at midnight — and in those scenarios the user typically did not override manually, so `man` is already `0`. The explicit reset is a defensive safeguard and is documented as a deliberate exception.

### The force pause is part of every drive gate (CCA 2026.07.13 V6)

`is_paused` used to be checked only inside `cover_move_action` / `tilt_move_action` — the *movement* was suppressed, but everything keyed to the *drive decision* still ran: the user's before/after actions in `drive_with_actions` fired ("cover is opening" notifications with no movement), and the `man:` reset followed `will_drive` (Invariant 7), so a paused run cleared a manual override although nothing moved.

The pause is therefore part of **every** drive gate: all five `state_gates`, every branch-local `will_drive`, and the inline `run:`/`if:` gates of the force handlers and the shading-end drive.

Semantics: a paused run **records** its state transition (helper write, `bas`/`shd`/`win`/`frc` all updated — that is what makes the pause-resume instant) but does not drive, does not run drive actions, and does not touch `man`. When the pause ends, `t_force_pause_disabled` (or, after an outage of the pause entity, its `t_recovery` trigger) drives the cover to `effective_state` — that handler's own `will_drive` is `not is_paused`, guarding the queued-run race where the pause was re-enabled before the resume run executed.

**The actuation-point checks are live reads.** `apply_transition` first projects
whether position or relevant tilt differs outside tolerance. After any pre-drive
delay it reads `states(force_pause)` and `instance_active` directly, before any
user action runs. A full drive then runs the selected before-action and re-reads
both ownership gates once more in `drive_with_actions`. This closes the remaining
race when a user before-action itself waits. The cover and tilt movement anchors
re-read again before their respective service stages because tilt alignment and
cover movement can introduce further waits. The first stage that passes sets
`drive_dispatched`; a later ownership loss can stop the remaining stages without
denying that a partial movement already occurred. Raw tilt-only plans use the
same tilt-stage check. A pause enabled, or a hand-over performed, before any
stage therefore stops movement, the after-action, the drive timestamp and the
automatic manual clear together.

When **default cover actions are disabled**, the user after-action is the
configured movement implementation rather than an optional notification.
CCA cannot inspect whether that sequence calls a cover service, so after the
same projection and live ownership checks, entering the custom-only pipeline
counts as `drive_dispatched`. This preserves the documented custom-actions-only
contract and keeps `d` / the automatic manual clear aligned with that contract.

Enforced by `tests/test_apply_transition_architecture.py::TestForcePauseIsPartOfEveryDriveGate` — a new branch whose drive gate ignores the pause fails structurally. The live actuation gates are pinned by `TestActuationPointLiveGates` in the same file.

### Triggers from/to an invalid sensor state are deliberately ignored

The contact handler ("Contact sensor state changed") gates on **both** the previous and the new trigger state being valid:

```yaml
- "{{ trigger.from_state.state not in invalid_states }}"
- "{{ trigger.to_state.state not in invalid_states }}"
```

(`invalid_states` = `''`, `unavailable`, `unknown`, `none`, `None`, `null`, `query failed`, `[]`.) The global condition additionally rejects any trigger whose `to_state` is invalid.

**Rationale:** A state transition that touches an invalid state is not a real, trustworthy physical event — it is a sensor dropout (connectivity loss, battery, restart) or a recovery from one. Acting on such transitions would move covers based on noise. CCA therefore ignores transitions **into** an invalid state (`on → unavailable`) **and out of** one (`unavailable → off`).

**Known consequence (Issue #505):** If a window contact sensor goes `on → unavailable` (instead of cleanly `on → off`) while CCA holds the cover in the lockout/open position (status `lock`), and the sensor later recovers `unavailable → off`, the recovery transition is ignored. `win` stays `opn` in the helper and a remembered shading (`shd=1`) is not applied until another trigger updates the window state — the cover can stay stuck in `lock`.

**This is intentional, not a bug.** The root cause is an unstable contact sensor reporting `unavailable`. The fix belongs at the sensor (battery / radio range), not in the blueprint. Do **not** remove the `from_state` guard to "process recovery transitions" — that would make CCA act on sensor dropouts. Do not "harmonize" this away.

### Attribute-only re-triggers on contact/resident sensors are ignored (Issue #550)

The contact (`t_contact_tilted_changed`, `t_contact_opened_changed`) and resident (`t_resident_update`) triggers are plain `trigger: state`. By default a HA state trigger with only an `entity_id` fires on **every** change of the state object — including **attribute-only** changes where the actual `on`/`off` value is unchanged (internal `match_all` mode).

The fix is applied **at the trigger**, not in a global condition: each of the three triggers carries `not_to`. Setting *any* of `from`/`to`/`not_from`/`not_to` flips HA out of `match_all`, so the trigger only fires on real state-value transitions and silently drops attribute-only changes:

```yaml
- trigger: state
  entity_id: !input contact_window_tilted
  not_to:
    - "unavailable"
    - "unknown"
  ...
```

**Why the trigger, not a global condition:** A global `condition` still lets the automation *start* — HA records a (stopped) trace for every triggered run. Filtering at the trigger means the automation never runs at all → no trace, no queue entry, no logbook noise. `not_to`/`not_from` require HA ≥ 2023.4; the blueprint's `min_version` (2025.4.0, required by the transition architecture's outer-scope variable updates) covers this.

**Rationale:** A user binding a "noisy" entity to one of these inputs — classically a HA **Threshold helper** built on `sun.elevation`, whose `sensor_value` attribute updates on every elevation step — would otherwise re-fire the whole automation every few minutes although the entity's real state changes only twice a day. There was never any functional harm (`mode: queued`, every branch idempotent), only trace/logbook noise.

**Why `not_to` (not `to`):** Contact/resident sensors can report `on`/`off` *or* `true`/`false`, so an allow-list (`to: [...]`) would be fragile. `not_to: [unavailable, unknown]` only excludes the dropout sentinels, keeps every real transition, and aligns with the existing `invalid_states` handling (the `to_state` invalid-state guard in the global conditions and the contact handler). The `from`-side recovery guard (#505) stays in the action conditions — `not_to` does not touch it.

**Scope:** Only contact + resident. The manual triggers (`t_manual_position`, `t_manual_tilt`) deliberately react to attribute changes (`current_position` / `current_tilt_position`) and must **not** get `not_to`.

---

### Tilt is part of status detection, but the last applied tilt is NOT persisted (#558)

The position checkers (`in_open/close/shading/ventilate_position`) compare the
current tilt against the target tilt within `tilt_position_tolerance` (an
absolute dead-band, analogous to `position_tolerance`). This lets states that
share the same cover position be told apart by their tilt angle (e.g.
`closed`/`shading`/`ventilate` all at position `0`). The same dead-band gates
manual tilt-change detection so small tilt jitter is not read as manual.

`in_shading_position` compares against the **dynamically computed**
`shading_tilt_position`. When the sun crosses a tilt-stage threshold, the target
briefly differs from the physically applied tilt until the `t_shading_tilt_*`
trigger re-drives — so the checker can read "not in shading position" for that
short window. This volatility is **intentionally not** stabilized by persisting
the last applied tilt in the helper (a `tp` field was considered and rejected):
the status helper holds *logical* state, not the last *physical* tilt. A
stateless fix (accepting any configured shading stage) is also rejected — it
would reintroduce the #558 ambiguity (e.g. a closed cover at tilt `0` matching a
shading stage configured to `0`). The volatility does not occur at all with a
single (non-staged) shading tilt.

Do not re-add a `tp`/last-tilt helper field to "fix" this.

---

### Alternate shading position resolves live via `effective_shading_position` (#580)

An optional second shading depth (`shading_position_alt`) is active while the
gating entity (`shading_position_alt_entity`, `binary_sensor`/`input_boolean`)
is `on`. The single source of truth is the `effective_shading_position`
variable (full `variables:` block — it calls `states()`, so it must not move
into `trigger_variables:`, Invariant 10). **Every** shading consumer reads it:
`in_shading_position`, all shading-related `position_comparisons`, and every
drive site (`target_position`). Never reference the raw `shading_position`
input in a consumer — that silently breaks the alt depth.

The mid-shading depth switch is handled by `t_shading_position_alt` + the
"Check for alternate shading position" branch (3b), modeled on "Check for
shading tilt": the reducer branch remains reachable while `shd == 1`; force,
resident, window and manual belong to its `will_drive` effect gate. It
re-applies the shading **tilt** after the position move (a position drive
physically disturbs the slat angle on tilt covers). The central transition
anchor clears `man` only after a real dispatch (Invariants 1+7).
A depth change is **not** a shading start: `shd`, `ts.shd`, and the pending
keys stay untouched, so `prevent_shading_multiple_times` is unaffected. No
helper field stores the active depth (same rationale as #558 — the helper
holds logical state; the brief `in_shading_position` volatility after a switch
is accepted and healed by the re-drive trigger).

### Independent shading hold gates `shading_end_conditions_met` live (#605)

The option `shading_independent_holds_end` (in `shading_config`) keeps an
active shading from ending while the independent temperature threshold is
still exceeded. The single source of truth is `independent_shading_holds`,
and it is consumed at exactly **one** choke point: `and not
independent_shading_holds` inside `shading_end_conditions_met`. That covers
every end path consistently — the end-pending arming, the execution re-check
and retry/abort, the #554 start-side cancel branch (`not
shading_end_conditions_met` → an armed end-pending is canceled while the hold
is active), the recovery's end-arm, and `shading_ended_during_force` in the
force-disable recovery (a stored shading is restored, not dropped, while the
hold is active). Do not gate individual end branches instead.

Deliberate semantics:

- **Live-evaluated, not "how was the shading started".** The helper does not
  record the start path (same rationale as #558 — logical state only). A
  shading started via the normal AND/OR conditions also holds on a hot day.
  On cool days (`independent_shading_holds` false) nothing changes.
- **Only the independent mode, by request:** the pre-existing "stay shaded"
  behavior option applies to *every* shading end; #605 explicitly asked for a
  hold that is scoped to hot days detected by the independent temperature
  comparison. Requires `shading_temp_comparison_independent`; the validator
  warns when the hold is selected without it.
- **Hysteresis on the LOW side** (`shading_independent_temp -
  shading_forecast_temp_hysteresis`), opposite to `independent_temp_valid`'s
  start check (`+ hysteresis`), so the hold does not flap at the threshold.
- **Latching end triggers are accepted:** an end trigger suppressed by the
  hold never re-fires when the temperature later drops (no new FALSE→TRUE
  edge). The shading then ends via the scheduled close (which writes
  `shd: 0`), the 23:55 reset, or any later end trigger that fires on a fresh
  edge. This is the requested "shade the whole day" behavior — do not add a
  re-fire trigger without revisiting the orphan audit.
- **The forecast-load gate includes `t_shading_end`** (Bug Pattern T family):
  without it, `forecast_temp_raw` is `None` on end triggers and the hold's
  forecast branch could never apply. This also fixed forecast-based *end*
  conditions, which previously evaluated without data on end triggers.

---

### A Manual Override reset's drive gate is opt-in (default off), asymmetric to `recovery_mode` (#553/#668/#677, CCA 2026.08.22)

`auto_recover_after_manual_reset` gates only whether a live reset (timeout/fixed-time/position)
*drives* the cover; the state correction (`man` clearing) always happens once `override_expired`
(Invariant 7's documented exception), via `manual_reset_event` opening `recovery_catch_up`. This
looks like it duplicates `recovery_mode` (never/outage/always) and invites "just reuse that
setting" — do not. `recovery_mode` governs restart/outage catch-up specifically; an explicit live
reset is a different event class the same way `manual_reset_event` is already documented as
separate from it in `recovery.md`. Coupling the reset's drive to `recovery_mode` would resurface
exactly the naming confusion this decision exists to avoid (a restart-scoped setting silently
deciding an unrelated interaction), without even fixing the reported bug: BRANCH 10's pre-#669
code already drove to `effective_state` on every reset, unconditionally, with no `recovery_mode`
involved at all — the reported "cover opens/closes for no reason after reset" complaints were
never about staleness, they were about driving into a resting cascade value nothing scheduled.

**`recovery_catch_up` for a manual reset additionally requires `override_expired`** (CCA
2026.08.23 review finding): a manual change that falls inside the reset's own tolerance window
has not actually expired by the strict rule yet, so schedule re-derivation and any drive must
wait for a later run rather than race the timestamp. `man` clearing is unaffected by this — it
is gated on `override_expired` directly, not on `recovery_catch_up`, so it still fires the moment
the override genuinely expires. **BRANCH 10 (the numbered "Reset manual detection" branch) now
also requires `helper_state_manual`** (same finding): without it, a reset trigger firing with
`man == 0` (nothing active to reset — e.g. right after the 23:55 midnight reset had already
cleared it) fell through past `manual_reset_event`'s pre-dispatch claim and drove unconditionally,
bypassing the opt-in through the back door. With the gate added, BRANCH 10 is unreachable dead
code (every run it could match was already claimed and stopped upstream); it is kept as a
structural safety net rather than removed in the same change.

**The remaining, load-bearing asymmetry:** even with the opt-in on, a reset must still never
drive to `'opn'` when `not is_opening_scheduled and live_force == 'non'` — the Issue #553
resting-state class (a schedule-less instance's permanent `bas` init default, which requires no
write at all: `bas` starts at `'opn'`). `manual_reset_recovery_hold` checks this unconditionally
inside the opt-in branch; it is not itself a separate setting. The `live_force == 'non'` term
(CCA 2026.08.23 review finding) matters because `recovered_state` mirrors `live_force` first
(architecture.md): an `'opn'` produced by an active Force-Open target has a live owner and is
not the ownerless #553 default, so the guard must not hold it back — without this term, an
enabled reset could silently withhold a legitimate Force-Open drive. There is deliberately
**no** equivalent guard for `'cls'`, but the reasoning is narrower than "it can't happen" — be
precise about what it does and doesn't cover:

- `bas` can only ever become `'cls'` through a real write: an actual closing schedule firing,
  or live `privacy_active`. Unlike `'opn'`, there is no zero-write, permanently-wrong default —
  the #553 class genuinely cannot occur for `'cls'`.
- It *can* still go stale a different way: a schedule that fires once, gets disabled later
  (e.g. the user turns off closing entirely after using it), while `bas` stays parked at the
  last value it wrote. A reset with the opt-in on would then drive to a `'cls'` that is no
  longer backed by any live automation — the same surprise-movement complaint #553/#668/#677
  were about, just reached via a config change instead of an unconfigured default. This is
  documented as a known residual risk in the `auto_recover_after_manual_reset` input
  description rather than silently ignored.
- Closing this residual gap with a symmetric `is_closing_scheduled` gate was tried once and
  reverted for unrelated, real regressions (see the #677 discussion history) — that attempt
  introduced a `bas: 'cls'` write path, not this reset's read-only reconciliation, but it shows
  the two legitimate `'cls'` sources (schedule *and* `privacy_active`) make a correct live gate
  meaningfully harder to get right than the single-source `is_opening_scheduled` case. Do not
  re-attempt it casually "for consistency" — if you do, both sources must be covered and the
  #677 regression must not reappear.
