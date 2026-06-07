# CLAUDE.md — Cover Control Automation (CCA) Blueprint

## Overview

`blueprints/automation/cover_control_automation.yaml` is a Home Assistant automation blueprint (Jinja2 + YAML). It controls roller blinds/shutters based on time, sun position, window contact sensors, and presence detection.

---

## Helper JSON Schema (v6)

State is persisted as a JSON string in an `input_text` helper:

```json
{"bas":"opn","shd":1,"pnd":"non","win":"opn","frc":"non","res":1,"man":0,
 "ts":{"opn":0,"cls":0,"shd":0,"due":0,"arm":0,"man":0},
 "v":6,"t":0}
```

| Field | Values | Meaning |
|-------|--------|---------|
| `bas` | `opn`/`cls` | Base state (time-based: open / closed) |
| `shd` | `1`/`0` | Shading active |
| `pnd` | `non`/`beg`/`end` | Shading pending phase (none / start-armed / end-armed) |
| `win` | `cls`/`tlt`/`opn` | Window state (closed / tilted / open) |
| `frc` | `non`/`opn`/`cls`/`shd`/`vnt` | Active force function |
| `res` | `1`/`0` | Resident present |
| `man` | `1`/`0` | Manual override active |
| `ts.opn` | Unix timestamp | Last time base state switched to open |
| `ts.cls` | Unix timestamp | Last time base state switched to closed |
| `ts.shd` | Unix timestamp | Last time shading state changed (0↔1) |
| `ts.due` | Unix timestamp | Fire time of armed pending (used together with `pnd`; `0` when `pnd == 'non'`) |
| `ts.arm` | Unix timestamp | First-arming anchor of current retry sequence (preserved across retries; `0` when `pnd == 'non'`) |
| `ts.man` | Unix timestamp | Last manual override event |

---

## Priority Cascade (`effective_state`)

```
1. FORCE    → frc != "non"                                       → Force position
2. LOCKOUT  → win == "opn"                                       → Open position
3. BASE=OPN → bas == "opn" AND no privacy/shading/restriction    → Open position
4. VENT     → win == "tlt" AND base would close/shade/privacy    → Ventilation position
5. PRIVACY  → resident && closing                                → Close position
6. SHADING  → shd == 1 && allow_shade                            → Shading position
7. BASE=CLS → bas                                                → Close position
```

The variable `effective_state` returns the currently active state from this cascade (`lock`, `opn`, `vnt`, `cls`, `shd`).

**Rationale for BASE=OPN before VENT:** A tilted window signals ventilation intent — and a fully open cover provides maximum airflow. So when the time schedule says "open" (`bas=opn`) and nothing else lowers the cover, opening wins over the tilted-vent floor. VENT is a *floor* only when the cover would otherwise go below ventilation position (close, shading, privacy-close, or base=opn with `allow_open=false`).

Implementation: `effective_state` first computes `base_target` (the cover state without VENT consideration: `cls`, `shd`, or `opn`), then applies VENT only when `win == 'tlt'` and `base_target != 'opn'`.

---

## Architectural Invariants — ALWAYS FOLLOW

### ⚠️ Invariant 1: NEVER put position checks in branch conditions

**Wrong:**
```yaml
- conditions:
    - "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}"
    - "{{ effective_state != 'lock' or not in_open_position }}"  # ← NOT HERE!
  sequence:
    - if: "{{ force_allows_ventilate }}"
      then: ...drive...
```

**Correct:**
```yaml
- conditions:
    - "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}"
    # No position check here!
  sequence:
    - if: "{{ force_allows_ventilate and (effective_state != 'lock' or not in_open_position) }}"
      then: ...drive...
    - *helper_update  # Helper is ALWAYS updated
```

**Why:** When the position check is in the branch conditions, the branch is not selected if the cover is already at the target position. This causes the logic to fall through to the next branch (e.g. shading), breaking the priority cascade.

**Rule:** Every branch that has priority must always be consumed (even if no drive is needed). The helper update must always happen.

### ⚠️ Invariant 2: Always update the helper

`*helper_update` must be at the end of **every** branch sequence — even when no cover drive occurs. This is the only way to correctly persist the `res` status (and other fields).

### ⚠️ Invariant 3: Realtime sensor vs. helper state

- `state_resident` / sensor checks (`states(contact_window_opened)`) → **Realtime** (current sensor value)
- `effective_state` → **Realtime** for `win` (reads live contact sensors; falls back to `helper_json.win` only when no sensors are configured)
- `helper_state_window` / `helper_json.win` → **Helper** (last persisted state)

`effective_state` uses the **live sensor** for the window state (`win`), so it always reflects the physical window position — even when the helper hasn't been updated yet (e.g. during the contact handler before `*helper_update` runs).

In the `resident_arriving`/`resident_leaving` handler: always check realtime sensors, as the helper still holds the old state.

**Specifically:** `helper_json.win` (= `helper_state_window`) is only updated when the contact handler actually moves the cover. If the cover was already at the target position when the window opened, `win` stays `cls` in the helper — even though the window is physically open. Therefore, always use `states(contact_window_opened)` in the `resident_arriving` handler, not `helper_state_window`.

### ⚠️ Invariant 4: `resident_flags` reads the live sensor — no stale-state problem

`resident_flags.allow_shade/allow_ventilate/allow_open` are based on `state_resident` (line ~3083), which reads the **live** sensor via `states(resident_sensor)` — **not** from `helper_json.res`.

In the `resident_leaving` context the sensor has already changed to `off`, so `state_resident == false` and all `resident_flags.allow_*` evaluate to `true` (because `not state_resident == true`). No special handling with `new_resident_status` is needed.

**Key distinction:**
- `state_resident` → **live sensor** (`states(resident_sensor)`) → always current
- `helper_json.res` → **persisted helper** → stale until `*helper_update` runs

`resident_flags.*` uses `state_resident`, so it automatically reflects the new sensor state at trigger time.

### ⚠️ Invariant 5: `opened` always takes priority over `tilted`

In **every** branch/handler that handles both `contact_window_opened` and `contact_window_tilted`, the `tilted` branch must explicitly check that `opened` is **not** active:

```yaml
# Tilted branch must always contain this condition:
- "{{ not (contact_window_opened != [] and states(contact_window_opened) in ['true', 'on']) }}"
```

Missing priority checks between opened/tilted cause the tilted branch to fire when both sensors are active, moving the cover to the ventilation position (e.g. 50%) instead of the open position (100%).

**Applies to all handlers:** `resident_leaving`, `resident_arriving`, `force_disabled`, `contact_sensor_changed`, shading start/end.

### ⚠️ Invariant 6: Lockout works regardless of `resident_allow_ventilation`

Lockout protection (window fully open → cover to open position) is a **safety feature** and must not depend on `resident_flags.allow_ventilate`.

**Wrong:** Gating the entire contact handler with `resident_flags.allow_ventilate` → lockout disabled when `resident_allow_ventilation` is not configured.

**Correct:** Check `resident_flags.allow_ventilate` only in the tilted sub-branch. The opened branch (lockout) must always run.

### ⚠️ Invariant 7: `man: 0` only when actually driving the cover

The `man` flag (manual override) may only be set to `0` when the automation actually moves the cover to a defined position. Do **not** set `man: 0` in:

- Pending timers (shading start/end pending)
- Lockout blocks without a drive (cover already at target position)
- Pure state changes without movement
- Win-only helper updates

**Wrong:** `man: 0` in `update_values` for every block that calls `*helper_update`.
**Correct:** `man: 0` only in `update_values` for blocks that also execute `*cover_move_action`.

### ⚠️ Invariant 8: Timestamp invariants

**ts.shd (shading timestamp):**
- `ts.shd` may only be set when `shd` actually changes (guard in `helper_update`: only when `new_shd != current.shd`)
- In the SHADED branch of the `resident_leaving` handler: `shd` was already `1` (precondition) → do **not** set `ts.shd` to `now`, preserve the original activation timestamp

**pnd / ts.due / ts.arm (pending phase + timestamps):**
- The top-level `pnd` enum encodes which phase is pending: `'non'` (idle), `'beg'` (start armed), `'end'` (end armed). Only one value at a time is representable — Invariant 11 is enforced by the schema.
- `ts.due` is the **fire time** of the armed pending (when the execution trigger should fire). Re-armed on every retry to `now + waiting_time`.
- `ts.arm` is the **retry anchor**: when the current pending sequence first armed. Set once at the start of the sequence, **preserved across all retries**, read by `shading_start_max_duration` and `shading_end_max_duration` checks via `helper_ts_pending_arm`.
- These three keys must not be reset in win-only helper updates (when only `win` is updated without a drive).
- `pnd: 'non'` always implies `ts.due == 0` and `ts.arm == 0`. Terminal branches must set all three together.
- Retry-continuation branches must set `pnd: 'beg'` (or `'end'`) and the new `ts.due`, but **not** `ts.arm` — `helper_update` preserves the existing value automatically when a key is omitted.
- Terminal branches that clear pending:
  - Start: Drive, Lockout-skip, Save-for-future, both Abort branches
  - End: Tilt-only, Lockout, Ventilation, Move-cover (both then/else), Stop retry, stale-pending cleanup (#395)
  - Midnight reset (BRANCH 11, "Reset shading status")
  - Incidental clears in non-shading branches (force, manual) — also clear all three for hygiene.
- **Contact handler branches must NOT reset `pnd`/`ts.due`/`ts.arm`.** Window open/close events are orthogonal to shading pending state. Omit these keys from `update_values` so `helper_update` preserves the existing values (#484).

### ⚠️ Invariant 11: Mutual exclusivity of shading-start and shading-end pending

`pnd` is a single enum field, so two phases cannot be pending simultaneously by construction. With misconfigured conditions (no hysteresis between start and end thresholds), the only failure mode is ping-pong (start fires → end fires → start fires → …), not double-pending.

**Guard:** Both pending-establishment branches gate on the opposite pending state to prevent ping-pong:

- "Shading detected" (start) requires `not helper_state_pending_end`
- "Shading end detected" requires `not helper_state_pending_start`

### ⚠️ Invariant 9: `ts_now` must be evaluated at the point of use

`ts_now` (`as_timestamp(now()) | round(0)`) must **never** be defined as a single global variable at the top of the automation action. It must be set locally — directly in the block where the current timestamp is needed.

**Why:** The automation can execute `delay:` steps or other time-consuming actions before reaching a block that writes to the helper. A global `ts_now` set once at the start would capture the trigger time, not the actual execution time — producing incorrect timestamps in the helper.

**Wrong:**
```yaml
variables:
  ts_now: "{{ as_timestamp(now()) | round(0) }}"  # set once, stale after any delay!
# ... delay, other actions ...
# ts_now is now potentially minutes behind actual time
```

**Correct:**
```jinja2
{# Inside helper_update anchor or any block that needs the current time: #}
{% set ts_now = as_timestamp(now()) | round(0) %}
{# Evaluated fresh at this exact point in execution #}
```

### ⚠️ Invariant 10: `trigger_variables:` accepts only limited templates

`trigger_variables:` is evaluated at trigger time in a **limited template context**. The functions `states()`, `is_state()`, and `state_attr()` are **not available** here. Only static values and trigger-derived properties (e.g. `trigger.to_state.state`) are safe.

Move any variable that reads entity state into the `variables:` (action scope) block. See "Home Assistant Limited Templates" for the full reference.

**Wrong:**
```yaml
trigger_variables:
  is_paused: "{{ states(force_pause) in ['on', 'true'] }}"  # states() unavailable!
```

**Correct:**
```yaml
trigger_variables:
  force_pause: !input force_pause  # static !input reference is fine

variables:
  is_paused: "{{ force_pause != [] and states(force_pause) in ['on', 'true'] }}"
```

### ⚠️ Invariant 12: `enable_logbook` and `helper_update`

The `helper_update` anchor wraps two steps in a `choose: [] default: [...]`
group: (a) `input_text.set_value` that persists the helper JSON, and (b) a
conditional `logbook.log` gated by `enable_logbook`. The logbook message
dumps `trigger.id`, `effective_state`, position, sensor states, and the raw
`update_values` JSON — it deliberately does **not** derive a human-readable
reason. The combination of `trigger.id` (which is sprechend, e.g.
`t_open_1`, `t_shading_start_pending_2`) and the `update_values` diff is
sufficient for retrospective debugging.

**Optional `log_extra` parameter:** branches that have additional context
(e.g. shading start/end pending and retry: time-window, elapsed time, block
reason, next retry interval) may set a free-form `log_extra: "..."` string
in their local `variables:` block. The template prints it as one extra line
when defined. Do **not** add `log_extra` to every branch — only where the
bare `trigger.id + update_values` is genuinely insufficient for debugging.

**Rule:** Do not reintroduce a reason-inference table into the template.
`trigger.id` is the source of truth for "which path ran". Adding new fields
to `update_values` requires no logbook changes — they are dumped automatically
via `to_json`.

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

### Triggers from/to an invalid sensor state are deliberately ignored

The contact handler ("Contact sensor state changed") gates on **both** the previous and the new trigger state being valid:

```yaml
- "{{ trigger.from_state.state not in invalid_states }}"
- "{{ trigger.to_state.state not in invalid_states }}"
```

(`invalid_states` = `''`, `unavailable`, `unknown`, `none`, `None`.) The global condition additionally rejects any trigger whose `to_state` is invalid.

**Rationale:** A state transition that touches an invalid state is not a real, trustworthy physical event — it is a sensor dropout (connectivity loss, battery, restart) or a recovery from one. Acting on such transitions would move covers based on noise. CCA therefore ignores transitions **into** an invalid state (`on → unavailable`) **and out of** one (`unavailable → off`).

**Known consequence (Issue #505):** If a window contact sensor goes `on → unavailable` (instead of cleanly `on → off`) while CCA holds the cover in the lockout/open position (status `lock`), and the sensor later recovers `unavailable → off`, the recovery transition is ignored. `win` stays `opn` in the helper and a remembered shading (`shd=1`) is not applied until another trigger updates the window state — the cover can stay stuck in `lock`.

**This is intentional, not a bug.** The root cause is an unstable contact sensor reporting `unavailable`. The fix belongs at the sensor (battery / radio range), not in the blueprint. Do **not** remove the `from_state` guard to "process recovery transitions" — that would make CCA act on sensor dropouts. Do not "harmonize" this away.

---

## Known Bug Patterns (with cause and fix)

### Bug Pattern A: Branch selection blocked by position check

**Symptom:** When cover is already at target position X, the next trigger incorrectly executes a lower-priority branch (e.g. shading instead of lockout).

**Cause:** `effective_state != 'X' or not in_X_position` in branch conditions → when position=X and effective_state=X the condition is `FALSE`, branch is skipped.

**Affected locations (last found):**
- Line ~5729: `resident_leaving` → LOCKOUT branch (fixed)
- Line ~5758: `resident_leaving` → VENT branch (fixed)
- `resident_arriving` with `resident_allow_ventilation` enabled (fixed)

**Fix:** Move position check into the `if:` guard:
```yaml
if: "{{ force_allows_ventilate and (effective_state != 'lock' or not in_open_position) }}"
```

### Bug Pattern B: ~~`resident_flags.allow_shade/allow_ventilate` stale in `resident_leaving`~~ (NOT A BUG)

**Previous assumption:** `resident_flags.allow_shade` reads stale state from `helper_json.res`.

**Actual behavior:** `resident_flags.*` is based on `state_resident` (line ~3083), which reads the **live sensor** via `states(resident_sensor)`. In the `resident_leaving` context the sensor is already `off`, so `state_resident == false` → all `allow_*` flags are `true`. No stale-state problem exists. See Invariant 4.

### Bug Pattern C: Lockout blocked by `resident_allow_ventilation` gate

**Symptom:** When `resident_allow_ventilation` is not configured, lockout protection stops working.

**Cause:** `resident_flags.allow_ventilate` as a top-level condition in the contact handler gates the entire ventilation handler including lockout.

**Fix:** Check `resident_flags.allow_ventilate` only in the tilted sub-branch, not as a global condition of the contact handler.

### Bug Pattern D: Missing `not contact_window_opened` check in tilted branch

**Symptom:** When both `contact_window_opened` and `contact_window_tilted` are active, cover moves to ventilation position (50%) instead of open position (100%).

**Cause:** The tilted branch does not check whether opened is also active. Since opened and tilted branches appear to have the same priority, tilted can match first.

**Fix:** Add to **every** tilted branch:
```yaml
- "{{ not (contact_window_opened != [] and states(contact_window_opened) in ['true', 'on']) }}"
```

### Bug Pattern E: `man: 0` in non-movement blocks

**Symptom:** Manual override is unexpectedly cleared even though no cover drive occurred.

**Cause:** `man: 0` in `update_values` for every block that calls `*helper_update`, even when no drive happens.

**Fix:** Remove `man: 0` from: pending timers, lockout-only blocks, pure state updates.

### Bug Pattern F: Phantom timestamp updates

**Symptom:** `ts.shd` shows incorrect timestamp; shading pending state is unexpectedly reset.

**Cause A:** `ts.shd: "now"` is set in sequences that do not change `shd` from 0→1.
**Cause B:** `pnd` / `ts.due` / `ts.arm` are reset in win-only helper updates.

**Fix:** Guard in `helper_update` — only apply `ts.shd` when `new_shd != current.shd`. Do not reset `pnd`/`ts.due`/`ts.arm` in win-only updates.

### Bug Pattern I: Shading-start retry aborts on fresh day (Issue #416)

**Symptom:** First retry attempt of the day aborts immediately when the start conditions are blocked by additional conditions or manual override; the `shading_start_max_duration` window is effectively zero on a fresh helper.

**Cause:** The duration check used `helper_ts_shade` (= `ts.shd`) as anchor. Pending establishment does not transition `shd`, so the Invariant-8 guard preserves `ts.shd` at its previous value (yesterday's shading-end or `0`). `now() - ts.shd` is therefore much larger than `shading_start_max_duration` → check fails → retry aborts.

**Fix:** Dedicated `ts.arm` field that records the retry-sequence start. Set in "Shading detected" (start) and "Shading end detected" (end), preserved across continues, cleared in all terminal branches of both sequences. Duration checks for both `shading_start_max_duration` and `shading_end_max_duration` now use `helper_ts_pending_arm`. The same field serves both directions because the sequences are mutually exclusive (Invariant 11, structurally enforced by `pnd`).

### Bug Pattern G: `helper_state_window` instead of realtime sensor in `resident_arriving` handler

**Symptom:** When cover was already at open position when the window was opened, `resident_arriving` does not recognize the lockout state → cover incorrectly closes.

**Cause:** `helper_json.win` is only updated when a drive occurs. If the cover was already open, `win` stays `cls` in the helper.

**Fix:** Always use realtime sensors in the `resident_arriving` handler:
```yaml
# Wrong: helper_state_window != 'opn'
# Correct:
- "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}"
```

### Bug Pattern H: Base state not updated when closing trigger fires with tilted window

**Symptom:** After the closing trigger fires with the window tilted, the cover correctly stays at the ventilation position — but `bas` remains `opn` instead of being updated to `cls`. The next day, `prevent_multiple_times` incorrectly suppresses the closing trigger because `ts.cls` was never set.

**Cause:** The tilted-closing branch ("Window tilted. No lockout. Move to ventilation position instead of closing") omitted `bas: 'cls'` and `ts.cls: 'now'` from its `update_values`. The branch correctly drives to the ventilation position but forgot to record the base state change.

**Rule:** The CLOSE handler always updates the base state (`bas: 'cls'`, `ts.cls: 'now'`), regardless of whether the cover physically moves. The base state reflects the time schedule, not the physical position.

**Fix:** Add to the tilted-closing branch `update_values`:
```yaml
bas: 'cls'
ts:
  cls: 'now'
```

### Bug Pattern J: Contact handler lowers cover to ventilation when base state is open (Issue #460)

**Symptom:** When `bas == 'opn'` (opening time already fired) and the window transitions from fully open to tilted, the cover incorrectly lowers from 100% (open) to 50% (ventilation).

**Cause:** The tilted-drive branch's OR condition at the `helper_state_window == 'opn' and current_above_ventilate` alternative fires unconditionally when the window goes from open → tilted, regardless of whether `base_target == 'opn'`. Per the priority cascade, VENT is a floor — it should NOT lower a cover when `base_target == 'opn'`.

**Root fix:** `effective_state` was changed to derive `win` from **live contact sensors** instead of the stale `h.win` helper field. When sensors are configured, the live sensor value takes priority; when no sensors are configured, it falls back to `h.win`. This means `effective_state` now correctly returns `'opn'` (not `'lock'`) when the window transitions from open → tilted and `bas == 'opn'`. The tilted-drive branch guards with `{{ effective_state != 'opn' }}`, and the no-drive branch catches `{{ effective_state == 'opn' }}`.

### Bug Pattern K: `regex_search('"shd"\s*:\s*1')` matches `ts.shd` timestamp (Issue #467)

**Symptom:** All `t_shading_start_pending_*` triggers are blocked by condition/3 even though `shd == 0` (shading inactive). The automation stops despite valid shading conditions.

**Cause:** The regex `"shd"\s*:\s*1` is intended to check if the top-level `shd` field is `1`, but the helper JSON contains a nested `ts.shd` timestamp (e.g. `"shd":1779701945`) whose value starts with `1`. The regex matches this nested timestamp, making the condition think shading is already active.

**Fix:** Change all 6 occurrences of the regex to `"shd"\s*:\s*1\s*[,}]` — requiring a comma or closing brace after the `1` ensures it matches only the top-level `"shd":1,` and not a multi-digit timestamp value.

### Bug Pattern L: Shading pending arms before time window → execution aborts immediately

**Symptom:** Shading conditions are met shortly before `time_up_early_today` (e.g. 06:55 with window at 07:00). Pending arms successfully, but execution aborts with `"Shading Start aborted: Timeout or invalid"` despite having thousands of seconds of `shading_start_max_duration` remaining.

**Cause:** The outer if (line ~5196) allows pending triggers to bypass `is_shading_allowed_window` (via `trigger.id` match on `t_shading_start_pending`), but requires it for execution triggers. When `ts.due` (= `now + waitingtime`) resolves to a time before the window opens, the execution trigger fires too early, fails the outer if, and the retry also requires `is_shading_allowed_window` → abort.

**Fix:** In the pending arming branch, compute `ts.due` as `max(now + waitingtime, window_start_time)`. When the window is already open, this equals `now + waitingtime` (unchanged). When arming before the window, execution is deferred to the window start. No retry logic changes needed — the execution fires within the window and the normal flow handles it.

### Bug Pattern M: Combined sun-position trigger swallows independent elevation/azimuth end (Issue #483)

**Symptom:** Shading never ends even though the sun elevation drops below the configured end threshold. The trigger fires earlier (when azimuth goes out of range) but the end conditions are not met. When elevation later drops below threshold, no trigger fires.

**Cause:** `t_shading_end_pending_5` combined azimuth and elevation checks in a single template trigger using OR logic. HA template triggers fire on FALSE→TRUE transitions only. When azimuth goes out of range first, the template becomes TRUE and the trigger fires. But `shading_end_conditions_met` is FALSE (user only configured elevation as end condition). When elevation later drops below threshold, the template is already TRUE (from azimuth) → no re-fire → shading end never triggers.

**Fix:** Split `t_shading_end_pending_5` into two independent triggers:
- `t_shading_end_pending_5`: azimuth only (outside configured range)
- `t_shading_end_pending_7`: elevation only (outside configured range)

Each condition gets its own independent FALSE→TRUE transition. Update condition regex `[1-6]` → `[1-7]` and `is_shading_end_immediate_by_sun_position` check to match both trigger IDs.

### Bug Pattern N: Contact handler destroys active shading pending phase (Issue #484)

**Symptom:** Briefly opening and closing a door/window during a shading-start (or shading-end) pending phase prevents shading from ever executing. The pending timer (`ts.due`) is reset to `0`, and the sun-position trigger doesn't re-fire because the azimuth condition hasn't changed (no FALSE→TRUE transition).

**Cause A:** All "Window closed" sub-branches (`Return to shading`, `Return to open`, `Return to close`) and the "Window opened - Full ventilation (lockout)" branch unconditionally set `pnd: 'non'`, `ts.due: 0`, `ts.arm: 0` in their `update_values`.

**Cause B:** The "was ventilating before" OR condition includes `in_open_position`, which matches whenever the cover happens to be at open position — even when CCA was never in ventilation mode (`win == 'cls'` the entire time). This causes spurious "Window closed" branch matches.

**Fix A:** Remove `pnd`/`ts.due`/`ts.arm` from `update_values` in all contact handler branches. The `helper_update` anchor preserves existing values when keys are omitted.

**Fix B:** Remove `in_open_position` from the "was ventilating before" OR condition in all three "Window closed" branches. The dedicated "No drive, sync" branches already ensure `helper_state_window` is correctly updated when the window opens/tilts.

### Bug Pattern O: Contact "window closed" handler closes on bare resident presence

**Symptom:** With `bas == 'opn'`, no shading, no force, and a resident present, closing the window lowers the cover from open to close — even though `effective_state == 'opn'` and the user never configured privacy-closing.

**Cause:** The "Window closed" return branches used raw `resident_now` as a privacy proxy. "Return to open" required `helper_state_base == 'opn' and not resident_now`, and "Return to close" fired on `helper_state_base == 'cls' or resident_now`. Any resident presence therefore forced a close, diverging from `effective_state`, whose `privacy_active` requires `'resident_closing_enabled' in resident_config` (and whose `allow_open` gate closes only when `resident_allow_opening` is unset).

**Fix:** Introduce `resident_blocks_open` in the post-delay contact-handler variables:
```jinja2
resident_now and (resident_flags.closing_trigger or 'resident_allow_opening' not in resident_config)
```
Use `not resident_blocks_open` in "Return to open" and `resident_blocks_open` in "Return to close". This mirrors `effective_state`'s privacy + allow_open gates exactly, so the contact handler agrees with the cascade.

**Rule:** Contact "window closed" return branches must resolve open-vs-close from the same gates as `effective_state` (privacy + allow_open), never from bare presence.

---

### Bug Pattern P: Late opening trigger overwrites `ts.opn` and redundantly drives (Issue #495)

**Symptom:** Cover opens at the early time (e.g. 07:00, sun condition met) → `ts.opn = 07:00`, `bas = 'opn'`. When the late opening time fires (e.g. 08:00, `is_time_up_late`), the cover is already open but: `ts.opn` is overwritten with 08:00, the cover is redundantly re-driven (`cover_move_action` + `auto_up_action` scripts re-run), and `man` is cleared to `0`.

**Cause:** The "Already in open position" branch gated itself with an `or` in its **conditions**: it only fired when `helper_state_base != 'opn'` **OR** `now().day != ts.opn day`. With `bas == 'opn'` and same day, both are false → the branch is skipped → execution falls through to "Normal opening", which drives and sets `ts.opn: 'now'`, `man: 0`. This is the same class as Bug Pattern A (branch fall-through caused by a check in the conditions) and Bug Pattern F (phantom `ts.opn` update with no real base transition).

**Fix:** Remove the `or`-gate from the branch **conditions** so the branch always fires when `effective_state == 'opn' and in_open_position` (and not shaded/pending). Move the refresh decision **inside** the sequence as `if/then/else`:
```yaml
- if: "{{ helper_state_base != 'opn' or now().day != helper_ts_open | timestamp_custom('%-d', true) | int }}"
  then:   # real base transition or new day → refresh ts.opn
    - variables: {update_values: {bas: 'opn', ts: {opn: 'now'}}}
  else:   # already open, same day → preserve ts.opn
    - variables: {update_values: {bas: 'opn'}}
- *helper_update
```
No drive, no `man: 0` in the already-open case. `helper_update` preserves the existing `ts.opn` when the key is omitted.

**Do NOT guard `ts.opn` globally in `helper_update`** (analogous to the `ts.shd` guard): that would break the legitimate daily `ts.opn` refresh for `prevent_multiple_times` (on a new day `bas` is still `'opn'` from yesterday — no transition, but `ts.opn` MUST be refreshed). The refresh decision is branch-local, not a helper-update invariant.

**Rule:** A branch that "consumes" an already-reached state must always be **selected**; whether it refreshes a timestamp / drives the cover is decided **inside** the sequence (`if/then/else`), never via the branch conditions. Open-state timestamp refresh happens only on a real `bas` transition or a day change.

**Open follow-up:** The CLOSE handler may have the symmetric pattern for `ts.cls`, but note Bug Pattern H — CLOSE must always record the base-state change on a real schedule transition. Any fix there must preserve that, only suppressing the no-op same-day re-fire.

---

### Bug Pattern Q: Hardware position drift triggers false manual override

**Symptom:** Some minutes after the automation drives the cover (e.g. to the shading position 58 %), the cover reports a tiny position drift on its own (58 % → 59 %, stable ≥ the trigger's `for: 60s`). `t_manual_position` fires *outside* the drive-settle window, the "Manual: …" handler sets `man: 1`. With `ignore_shading_after_manual` active, the shading-end branches (gated by `not (helper_state_manual and override_flags.shading)`) are then blocked → the cover stays in the shading position even after the sun leaves the facade, until `reset_override_timeout` clears the override.

**Cause:** The manual-detection gate in "Checking for manual position changes" only required `trigger.from_state ... != trigger.to_state ...` — **any** position change after the `now > helper_json.t + drive_time + 60` settle window counted as manual. There was no dead-band, so a ±1 % hardware/integration jitter (even one that keeps the cover *within* `position_tolerance` of where CCA put it, i.e. `in_shading_position` still `True`) was treated as a manual intervention. The trigger's own `for: 60s` confirms the drift is stable, so a transient filter does not help.

**Fix:** Replace the `!=` detection with a dead-band against `position_tolerance` for all three position sources (`custom_sensor` → state value, `current_position_attr`, `position_attr`):
```yaml
- "{{ ((trigger.to_state.attributes.current_position | float(0)) - (trigger.from_state.attributes.current_position | float(0))) | abs > position_tolerance }}"
```
A change only counts as manual when its magnitude *exceeds* `position_tolerance`. With `position_tolerance = 0` the old behaviour (react to every change) is restored. The tilt-detection branch is intentionally left unchanged (no tilt tolerance exists).

**Note — not solved by raising `position_tolerance` alone:** before this fix the detection ignored the tolerance entirely (`!=` only). The tolerance governed *which* branch was chosen (`in_shading_position`), not *whether* manual was detected. The dead-band ties the two together.

### Bug Pattern R: Stale shading-start pending leaves cover stuck closed at opening time (Issue #514)

**Symptom:** Brightness briefly exceeds the shading threshold *before* the opening time → shading-start pending arms (`pnd: 'beg'`, `ts.due` deferred to `window_start + 1` per Bug Pattern L). Brightness then falls back below the threshold, still before the opening time. At the opening time the cover stays closed; the trace shows `"Opening skipped: Shading start pending"`. The cover never opens that morning.

**Cause:** The opening handler's "Opening skipped: Shading start pending" branch gated only on `helper_state_pending_start`, so it deferred to `t_shading_start_execution` unconditionally. But the execution trigger only ever drives into the shading position or retries/aborts — it **never opens the cover**. With the conditions no longer met, execution loops in "Continue waiting" (until `shading_start_max_duration` from `ts.arm`) and then aborts — the cover is never opened, because the opening intent was already consumed (skipped) at the opening trigger.

**Fix:** Add `shading_start_warranted` (new variable, defined next to `shading_start_conditions_met`) to the "Opening skipped: Shading start pending" branch conditions. It mirrors the execution gate: `shading_start_conditions_met or (independent-temperature path active)`. When the pending is stale (`shading_start_warranted == false`), the branch is skipped and execution falls through to "Normal opening", which drives the cover open and clears `pnd`/`ts.due`/`ts.arm`. When still warranted, the defer behavior is unchanged. See the design decision "Opening handler preserves shading-start pending **only while still warranted**".

---

## Language & Style Conventions

- **CLAUDE.md**: Written in English.
- **Code comments** in the blueprint YAML: Written in English.
- **Chat responses**: In German.

---

## Home Assistant Limited Templates

Home Assistant distinguishes between *full* and *limited* template contexts. See also Invariant 10.

| Context | Limited? | Notes |
|---------|----------|-------|
| `trigger_variables:` | **Yes** | Evaluated at trigger time, before the action runs |
| `variables:` (action scope) | No | Full template access |
| `conditions:` | No | Full template access |
| `sequence:` / `action:` | No | Full template access |

**Unavailable in limited templates:** `states()`, `is_state()`, `state_attr()`, and any integration-specific runtime function.

---

## Code Style

### No implementation comments in the blueprint

Comments explaining *why* something is placed at a specific location (e.g. template context restrictions) do **not** belong in the blueprint YAML. They are irrelevant to end users and clutter the file. Put such explanations in CLAUDE.md or commit messages instead.

**Wrong:**
```yaml
# Force pause (evaluated here because states() is not allowed in trigger_variables)
is_paused: ...
```

**Correct:**
```yaml
# Force pause
is_paused: ...
```

### No Jinja2 comments in templates

Do **not** use `{# ... #}` comments inside Jinja2 templates. They clutter the template code and are not visible to end users. Use YAML comments (`#`) outside of templates where needed, or document in CLAUDE.md.

**Wrong:**
```jinja2
{# Guard: ts.shd only updates when shd actually changes #}
{% if new_shd == current_shd %}
```

**Correct:**
```jinja2
{% if new_shd == current_shd %}
```

---

## Version Bumping

The version string exists in **two** locations — both must be updated together:

1. **Description** (user-facing): line ~7 → `**Version**: YYYY.MM.DD`
2. **Variable** (runtime): line ~2756 → `version: "YYYY.MM.DD"`

The **changelog** is at `docs/CHANGELOG.md` (symlinked from `blueprints/automation/CHANGELOG.md`). Add a new `# CCA YYYY.MM.DD` section at the top with the changes. Use the existing emoji/format conventions (🐛 Fix, 🔧 Improvement, ✨ Feature).

---

## Code Quality Gates

Every change to the blueprint must pass all of the following checks before commit.

### Logic correctness

- No logic gaps: every reachable combination of sensor states must lead to a defined, intentional outcome.
- The priority cascade must be respected in every branch (see Invariant 1).
- `*helper_update` must be called at the end of every branch sequence (see Invariant 2).
- After any code change, run `pytest tests/ -v` — all tests must pass.

### No Home Assistant warnings or errors

- No unknown service calls, invalid entity domains, or blueprint schema violations.
- No Jinja2 template errors at runtime. Test critical templates with Developer Tools → Template before committing.
- No undefined variable references in templates — guard with `| default()` where a value may be absent.
- No deprecation warnings from HA service calls (use current action syntax).

### Code consolidation

- Use YAML anchors (`&anchor` / `*anchor`) for repeated action sequences instead of copy-paste.
- Extract shared computed values into `variables:` rather than duplicating complex expressions across branches.
- Do NOT over-abstract: three similar lines of code are better than a premature abstraction that hides intent.
- Keep individual `choose:` branches short and focused. A branch that is hard to read is a bug waiting to happen.

### End-user usability

- Every blueprint input must have a `name:` and a `description:` that a non-technical user can understand without reading the code.
- Optional inputs must use `default:` values or constrained `selector:` types so misconfiguration is difficult.
- Section headers (`section:`) must group related inputs logically as visible in the HA UI.
- Never expose internal field names, compact keys, or implementation details in user-facing descriptions.

### Debug-friendliness

- Every `choose:` branch must have an `alias:` that uniquely identifies it. This text appears in the HA automation trace and is the primary tool for remote support.
- `sequence:` steps that drive the cover or write the helper must have an `alias:` describing what they do.
- The helper JSON is the primary debug artifact. All fields must be kept meaningful and up to date at all times — a stale helper is as bad as no helper.
- Do not suppress HA log output for unexpected or error states. Unexpected states should log a warning so they are discoverable.

---

## Running Unit Tests

```bash
pip install pytest jinja2 pyyaml
pytest tests/ -v
```

Tests verify the priority cascade for critical scenarios without a real Home Assistant instance.
