# CCA Design Decisions (intentional deviations)

Every entry here looks like an inconsistency but is deliberate. Read this before
"harmonizing", unifying, or cleaning up anything that seems asymmetric —
especially resident/manual-override gates, pending preserve/discard asymmetries,
and invalid-sensor-state handling. Restart/outage handling has its own file:
`recovery.md`.

---

## Design Decisions (intentional deviations from the general patterns)

### Resident handler bypasses `helper_state_manual` / `override_flags.*`

The resident sensor handler (`resident_leaving` / `resident_arriving`) does **not** check `not (helper_state_manual and override_flags.X)` in any of its branches. All other handlers (Open, Close, Shading-Start, Shading-End, Contact, Manual) do.

**Rationale:** Presence transitions are treated as a hard reset of any earlier manual intent — when the resident leaves or arrives, the cover should follow the new presence-derived target regardless of an active manual override. The `ignore_*_after_manual` configuration only governs scheduled / environment-driven triggers, not presence transitions.

This is intentional. Do not "harmonize" by adding the override gate to the resident handler.

### Opening handler preserves shading-start pending **only while still warranted**; closing handler discards it

When the opening trigger fires while a shading-start pending is active (`pnd == 'beg'`) **and shading is still warranted**, the opening handler **preserves** `pnd`, `ts.due`, and `ts.arm` and defers to the `t_shading_start_execution` trigger (which fires 1 second later at `ts.due = window_start + 1`). "Still warranted" is the variable `shading_start_warranted` = `shading_start_conditions_met or (independent-temperature path active)` — it mirrors the execution gate exactly.

When the closing trigger fires while a shading-start pending is active, the closing branches **discard** `pnd`/`ts.due`/`ts.arm` by setting them to `non`/`0`/`0`.

**Rationale:** At closing time, a shading-start intent from earlier in the day is no longer relevant — the cover is about to close regardless. Driving it to the shading position only to immediately close it would be wrong. At opening time, the intent is still valid **provided the conditions are still met** — the execution trigger should handle the drive.

**Stale-pending guard (Issue #514):** A pending can be armed before the opening time (brightness briefly exceeds the threshold) and then go stale when the conditions fall back below the threshold *before* the opening time. The `t_shading_start_execution` trigger only ever drives into the shading position or retries/aborts — it **never opens the cover**. So if the opening handler deferred unconditionally, a stale pending would leave the cover stuck closed all morning. The "Opening skipped: Shading start pending" branch therefore gates on `shading_start_warranted`; when the pending is stale the branch is skipped, execution falls through to "Normal opening", which drives the cover open and clears `pnd`/`ts.due`/`ts.arm`.

This asymmetry is intentional. Do not "harmonize" the closing handler to preserve pending — it must discard it. Do not remove the `shading_start_warranted` gate from the opening "skip" branch — that reintroduces #514.

### Midnight reset (BRANCH 11) sets `man: 0` without driving

The "Reset shading status that is no longer required" branch writes `man: 0` even though it does not drive the cover. This is an intentional exception to Invariant 7.

**Rationale:** Midnight is the natural reset point for the daily automation cycle. Clearing `man` here ensures stale manual overrides do not block the next day's automation. In practice the branch only fires when shading was active (or pending) at midnight — and in those scenarios the user typically did not override manually, so `man` is already `0`. The explicit reset is a defensive safeguard and is documented as a deliberate exception.

### The force pause is part of every drive gate (CCA 2026.07.13 V6)

`is_paused` used to be checked only inside `cover_move_action` / `tilt_move_action` — the *movement* was suppressed, but everything keyed to the *drive decision* still ran: the user's before/after actions in `drive_with_actions` fired ("cover is opening" notifications with no movement), and the `man:` reset followed `will_drive` (Invariant 7), so a paused run cleared a manual override although nothing moved.

The pause is therefore part of **every** drive gate: all five `state_gates`, every branch-local `will_drive`, and the inline `run:`/`if:` gates of the force handlers and the shading-end drive. `&drive_with_actions` additionally opens with a `not is_paused` condition guard (same mechanic as `cover_move_action`: a false condition only stops that grouped sequence; the `*helper_update` after it still runs — Invariant 2 intact). The inner `is_paused` conditions of the move actions stay as defense in depth.

Semantics: a paused run **records** its state transition (helper write, `bas`/`shd`/`win`/`frc` all updated — that is what makes the pause-resume instant) but does not drive, does not run drive actions, and does not touch `man`. When the pause ends, `t_force_pause_disabled` (or, after an outage of the pause entity, its `t_recovery` trigger) drives the cover to `effective_state` — that handler's own `will_drive` is `not is_paused`, guarding the queued-run race where the pause was re-enabled before the resume run executed.

**Since CCA 2026.07.20 the actuation-point checks are live reads.** The inner conditions of
`cover_move_action` / `tilt_move_action` and the opening guard of `drive_with_actions` no
longer read the `is_paused` variable (frozen when the variables step rendered) but
`states(force_pause)` directly — and the same condition re-checks the `instance_active`
gate. A pause enabled, or a hand-over performed, while a run sits in its pre-drive delay
(up to minutes) must still stop the movement: the branch-level `will_drive` was computed
before the delay and cannot see it. The branch-level gates keep using the `is_paused`
variable — the decision and the actuation guard are different layers. Known corner,
accepted: the helper write of such a run was computed with `will_drive` true, so `man: 0`
can land although the movement was suppressed at the last moment — recomputing the whole
transition after the delay would break the plan-then-apply architecture for a rare window.

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

**Why the trigger, not a global condition:** A global `condition` still lets the automation *start* — HA records a (stopped) trace for every triggered run. Filtering at the trigger means the automation never runs at all → no trace, no queue entry, no logbook noise. `not_to`/`not_from` require HA ≥ 2023.4; the blueprint's `min_version` (2024.10.0) covers this.

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
shading tilt": only while `shd == 1`, gated on force/resident/window/manual.
It re-applies the shading **tilt** after the position move (a position drive
physically disturbs the slat angle on tilt covers) and clears `man` only when
it actually drives (`not in_shading_position` in the if-guard, Invariants 1+7).
A depth change is **not** a shading start: `shd`, `ts.shd`, and the pending
keys stay untouched, so `prevent_shading_multiple_times` is unaffected. No
helper field stores the active depth (same rationale as #558 — the helper
holds logical state; the brief `in_shading_position` volatility after a switch
is accepted and healed by the re-drive trigger).

