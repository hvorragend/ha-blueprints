# CCA Architectural Invariants — full rationale

The one-line index of these invariants lives in `.claude/CLAUDE.md`. This file
holds the full explanation, examples and edge cases for each invariant.
Read the relevant invariant here before changing any branch it governs.

---

## Architectural Invariants — ALWAYS FOLLOW

### ⚠️ Invariant 1: NEVER put position checks in branch conditions

**Wrong:**
```yaml
- conditions:
    - "{{ window_opened_now }}"
    - "{{ effective_state != 'lock' or not in_open_position }}"  # ← NOT HERE!
  sequence:
    ...
```

**Correct:**
```yaml
- conditions:
    - "{{ window_opened_now }}"
    # No position check here!
  sequence:
    - variables:
        will_drive: "{{ force_allows_ventilate and (effective_state != 'lock' or not in_open_position) }}"
        drive_plan:
          run: "{{ will_drive }}"
          ...
        update_values: ...
    - *apply_transition  # Helper is ALWAYS updated
```

**Why:** When the position check is in the branch conditions, the branch is not selected if the cover is already at the target position. This causes the logic to fall through to the next branch (e.g. shading), breaking the priority cascade.

**Rule:** Every branch that has priority must always be consumed (even if no drive is needed). The position check belongs in `will_drive`, never in the branch conditions.

### ⚠️ Invariant 2: Always update the helper

`*apply_transition` must be at the end of **every** branch sequence — even when no cover drive occurs (its helper write is unconditional). This is the only way to correctly persist the `res` status (and other fields). Classification-style handlers (Manual, Reset) set `update_values` inside their choose branches and call `*apply_transition` once in the shared tail. Never call `*helper_update` or `*drive_with_actions` directly from a branch.

### ⚠️ Invariant 3: Realtime sensor vs. helper state

- `state_resident` / sensor checks (`states(contact_window_opened)`) → **Realtime** (current sensor value)
- `effective_state` → **Realtime** for `win` (reads live contact sensors **only while `is_ventilation_enabled`** — with the ventilation automation disabled the contacts do not exist as far as CCA is concerned (Bug Pattern AC) and `w` is `'cls'`; falls back to `helper_json.win` only when no sensors are configured)
- `helper_state_window` / `helper_json.win` → **Helper** (last persisted state)

`effective_state` uses the **live sensor** for the window state (`win`), so it always reflects the physical window position — even when the helper hasn't been updated yet (e.g. during the contact handler before `*helper_update` runs).

In the `resident_arriving`/`resident_leaving` handler: always check realtime sensors, as the helper still holds the old state.

**Specifically:** `helper_json.win` (= `helper_state_window`) is only updated when the contact handler actually moves the cover. If the cover was already at the target position when the window opened, `win` stays `cls` in the helper — even though the window is physically open. Therefore, always use `states(contact_window_opened)` in the `resident_arriving` handler, not `helper_state_window`.

### ⚠️ Invariant 4: `resident_flags` reads the live sensor — no stale-state problem

`resident_flags.allow_shade/allow_ventilate/allow_open` are based on `state_resident` (line ~2832), which reads the **live** sensor via `states(resident_sensor)` — **not** from `helper_json.res`.

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

**Wrong:** `man: 0` in `update_values` for every block that calls `*apply_transition`.
**Correct:** `man: 0` only when the branch actually drives — encoded via the `will_drive` pattern: `man: "{{ 0 if will_drive else helper_json.man | default(0) | int }}"` with `drive_plan.run: "{{ will_drive }}"` (see Transition Architecture).

### ⚠️ Invariant 8: Timestamp invariants

**ts.shd (shading timestamp):**
- `ts.shd` may only be set when `shd` actually changes (guard in `helper_update`: only when `new_shd != current.shd`)
- In the SHADED path of the `resident_leaving` handler (since the target-chain consolidation: the `leave_target == 'shd'` case): `shd` was already `1` (precondition) → do **not** set `ts.shd` to `now`, preserve the original activation timestamp
- The midnight reset (BRANCH 11) does **not** stamp `ts.shd` when it clears `shd` 1→0 (CCA 2026.07.19). The trigger fires at 23:55, but the branch's random 0–60 s delay plus queued runs ahead of it (a drive delay can hold the queue for up to 10 minutes) can push the **write** past midnight — and a next-day stamp makes the once-per-day guard (full-date compare) block the *whole following day's* shading (the #365 failure through the back door). Omitting the stamp is behavior-neutral on the happy path: `ts.shd` keeps the same-day stamp of the last real `shd` transition, so the guard decides identically.

**pnd / ts.due / ts.arm (pending phase + timestamps):**
- The top-level `pnd` enum encodes which phase is pending: `'non'` (idle), `'beg'` (start armed), `'end'` (end armed). Only one value at a time is representable — Invariant 11 is enforced by the schema.
- `ts.due` is the **fire time** of the armed pending (when the execution trigger should fire). Re-armed on every retry to `now + waiting_time`.
- `ts.arm` is the **retry anchor**: when the current pending sequence first armed. Set once at the start of the sequence, **preserved across all retries**, read by `shading_start_max_duration` and `shading_end_max_duration` checks via `helper_ts_pending_arm`.
- These three keys must not be reset in win-only helper updates (when only `win` is updated without a drive).
- `pnd: 'non'` always implies `ts.due == 0` and `ts.arm == 0`. Terminal branches must set all three together.
- Retry-continuation branches must set `pnd: 'beg'` (or `'end'`) and the new `ts.due`, but **not** `ts.arm` — `helper_update` preserves the existing value automatically when a key is omitted.
- Terminal branches that clear pending:
  - Start: Drive, Lockout-skip, Save-for-future, no-drive default of the drive choose, Abort (shared retry routine)
  - End: Tilt-only, Lockout, Ventilation, Move-cover (then/else and the opening-prevented else), Stop retry, stale-pending cleanup (#395)
  - Midnight reset (BRANCH 11, "Reset shading status")
  - Incidental clears in non-shading branches (force, manual) — also clear all three for hygiene.
- **Every execution path must be terminal** (Bug Pattern AK): any path reachable from `t_shading_start_execution` / `t_shading_end_execution` must end in a helper write that either re-arms (`pnd` + new `ts.due`) or clears (`pnd: 'non'`, `ts.due/arm: 0`). The execution templates compare `now() >= ts.due`; once due is in the past they stay true forever and never re-fire — a path that stops without a helper write leaves the pending armed until the midnight reset. Drive chooses inside the execution handlers therefore need a default, and `if:` steps before a `stop:` need an else.
- **Contact handler branches must NOT reset `pnd`/`ts.due`/`ts.arm`.** Window open/close events are orthogonal to shading pending state. Omit these keys from `update_values` so `helper_update` preserves the existing values (#484).

**t / d (write and drive timestamps, both top-level):**
- `t` is stamped on **every** helper write. Consumers rely on exactly that semantic: `automation_resumed`, the instance-takeover check, `midnight_reset_missed`. Never make `t` conditional.
- `d` is stamped **only** when the writing run's `drive_plan.run` was true — derived inside `helper_update` from the same `will_drive` decision that gates the `man: 0` reset (Invariant 7). Pure state syncs (window/resident updates, pending arming, base-only updates) must never stamp it: the manual-detection settle window keys off `d` via `helper_ts_drive`, and a stamp from a non-driving write reopens the #614 blind window (Bug Pattern AP). No branch writes `d` through `update_values` — it is owned entirely by `helper_update`.
- Known corner, accepted (same family as the pause design decision): `drive_plan.run` true with the movement suppressed at the last moment (live pause check, tolerance no-op) still stamps `d`. That errs in the safe direction — a suppressed manual detection is less harmful than CCA reading its own movement as a manual override.

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

### ⚠️ Invariant 13: `recovered_state` must mirror `effective_state`

The recovery gate duplicates the priority cascade in `recovered_state` —
deliberately, because `effective_state` reads `helper_json.bas`/`.frc`, which
are exactly the stale values the recovery must correct, and HA templates
cannot be parameterized (see the design decision "Restart / outage handling").

**Every change to the `effective_state` cascade must be applied to
`recovered_state` in the same commit** — new priorities, new gates
(e.g. the #553 `is_opening_scheduled` schedule gate), changed conditions.
The parity tests (`tests/test_restart_recovery.py::TestCascadeParity`) render
both templates with identical inputs and fail when they drift apart — extend
them with a scenario covering the change, do not weaken them to make a
divergence pass.

### ⚠️ Invariant 14: Anchor bodies are rendered as variables on every run

The anchors `&cover_move_action`, `&tilt_move_action`, `&drive_with_actions`,
`&helper_update` and `&apply_transition` are defined as **values of a top-level
`variables:` step**. Home Assistant renders variable values recursively when
that step executes, so every template inside those anchor bodies is evaluated
once per run **outside** its real execution context (no `repeat`, no `wait`,
no `target_position`, no `drive_action_set`, no `drive_plan`).

**Rule:** Every runtime-context reference inside an anchor body must be
template-guarded:

- `{{ repeat.item if repeat is defined else '' }}` — never plain `repeat.item`
- `{{ wait.completed if wait is defined else '' }}`
- `target_position | default(101)`, `drive_action_set | default('')`, …
- `(drive_plan | default({})).run | default(false)` — never plain `drive_plan.run`

These guards look like dead defensive code but are load-bearing: removing
them makes the anchor-definition step raise `UndefinedError` on every run.
Anchors that must not be pre-rendered (e.g. `&shading_start_retry`) are
instead defined at their first use inside the action tree — such anchors are
only evaluated in their real context, but can only be aliased *after* their
textual position in the file.

The shared drive idiom `&drive_with_actions` (before-action → cover move →
tilt move → after-action) is selected via the `drive_action_set` variable
(`up` / `down` / `ventilate` / `shading_start` / `shading_end`). Delays and
`*helper_update` deliberately stay at the call site so ordering and timing
remain visible per branch. With the Tilt Wait Mode `tilt_before_position`
(`is_tilt_before_position_mode`, Issues #355/#612 — motors like the Somfy
J4 IO that reject tilt commands while fully open, force their tilt target
to 100/0 on `open_cover`/`close_cover`, and restore the last tilt target
after every positioning run), a preliminary alignment step runs before the
cover move: a cover at the fully-open endpoint is briefly started downwards
(so the motor accepts tilt commands again), otherwise the slats are
pre-tilted to match the travel direction (0 when moving down, 100 when
moving up). `&cover_move_action` then avoids the `open_cover`/`close_cover`
shortcuts unless the tilt target matches their implicit tilt, and the final
tilt target is sent after the movement — `&tilt_move_action` waits for the
cover to become idle in this mode, exactly like `wait_idle`. The alignment
step is skipped when the position will not change (same tolerance check as
`&cover_move_action`), so a tilt-only run tilts directly.

---

