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
3. BASE=OPN → bas == "opn" AND is_opening_scheduled AND no privacy/shading/restriction → Open position
4. VENT     → win == "tlt" AND base would close/shade/privacy    → Ventilation position
5. PRIVACY  → resident && closing                                → Close position
6. SHADING  → shd == 1 && allow_shade                            → Shading position
7. BASE=CLS → bas                                                → Close position
```

The variable `effective_state` returns the currently active state from this cascade (`lock`, `opn`, `vnt`, `cls`, `shd`).

**Rationale for BASE=OPN before VENT:** A tilted window signals ventilation intent — and a fully open cover provides maximum airflow. So when the time schedule says "open" (`bas=opn`) and nothing else lowers the cover, opening wins over the tilted-vent floor. VENT is a *floor* only when the cover would otherwise go below ventilation position (close, shading, privacy-close, or base=opn with `allow_open=false`).

**BASE=OPN beats VENT only when an opening automation actually exists** (`is_opening_scheduled`). `bas` initializes to `'opn'` and is only ever switched to `'cls'` by the close handler — so in a shading-only setup with no opening automation, `bas` stays `'opn'` permanently. Without the gate the VENT floor could never apply there (Issue #553, Bug Pattern Z). When no opening automation exists, a tilted window therefore still produces `vnt`.

The flag mirrors the `enabled:` gates of the **opening triggers**, not the time control switch: `bas` only ever reaches `'opn'` through the opening handler, and that handler is reached by four sources — time fields (`t_open_1/2`), calendar (`t_calendar_event_start`), brightness (`t_open_4`) and sun elevation (`t_open_5`). The latter two open the cover with time control switched **off** (the opening branch passes them through via `is_time_control_disabled`), so their `bas: 'opn'` is a real intent too. Gating on `not is_time_control_disabled` misread it as the init default and let VENT drag an open cover down to the ventilation position (Bug Pattern AL).

Implementation: `effective_state` first computes `base_target` (the cover state without VENT consideration: `cls`, `shd`, or `opn`), then applies VENT when `win == 'tlt'` and `not (base_target == 'opn' and is_opening_scheduled)`.

---

## Transition Architecture (CCA 2026.07.03)

The action tree follows an **event → reducer → reconciler** structure within the
limits of HA YAML (user-supplied `!input` conditions can only be evaluated in
`conditions:`/`if:`, and variables set inside `if/then` do not propagate — so
branch *dispatch* stays a `choose:` skeleton, while state computation and
actuation are centralized).

**Every leaf branch computes exactly two things, then calls one shared anchor:**

```yaml
sequence:
  - variables:
      will_drive: "{{ <drive gate> }}"       # only when a gate exists
      drive_plan:                             # actuation plan (reconciler output)
        run: "{{ will_drive }}"               # drive at all? (default false)
        move: "full"                          # 'full' (default) | 'tilt' (tilt only)
        action_set: "up"                      # before/after action selector
        target: "{{ open_position | int }}"
        target_tilt: "{{ open_tilt_position | int }}"
        tilt_first: false                     # reposition tilt to 0 first
        delay_s: "{{ drive_delay_standard }}" # pre-drive delay (0 = none)
      update_values:                          # state transition (reducer output)
        bas: "opn"
        man: "{{ 0 if will_drive else helper_json.man | default(0) | int }}"
  - *apply_transition
  - stop: "..."
```

`&apply_transition` performs, in fixed order: optional delay (only when driving)
→ optional drive (`*drive_with_actions`, or `*tilt_move_action` for `move: tilt`)
→ **unconditional** `*helper_update`. Because the helper write is structural,
every path through a leaf branch is terminal (Invariant 2 / Bug Pattern AK by
construction). `tests/test_apply_transition_architecture.py` enforces this:
no raw `*helper_update` / `*drive_with_actions` / `*tilt_move_action` outside
the anchor definitions and the v5→v6 migration persist.

**Event normalization** (post-forecast variables block): the live sensor idioms
are computed once per run and referenced by all branch conditions —
`window_opened_now`, `window_tilted_now`, `window_any_now`,
`window_opened_clear` (explicitly closed/unconfigured — NOT the negation of
`window_opened_now`; an unavailable sensor is neither), `lockout_now.closing/
shading_start/shading_end`, `shading_once_guard_ok`, `drive_delay_standard`.
The contact handler re-reads the sensors **after its settle delay** into local
`contact_opened_now` / `contact_tilted_now` / `was_ventilating` — do not replace
those with the trigger-time globals. `override_blocks.opening/closing/
ventilation/shading` (top variables block) centralizes the manual-override
gates (`helper_state_manual and override_flags.X`).

**Reconciler projection** `state_targets` and **drive gates** `state_gates`:
`state_targets` maps each state (`lock`/`opn`/`vnt`/`shd`/`cls`) to
`{target, target_tilt, action_set}`; `state_gates` maps each state to the
standard drive gate `force_allows_X and (effective_state != X or not
in_X_position)`. Branches that "drive to state X" (force enable, force
last-wins, force-pause resume) build their `drive_plan` from them instead of
repeating position/tilt/action/gate triples. The force-pause-resume handler is
a pure reconciler step: `resume_state` (= `effective_state` with `'opn'`
fallback) → `state_targets[resume_state]`.

**Target chains** (CCA 2026.07.03, round 2): handlers that were N nearly
identical "drive back to the background state" branches are collapsed into a
single leaf per handler that computes a target variable via a first-match
Jinja chain mirroring the former branch order, then builds `drive_plan` from
`state_targets[target]` / `state_gates[target]` and the `update_values` from
a small per-target template:

- Contact "Window closed" → `return_target` (`shd` → `opn` → `cls` / `non`),
  one leaf ("Window closed - Return to background state") — all three former
  branches shared the same gates and `auto_ventilate_end_condition`.
- Resident leaving → `leave_target` (`lock` → `shd` → `opn` → `cls` / `non`)
  plus a separate VENT-tilted leaf (needs `auto_ventilate_condition`).
- Resident arriving → `arrive_target` (`cls` / `non`, lockout suppresses
  privacy-closing) plus the VENT-hold leaf.
- Force-disable recovery → `recovery_target` (`cls` → `shd` → `lock` → `opn`
  → `vnt` / `non`); `vnt` keeps its own leaf (user condition) — it is the
  lowest-priority target, so the split preserves ordering.

The user-supplied `!input` conditions are the reason VENT targets keep
dedicated leaves: they can only be evaluated as YAML conditions. Chain
equivalence with the former branch order was verified by exhaustive
truth-table simulation. The chosen target is visible in the trace (variable)
and the logbook (`log_extra`); the per-target stop messages were merged into
one generic message per handler.

**The `will_drive` pattern encodes Invariant 7:** the drive gate is defined
once per branch; `drive_plan.run` and the `man:` reset in `update_values` both
reference it, so `man: 0` can never diverge from the actual drive decision.

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

**Wrong:** `man: 0` in `update_values` for every block that calls `*apply_transition`.
**Correct:** `man: 0` only when the branch actually drives — encoded via the `will_drive` pattern: `man: "{{ 0 if will_drive else helper_json.man | default(0) | int }}"` with `drive_plan.run: "{{ will_drive }}"` (see Transition Architecture).

### ⚠️ Invariant 8: Timestamp invariants

**ts.shd (shading timestamp):**
- `ts.shd` may only be set when `shd` actually changes (guard in `helper_update`: only when `new_shd != current.shd`)
- In the SHADED branch of the `resident_leaving` handler: `shd` was already `1` (precondition) → do **not** set `ts.shd` to `now`, preserve the original activation timestamp
- The midnight reset (BRANCH 11) **does** write `ts.shd: "now"` when it clears `shd` 1→0 — this is fine: the reset fires at **23:55 same day** (`now() >= today_at('23:55:00')`), so the stamp lands on the current day, never the next one. The once-per-day shading guard (full-date compare) therefore still allows shading the following day.

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
(`is_tilt_before_position_mode`, Issue #355 — motors like the Somfy J4 IO
that restore the previous slat position after every positioning run), the
inner order flips to tilt move → `tilt_delay` → cover move, and
`&tilt_move_action` skips its pre-tilt wait (the cover is still idle): the
motor's own restore re-applies the target tilt after positioning, so no tilt
command is sent — or waited for — after the movement.

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

Enforced by `tests/test_apply_transition_architecture.py::TestForcePauseIsPartOfEveryDriveGate` — a new branch whose drive gate ignores the pause fails structurally.

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

++ b/.claude/CLAUDE.md
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

### Restart / outage handling: block on state-critical entities, recover via `t_recovery`

Two halves of one mechanism. Neither works without the other.

**The catch-up half is opt-in, and since CCA 2026.07.13 V7 it is a three-way choice**
(`enable_recovery`: `never` (default) | `outage` | `always`; legacy booleans map to the
two ends via `recovery_mode`). Users reported unwanted cover movements right after a HA
restart — the recovery is *supposed* to move the cover when the cascade demands it (e.g.
applying a stored shading intent or catching up a missed opening), but many users prefer
"never touch the covers after a restart" over catching up.

**The middle mode exists because "restart" and "outage" are different events.** A HA
restart, a reload and a UI save re-create the automation; a Zigbee gateway that drops out
over the closing time does not. The complaints were about the first class; leaving a cover
open all night because the stick hiccupped is nobody's preference. `recovery_catch_up`
(action variable) is the single gate: `always`, or `outage` **and** neither `is_restart_run`
nor `automation_resumed`.

**`is_restart_run` must not depend on HA's start-up order**, and it does not. A restart brings
every entity back from `unavailable`, so the *source* `t_recovery` triggers fire then too —
and the integrations load in an arbitrary order, before or after the automation attaches,
before or after `homeassistant_start`. Three signals, and the first two are what make the
order irrelevant:

1. **`automation_resumed`** — the primary one. The availability gates block **every** run
   while a critical source is missing, so nothing can write the helper; `automation_resumed`
   (`helper.t < attach`) therefore stays armed for the **whole** start-up, however long the
   integrations take. The run that finally passes is the one after the last critical source
   returned — and it is flagged, by construction, not by timing luck.
2. **The outage this run ends *began* at the attach** (`trigger.from_state.last_changed <
   attach + 300`, scoped to `from_state.state in invalid_states` — the shape of the
   `t_recovery` source triggers). On a restart every entity is created or restored
   `unavailable` during boot, so its `last_changed` points back at the boot **no matter how
   many hours the gateway then takes to answer**. This is the clause that makes a slow
   integration a restart. Without it, a Zigbee hub answering 40 min after a restart reads as
   a mid-runtime outage and `outage` mode moves the cover after a restart — precisely what it
   promises not to do. The scoping is load-bearing: unscoped, a contact that had been `off`
   since yesterday carries a `last_changed` older than the attach and would read as a restart.
3. **A 300 s settle window** for the tail: a source returning *after* the first helper write
   has already cleared `automation_resumed`. It only has to cover the spread of entities being
   *added* during boot — not how long a device stays unreachable; (1) and (2) do that.

`homeassistant: start` plays no part in the classification — it is only a catch-up trigger,
gated on `recovery_mode == 'always'`. So when it fires relative to the integrations does not
matter either.

**The dividing line is cause vs. prevent, not "recovery code vs. other code".**
A mechanism is opt-in when it can *cause* a movement; it is always active when it
can only *prevent* a wrong one. That single rule places all three pieces:

- **Opt-in.** A *source* `t_recovery` trigger whose source can only be *caught up*
  carries `enabled: "{{ is_recovery_enabled and ... }}"` — filter at the trigger,
  same rationale as #550: no run, no trace, no drive. That is every source that
  **never blocks a run**, so its outage strands nothing: resident, brightness, sun,
  forecast, custom shading sensor, calendar, workday — **and the force pause**
  (`is_paused` is read live and nothing about it is stored, so its return leaves no
  stale claim; the only thing to do would be to drive back into the force the pause
  suspended). Inside the gate, `will_drive` (= `recovery_catch_up and recovery_allowed`)
  gates the drive, the direction `choose:` gates the re-derived base state (writing
  `bas: 'cls'` for a swallowed closing is a *deferred* movement — a later branch would
  drive into it), and `recovered_pending` refuses to arm a shading pending (it would
  drive later too). Note `recovered_base` itself stays **unconditional** — only the
  *write* (`new_base`) is gated.
- **Always active: the `t_recovery` triggers of the five gate sources** (cover, status
  helper, custom position sensor, both window contacts — CCA 2026.07.13 V7). Third
  application of the rule, and the one that was missed twice. These are exactly the
  entities Half 1 blocks on, and while one of them is unusable the gate drops **every**
  run — including the *latching* ones from the audit below, which never fire again
  (`t_shading_*_execution`, `t_reset_timeout`/`t_reset_position`), and including the
  runs that would have written `frc`/`win`/`res`. A stale `frc` then holds the whole
  cascade in the force state and produces a wrong movement on **every** later trigger.
  Nothing else reports any of this: no restart happened, so neither `homeassistant: start`
  nor the resume trigger fires, and the force entities' own (ungated) triggers only fire
  when the *force* entity dropped out — not when the *cover* did. Gated off, a single
  gateway hiccup left the automation permanently broken with the opt-in off (the default),
  which is the state most users are in. Correcting it prevents a wrong movement, so it is
  always active; with the catch-up off the run is hygiene-only (`will_drive` false).
- **Always active.** The availability gates of Half 1 — they only block.
- **Always active: the four force-entity `t_recovery` triggers** (#603). They were
  gated with the rest, and that misread the rule: `frc` is **persisted** and
  `effective_state` reads it, so a stale `frc` does not miss an event — it holds the
  whole cascade in the force state and produces a **wrong movement on every later
  trigger**. And nothing else corrects it: `t_force_disabled_*` is `from: "on"`, so
  `unavailable → off` never fires it, and `live_force` deliberately keeps *reading*
  the recorded force as active while its own entity is unreadable (that is the Tier-2
  fallback). With the trigger gated off, a force whose switch dropped out and returned
  as `off` stayed recorded **indefinitely**. Correcting it prevents a wrong movement,
  so it is always active; with the opt-in off the run is hygiene-only (`will_drive`
  false). The force *pause* keeps its gate — see above; that asymmetry is the rule
  applied, not an oversight.
- **Always active: the resumed-run helper hygiene.** The resume trigger
  (`this.last_changed`, piece 2 below) is the **one** `t_recovery` trigger without
  the opt-in gate, and `automation_resumed` claims any trigger regardless of it.
  A resumed automation holds a helper that may be *days* old, and acting on it moves
  the cover **wrongly**: a shading from an earlier day still reads as active (the
  23:55 reset never ran), and an override reset that came due while the automation
  was off can never fire again (its trigger latches). So the gate still runs, clears
  the stale shading / dead pending / expired override, re-reads force+resident+window,
  and stops — with `will_drive` false it cannot move the cover. Preventing a wrong
  movement is not what the opt-in guards against. Cost, accepted: with the switch off
  there *is* a trace and a helper write on a resumed run, and the first regular trigger
  within ~60 s of the resume is consumed by the gate's `stop:` (it cannot hand control
  back to the dispatch — `helper_json` and everything derived from it was rendered
  before the write). Two corner costs of that claim, both accepted: a shading pending
  whose `ts.due` elapses between the trigger attach and the resume fire reads as stale —
  with the opt-in on it is re-armed (execution delayed by one waiting period), with it
  off it is cleared and that shading waits for the next condition crossing. And the
  claim window is only as short as the resume trigger is prompt — which is why the
  resume template mirrors the availability gates (piece 1 below): an edge that fired
  into a blocked run would be consumed, leaving the claim armed until the first regular
  trigger of the day, which it would then eat.

**The `automation_resumed` claim exempts the manual triggers** (`t_manual_position`,
`t_manual_tilt`, #603) — the same exemption they already have from the contact gate,
and for the same reason: the manual handler **never drives**, it only *records* the
intervention (`man: 1`, `ts.man`, base-state sync). Claiming it would mean `man: 1`
is never written; the recovery then reads the stale `man: 0` as "no override",
`recovery_allowed` passes, and it drives the cover straight back — actively fighting
the move the user just made. (With the switch off the run is hygiene-only, but it
still *consumes* the event, so the intervention goes unrecorded and the next regular
trigger overrules it.) The exposure is narrow — `automation_resumed` is only true
between the trigger attach and the first helper write, i.e. until the resume trigger
fires ~60 s later — but a user who saves the automation and then grabs the cover
slider lands in it exactly.

**Accepted cost of that exemption:** the manual handler's helper write updates `t`,
which clears `automation_resumed` and disarms the pending resume trigger
(`helper.t` overtakes the attach time). In that corner the stale-helper hygiene does
not run on this resume; it is deferred to the next `t_recovery` source or the 23:55
reset. That is the right trade: the run records `man: 1`, so the recovery would not
have been allowed to drive anyway (`recovery_allowed`), and the reset triggers for the
freshly stamped override arm normally. What is deferred is only the *cleanup* of a
stale `shd`/`pnd`/`frc`, and none of that can move the cover while the override stands.
Chaining both (recovery hygiene *and* manual detection in one run) is not possible:
`helper_json` and everything derived from it is rendered before the first write, so a
second write in the same run would clobber the first (same reason the gate cannot hand
control back to the dispatch).

Consequence with the switch off: every "Repaired by the recovery" entry in the
orphan-audit table below that *catches up* a dropped event does **not** apply —
dropped events stay dropped until the next regular trigger, which is the documented
pre-2026.07.12 behavior the user explicitly chose. The rows repaired by *hygiene*
(stale shading, dead pending, expired override, stale `frc`/`res`/`win`) still apply.

**Do not "harmonize" by gating the resume trigger too.** That reinstates exactly the
two bugs it was written for — and since the switch is off by *default*, it would
reinstate them for almost every user. `tests/test_restart_recovery.py::TestRecoveryTriggers`
pins the split (`test_the_resume_trigger_is_deliberately_not_gated`,
`test_the_opt_in_gates_the_drive_not_the_hygiene`).

#### Half 0 — a disabled entity is not an outage

HA drops a **disabled** (or deleted) entity out of the state machine entirely. `states(x)`
reports `'unknown'` for it — indistinguishable from a dropout by that read alone — but it is
the opposite kind of event: it **never comes back**. No `unavailable → valid` flank, so no
`t_recovery`, no repair, and no Tier-2 fallback is ever corrected. **Every mechanism below is
the wrong one for it**, and each failed silently and permanently:

- a disabled **cover** or position sensor → the Tier-1 gate blocks *every* run, forever, with
  no log line anywhere (a `condition:` cannot log — Bug Pattern AF: the upstream gate orphaned
  the downstream validation);
- a disabled **force entity** → `force_helper_unreadable` kept the recorded force alive
  (that is its whole job during a dropout), and no trigger was left to clear `frc` → the
  cascade froze in the force **permanently**.

`states[x] is none` is the **only** way to tell the two apart, and it is where the split is
made (CCA 2026.07.13 V7):

- **The Tier-1 gate skips missing entities** (`for entity in critical_entities if states[entity]
  is not none`) so the run reaches the **mandatory entity validation** in the actions, which
  names the entity, logs it, and *then* stops. Same shape as the Tier-1b helper rule: block on
  `unavailable`, let the unrepairable-by-waiting case through to something that can speak.
- **`force_helper_unreadable` requires the entity to exist.** Gone ⇒ the force is over, not
  unreadable.
- **Condition-only (Tier-3) entities** are logged as a *warning* and otherwise behave exactly
  as if unconfigured — which is the one place where "pretend it was never configured" is the
  right answer.

**Do not extend that "pretend it is unconfigured" reading to the window contacts.** It would
silently disable the lockout (Invariant 6). A disabled contact keeps the Tier-2 rule (blocks
only while `win != 'cls'`) and is reported by the validation — a parked cover the user can see
the reason for beats a cover that lowers onto an open window.

#### Half 1 — the gate (global conditions)

Three tiers, and the tier a source belongs to is decided by **what CCA can do without it**.

**Tier 1 — hard block (`critical_entities`).** No substitute exists, so the run is blocked, period:

| Entity | Failure mode when invalid |
|---|---|
| `blind` | no `current_position` → `101` sentinel; `\|101 − 100\| ≤ position_tolerance` makes `in_open_position` **true**, so a dead cover reads as "open" |
| `custom_position_sensor` (when it is the position source) | same as `blind` |

```jinja2
{% set ns = namespace(ready=true) %}
{% for entity in critical_entities %}
  {% if states(entity) in invalid_states %}{% set ns.ready = false %}{% endif %}
{% endfor %}
{{ ns.ready }}
```

**Tier 1b — the status helper, and why it needs its own gate.** It is state-critical (`helper_json` falls back to a fresh default JSON, so a write would destroy the persisted state) — but it is **not** in `critical_entities`, because it must stay **repairable**:

```jinja2
{{ cover_status_helper == [] or states(cover_status_helper) != 'unavailable' }}
```

- `unavailable` → the entity exists but is not loaded yet; its stored value is intact. **Block** — writing defaults here would destroy a good state.
- `unknown` / empty / non-JSON → there is no value left to protect. **Must pass**, because the actions contain the repair: the *"Initialise empty helper with JSON default values"* step rewrites a fresh v6 JSON on any run. Gating it with the full `invalid_states` list makes that repair unreachable and the automation **permanently dead** — an `unknown` helper could never be rewritten (Bug Pattern AF family: an upstream gate must not orphan a downstream repair). This is not hypothetical; a helper can end up `unknown` after being recreated in the UI or after a failed state restore.

**CCA never writes a non-JSON value.** Both `input_text.set_value` calls (`helper_update` and the init step) build a dict literal and emit `| to_json`; there is no path that writes `unknown`. A `unknown` helper state comes from HA, not from the blueprint — the blueprint's job is only to detect and repair it. The payload size is bounded by the schema (~200 chars, timestamps are fixed-width), and a helper whose `max` is below 210 is caught by a `stop` before the main `choose`.

**Tier 2 — last-known fallback (window contacts, resident sensor, force entities).** For the first two, these are **battery devices that only report on change**. After a *hub* restart they can stay stateless for **hours** — until someone actually moves the window. A hard block would park the cover for the rest of the day, which is far worse than the bug it prevents. So the helper's persisted value is used instead:

- `state_resident` (and `resident_now` in the contact handler) fall back to `helper_json.res` while the sensor is invalid. Reading a dropped sensor as "away" would silently drop privacy closing.
- The **force entities** are `input_boolean` **or `switch` / `binary_sensor`** (see the input selectors), so they drop out like any other integration. `is_forced_*` reads "not `on`" — which is what an invalid state produces — so an unreadable switch would read as *turned off*. `live_force` therefore falls back to `helper_state_force`, but **only when the entity of the force the helper actually records is the unreadable one** (`force_helper_unreadable`) and nothing else is live:

```jinja2
{{ helper_state_force if candidates.best == 'non' and force_helper_unreadable else candidates.best }}
```

  The scoping matters in both directions. A force whose *own* switch is readable and `off` really did end → clear it (BRANCH 8 depends on this: it runs on exactly that transition). An unrelated switch dropping out must not resurrect a force that ended. And a genuinely live force always beats the fallback.

  **Why a fallback and not a gate:** `t_force_enabled_*` / `t_force_disabled_*` / `t_force_pause_disabled` are `from: "on"` / `from: "off"` state triggers, so `unavailable → on` and `unavailable → off` **do not fire them**. Without the fallback, a recovery run that lands while the switch is still out writes `frc: 'non'`, drives the cover to the scheduled target, and the force is gone **permanently** — no trigger ever re-establishes it. The force entities therefore also carry a `t_recovery` trigger; that is what re-syncs `frc` once the switch is readable again — and it is **not** gated on `is_recovery_enabled` (#603), because without it a force that returned as `off` would stay recorded in the helper forever.

- Window contacts have no equivalent single read (the raw `states(contact_window_*) in ['true','on']` pattern is spread across every handler and reads an invalid contact as "closed"). Rather than sweeping all of them, the gate makes that reading *safe*: a run is blocked **only** while a configured contact is invalid **and** the last known `win` is not `cls`.

```jinja2
{% set last_window_closed = helper in invalid_states or helper | regex_search('"win"\s*:\s*"cls"') %}
{{ last_window_closed or not contact_missing }}
```

  - Last known **closed** + contact stateless → run. "Reads as closed" agrees with the last known truth, so every raw read in every handler is correct. This is the normal case after a hub restart (windows are usually shut) — CCA keeps working.
  - Last known **open/tilted** + contact stateless → block. CCA would otherwise treat the window as closed and drop the lockout. Blocking holds the cover in its current lockout/vent position — which is exactly what lockout wants. It self-heals: closing the window makes the contact report, which fires `t_recovery`.

**The contact triggers themselves are exempt from that gate** (`trigger.id in ['t_contact_opened_changed', 't_contact_tilted_changed']`). Without the exemption the gate **deadlocks**: with `win == 'opn'` and one contact stateless, the very event that would write `win: 'cls'` — the other contact reporting the window shut — is the one the gate blocks, so `win` stays `opn` forever. A contact trigger carries a *valid* `to_state` by construction (`not_to` on the trigger plus the `invalid_states` guards in the handler), so letting it through is safe.

**The manual triggers are exempt too** (`t_manual_position`, `t_manual_tilt`). The manual-detection handler only records the intervention (`man: 1`, `ts.man`, base-state sync) — it never drives the cover, so it cannot act on the unknown window state. Without the exemption a manual move during a contact outage would go unrecorded, and the recovery would later overrule the user's intervention (the recovery gate skips only on `helper_state_manual`). The critical-entities and helper gates still apply to these triggers — with the cover unavailable there is no position data to detect a manual change from.

**Dead battery = parked cover.** If a contact never reports again while `win` is `opn`/`tlt`, the cover stays at its lockout/vent position indefinitely. That is the deliberate trade: never lower a cover onto a window last known to be open. The failing condition is visible in the trace; there is no log warning (a condition cannot log).

**Tier 3 — never blocks (sun, brightness, weather/forecast, calendar, workday).** *Condition-only*: an invalid state can only stop shading from starting, never produce a wrong target. Blocking on them would turn a flaky outdoor sensor into a **permanently dead cover automation**.

**Group semantics are intended:** `states(blind)` on a cover group is the *group* state (HA: `available = any(member available)`), so the gate fires exactly when **all** members are gone. A partially-degraded group keeps running on the remaining members' averaged position — the check is deliberately **not** per group member (`expand(blind)`).

**Not gated on the position sentinel:** the gate checks the *state*, not `current_position != 101`. A sentinel gate would permanently silence the `check_config` messages *"Cover entity is missing the required 'current_position' attribute"* and *"Position source set to … but cover doesn't have this attribute"*, which live in the `default:` branch of the actions — a misconfigured cover would then produce no diagnostics at all (Bug Pattern AF family: an upstream gate must not orphan a downstream validation). An unconfigured helper (`cover_status_helper == []`) is likewise excluded from the list, so the MANDATORY HELPER VALIDATION stays reachable.

**The helper is the fallback truth.** While a run is blocked nothing writes, so the helper keeps its last valid content across the whole outage — and it is that content (`win`, `res`, `bas`, `shd`, `frc`) which every fallback above reads. This is why the helper is Tier 1: lose it and there is nothing left to fall back to.

**No grace-period setting.** An "assume closed after N minutes" knob was considered and rejected: it either guesses (unsafe for lockout) or does nothing the last-known fallback does not already do — and it would ask the user to tune a value they cannot reason about.

#### Half 1b — the automation is switched off and on again, or re-saved

This is **not** a restart, and it is the harder case. Nothing reports it: no entity became `unavailable`, no entity came back, and `homeassistant: start` does not fire when an automation is merely toggled. HA just re-attaches the triggers. Meanwhile the automation may have been off for **days**, so the helper is arbitrarily old — and every *latching* trigger from the orphan audit below (`t_shading_*_execution`, `t_reset_timeout`, `t_reset_position`) is **already true at attach time**. A template trigger arms on `false` and fires on the `false → true` edge, so a condition that is true from the start can never fire. The override stays forever, the dead pending stays forever.

**Saving the automation is the same event, and it is by far the most common one.** When a user edits the blueprint inputs in the UI, HA removes the automation entity and adds it back, so `last_changed` is stamped with the save time and every trigger is attached anew — mechanically indistinguishable from a toggle. Verified against a live instance: after a restart every automation shares one `last_changed`, while the four re-saved ones each carry their own save timestamp. HA reloads **only the edited automation** (a save on some other automation does not disturb a CCA instance), but `automation.reload` / *"Reload automations"* / a restart re-attaches **all** of them, so every CCA instance resumes at once — `max: 25` covers that.

Two consequences worth knowing, neither of them a defect: with `enable_recovery` **on**, every save runs the full recovery, so *changing a setting can move the cover* — including the documented "recovery bypasses the direction-specific additional conditions" limitation (a suppressed opening gets caught up by a save hours later). And a run that is inside a `delay:` when the save lands is killed with the queue, so its helper write is lost — the resume hygiene re-reads `win`/`frc`/`res` and repairs it, but `bas` is only re-derived with the opt-in on.

**There is no way to tell a save from a multi-day absence**, and no reason to try: `last_changed − helper.t` is arbitrarily large in both cases (a quiet night leaves the helper hours old), and the hygiene is a no-op on a fresh helper anyway. Do not add a "the helper is recent, skip the recovery" heuristic — it would silently disarm the resume path for exactly the users whose automation sat idle before going down.

Three pieces, and the first one is the only non-obvious part.

**1. The resume trigger — how to fire on a condition that is already true.** `this` is a **snapshot** HA takes when it attaches the triggers (`state.as_dict()`), so `this.last_changed` is the moment the automation was switched on. The template therefore starts out *false* and arms itself:

```jinja2
{{ attached > 0 and (helper.t | default(0) | int) > 0 and
   as_timestamp(now()) > attached + 60 and
   (helper.t | default(0) | int) < attached }}
```

At attach time `now()` is within the 60 s offset → `false` → **armed**. A minute later it flips → fires `t_recovery`. Once the recovery has written the helper, `t` overtakes the attach time → `false` again → re-armed for next time. **Without the offset this trigger would never fire at all** — the exact trap it exists to escape. It polls nothing: an automation that was never off never fires it (any normal trigger writing the helper within that minute also cancels it). It also covers reload and restart, which is why the "a source that never went `unavailable`" limitation is now largely academic.

**The template also mirrors the availability gates** (CCA 2026.07.13 V6): `critical_ready` (cover, plus the custom position sensor when it is the source) and `contact_ready` (the Tier-2 rule verbatim: a stateless contact only blocks while `helper.win != 'cls'`, scoped to `is_ventilation_enabled`). This is not decoration — the trigger has exactly **one** false→true edge, and an edge that fires into a run the gates block is *consumed*: the template stays true, never re-fires, and `automation_resumed` stays armed until the first regular trigger, which the claim then eats. With the opt-in **off** that claimed run is a hygiene-only `stop:` — a restart where the cover takes longer than ~90 s to come back (Zigbee hub after a host reboot) would swallow e.g. the 07:00 opening, and with the opt-in off no gated `t_recovery` source exists to run the hygiene earlier. With the readiness clauses the edge arrives exactly when the run can pass the gates (the `states()` reads register listeners, so the cover's return re-evaluates the template). The user's `auto_global_condition` can still block the run — not mirrorable, pre-existing, documented under "Not repairable, by design". Tests: `TestResumeTrigger::test_it_waits_for_the_cover_to_be_usable` and siblings.

**2. Any trigger on a resumed run is claimed by the recovery.** `automation_resumed` (`helper_ts_write < this.last_changed`) is a second entry condition of the recovery gate, and **that is why the recovery gate runs before the dispatch**. The cover only ever moves through a trigger, so making every trigger recalculate first means acting on an untrusted helper is *structurally impossible*, not merely unlikely. It self-clears the moment the recovery writes the helper. This is the safety net under piece 1: even if the resume trigger never fired, nothing can move on stale state.

**3. The manual-override gate moved out of the entry conditions.** The recovery gate used to be skipped entirely on `man == 1`. That would mean a stale shading or a dead pending survives the recovery whenever an override is active. The gate now lives in `recovery_allowed`, so the **helper hygiene always runs** and only the *drive* is blocked (lockout still overrules, Invariant 6).

**Stale day — the midnight reset that never ran.** `stale_day` = the helper was last written on an earlier date. BRANCH 11 clears `shd`/`pnd` every night at 23:55; if the automation was off, it did not. So a shading from three days ago still reads as active and the first trigger would drive the cover into the shading position — at night, even. The recovery therefore emulates that reset: `recovered_shade` drops `shd`, `pending_is_stale` also fires on `stale_day`, and `ts.opn`/`ts.cls` are zeroed (they gate the once-per-day open/close guards and must not suppress today's run).

**But `ts.shd` is deliberately *not* stamped** when `shd` is cleared 1→0 here. BRANCH 11 may stamp it because it runs at 23:55 on the **same** day; this branch runs on the **new** day, and stamping today's date would make the once-per-day guard block today's shading (Bug Pattern V). Same field, opposite rule — the difference is *which day the code runs on*.

#### Why the recovery is a pre-dispatch gate and not a numbered branch

It sits **before** the main `choose:`, as a plain `if/then` step next to the helper init, the v5 migration, the forecast load and the calendar-relevance check — not as a branch inside the dispatch. It has to run before everything else (on a resumed run it claims every trigger, piece 2 above), and inside the choose that would mean inserting a branch at index 0.

**Adding, removing or reordering a branch of the dispatch `choose:` means touching the trace tools.** `docs/trace-analyzer` and `docs/trace-compare` parse the HA trace path `action/N/choose/M` and resolve `M` against the branch **aliases** — primarily those in the trace's own config, and against the static `BRANCH_ORDER` list when the trace was pasted truncated and carries no config. `BRANCH_ORDER` must therefore mirror the `choose:` order exactly, and `BRANCH_DEFINITIONS` (keyed by alias) must have an entry for every branch. `tests/test_trace_tools_branch_map.py` fails when either drifts.

Because the recovery is *not* a branch, it carries no `choose/M` and would read as "No branch executed". Both tools therefore resolve a run that ended in a pre-dispatch step through the step's own `alias:` (`PRE_DISPATCH_DEFINITIONS`) — same mechanism for the calendar-relevance check. A new pre-dispatch step that can `stop:` a run needs an entry there, or its traces become anonymous.

Keeping the recovery out of the choose leaves the branch indices `0..13` untouched. `stop:` behaves identically in both places, so the control flow is unchanged. `TestResumedRunClaimsEveryTrigger.test_the_recovery_gate_runs_before_the_dispatch` pins the placement and asserts the gate is not *also* inside the choose.

#### Half 2 — the recovery (`t_recovery` → the recovery gate)

A blocked automation **silently loses** every event of the outage: time/calendar triggers of that period never fire again, and template/numeric triggers fire only on a `false → true` transition — which is consumed while the run is blocked. Nothing replays them.

**Trigger set:** `homeassistant: start`, the resume trigger above, plus one state trigger per source (`from: [unavailable, unknown]`, `not_to: [unavailable, unknown]`, `for: 30s`), all sharing the id `t_recovery`. **Every entity CCA reads gets one** — that is the rule, and the reason is that the three tiers of the gate say nothing about *replay*. A Tier-3 source never blocks a run but its return is what makes a missed shading start re-evaluable; a Tier-2 source falls back to the helper but the fallback must eventually be *corrected*. So: cover, status helper, position sensor, both window contacts, resident, brightness, sun, forecast, the custom shading-condition sensor, calendar, both workday sensors, the four force entities and the force pause.

**The last source to return performs the recalculation.** A source returning early fires `t_recovery`, but while any *critical* entity is still missing, the gate stops that run — so the run that survives is the one after the last critical entity is back. Runs triggered by a later-returning *condition-only* source are not suppressed either: they re-run the recovery gate with fresh data (idempotent — the drive is a no-op via the `cover_move_action` tolerance guard, and an already-armed pending is preserved rather than re-armed). `max:` is 25 because a restart can queue one run per recovering source (19) plus normal traffic, and dropping one would drop exactly the run that had the data.

**What the recovery gate restores:**

- `recovered_base` — base state re-derived from the schedule/calendar (`is_evening_phase` / `is_daytime_phase`), **plus the night clause** (CCA 2026.07.13 V6): both phases compare against *today's* times, so between midnight and the opening time both are false — but the night is the previous evening continued. With `is_down_enabled` and `now` before today's opening start (time field, or `calendar_open_start` when calendar-controlled), `recovered_base` is `'cls'`. Without the clause, a closing swallowed the evening before (e.g. shading was active, so `bas` stayed `'opn'`) made a 2-am restart drive the cover **open at night**: `stale_day` drops the shading, `recovered_state` becomes `'opn'`, and the user's `auto_up_action` fires too. Gated on `is_down_enabled` (no closing schedule → do not invent one); falls back to the helper base when the calendar boundary is unknown (`calendar_open_start is none`). The boundaries are available here because the calendar-load gate matches `t_recovery`/`automation_resumed` (Bug Pattern T, third recurrence).
- `recovered_window` — live contact sensors (lockout / vent floor).
- `live_force` — the force state re-derived from the **live** force entities ("last activated wins"), falling back to `helper_state_force` while the recorded force's own entity is unreadable (Tier 2 above). A force switched on or off during the outage left `frc` stale in the helper; `live_force` is the single source of truth and is also what the force-disable handler (BRANCH 8) uses.
- `res` — re-read from `state_resident` and **persisted**. The resident handler's trigger was swallowed by the outage, so nothing else corrects `res` — and `res` is exactly the value `state_resident` falls back to on the *next* dropout. Leaving it stale poisons that fallback.
- `recovered_state` — **mirrors `effective_state`, but on `recovered_base` and `live_force`.** The duplication is deliberate: `effective_state` reads `helper_json.bas`/`.frc`, which are exactly the stale values the recovery must correct, and HA templates cannot be parameterized. **Keep both in sync — every change to the `effective_state` cascade must be applied to `recovered_state` (Invariant 13).** `TestCascadeParity` renders both side by side; `TestRecoveredStateUsesRecoveredInputs` additionally feeds them *diverging* base/force, which parity by construction cannot see.
- `recovered_pending` — shading is **re-evaluated**, not replayed: with `shd == 0` and `shading_start_warranted` (fresh forecast — the forecast-load gate matches `t_recovery` **and `automation_resumed`**, because the resumed-run backstop reaches this code through trigger ids the gate does not list; Bug Pattern T, #603) a start pending is armed; with `shd == 1` and `shading_end_conditions_met` an end pending is armed. Due/arm mirror the arming branches, including the pre-window deferral (Bug Patterns L/S). The existing execution triggers then take over — the recovery deliberately does **not** duplicate the shading execution.
- A **stale pending** (`ts.due` already past) is cleared first: its execution trigger fired during the outage and was blocked, so there is no further `false → true` transition and it can never run. Leaving it armed would make the opening handler defer into a dead flow (Bug Pattern R/AG family).
- `defer_to_shading` — when a start pending is armed and the target would be `opn`, the drive is skipped and the shading execution does the movement (mirrors the #555 opening handler), **unless** the lockout window is open (Bug Pattern AG: the shading execution only stores the intent there and would never open the cover).
- The **user's drive actions** (`auto_up_action`, `auto_down_action`, …) run on a caught-up movement — a closing the outage swallowed *is* a closing. `action_set` therefore comes from `state_targets[recovered_state]`, but **only when `not recovery_in_position`**. This gate is load-bearing: unlike `state_gates`, `recovery_allowed` carries **no** position check (it must stay true so a tilt-only correction still runs), so `drive_plan.run` is true on virtually every recovery run and only `cover_move_action`'s internal tolerance guard suppresses the movement. The before/after actions in `drive_with_actions` sit **outside** that guard — without the gate, each of the ~19 recovery sources would re-fire the user's notifications and scenes after a restart although nothing moved. `not recovery_in_position` is the same "we actually drove" predicate that already gates the `man` reset here, and a tilt-only drive setting no `action_set` matches the "Check for shading tilt" branch (`move: 'tilt'`).
- The **drive target comes from `state_targets[recovered_state]`**, not from a local position chain. `state_targets.shd.target` is `effective_shading_position`, so the recovery honours the alternate shading position (#580) like every other drive. A hand-rolled chain over `shading_position` silently drags the cover back to the *normal* shading position on every restart while the alternate one is active — and `recovery_in_position` compares against the recovery's *own* target, so it cannot notice. `state_gates` is deliberately **not** used: those gate on `effective_state`, and the recovery must gate on `recovered_state` (main's own comment sanctions branches keeping their own gate expression). `TestRecoveryDrive` renders the real projection out of the blueprint and asserts the target still flows through it.
- `recovered_shade` / `stale_day` — a shading (and a pending) from an earlier day is dropped, because the 23:55 reset never ran. See Half 1b; note the `ts.shd` rule there, it is the opposite of BRANCH 11's.
- **Manual override survives** the outage — the gate sits in `recovery_allowed` (`not helper_state_manual or override_expired or recovered_state == 'lock'`), **not** in the branch conditions, so it blocks the *drive* while the helper hygiene still runs. Only lockout overrules it, per Invariant 6. When `override_expired` clears `man`, the branch also runs the user's `auto_override_reset_action`, exactly as BRANCH 10 does — a reset caught up by the recovery must not silently skip the notification/scene the user wired to it.

**Known limitation 1:** a source that never went `unavailable` (many helpers restore straight to their value) produces no recovery trigger — the `homeassistant: start` trigger covers that case.

**Known limitation 2 (`for: 30s`):** a HA state trigger with `for` requires the entity to *stay in the state it recovered into* for the whole period. If it changes again within those 30 s — a cover going `unavailable → open → closed` because something drives it — the pending trigger is cancelled and never fires. After a restart `homeassistant: start` covers this; for a mid-day integration outage the run is simply lost until the next trigger. The settle time is the price for not firing on a flapping entity; do not remove it without replacing that protection.

#### The orphan audit — what a dropped run costs, and who repairs it

Every gate creates the same hazard: a run that is blocked (or a trigger that fires while HA is starting) is **gone**. `trigger: template` and `trigger: numeric_state` fire only on a `false → true` transition, so a **latching** condition — one that stays true after the drop — never fires again. This table is the checklist to re-run whenever a gate or a trigger is added:

The **Opt-in?** column says whether the repair still happens with `enable_recovery`
on `never` (the default). "opt-in" = the repair *causes* a movement (it catches something
up), so the setting buys it. "always" = the repair only *prevents* a wrong movement, so it
runs either way — via the resumed-run hygiene or an always-on fallback.

**A repair marked "always" is only real if some ungated trigger can reach it.** That is the
mistake CCA 2026.07.13 V7 fixed: with the opt-in off, the *only* ungated entries into the
gate were the resume trigger (needs a re-attach) and the force entities (need the *force*
entity to have dropped out). A mid-runtime outage of the cover, the helper or a contact
produced neither — so every "always" row below was dead on paper for exactly the scenario
the gates create. The five gate sources are now ungated too; check any new "always" row
against *which trigger actually fires it*.

| Trigger | Latches? | Cost of a dropped run | Repaired by | Opt-in? |
|---|---|---|---|---|
| `t_open_*` / `t_close_*` / `t_calendar_event_*` | no (window closes) | missed opening/closing | the recovery gate's `recovered_base` (re-derived from schedule/calendar), written via `new_base` — **but only when the direction's `auto_up_condition`/`auto_down_condition` still allows it** (V7): a movement the user's condition suppressed was not missed | **opt-in** |
| *(a gate source drops out mid-runtime and returns — no restart, no re-attach)* | — | the gate blocks every run of the outage, so **all the latching rows below happen at once**, and the `frc`/`win`/`res` the blocked runs would have written stay stale (a stale `frc` moves the cover wrongly on every later trigger, forever) | the **ungated `t_recovery` triggers of the five gate sources** (cover, helper, position sensor, both contacts) | always — nothing else fires; the run they start is hygiene-only with the catch-up off |
| `t_shading_*_pending_*` (numeric/template) | **yes** (condition stays true) | shading never starts/ends that day | the recovery gate's `recovered_pending` (re-evaluates and re-arms) | **opt-in** |
| `t_shading_*_execution` | **yes** (`now >= ts.due` stays true) | pending armed forever, opening handler defers into a dead flow | the recovery gate's `pending_is_stale` (clears it) | always |
| `t_shading_tilt_*` | **yes** (sun stage stays true) | slats keep the previous angle | the recovery gate drives tilt when `recovered_state == 'shd'` | **opt-in** |
| `t_shading_reset` (23:55) | yes, until midnight | `shd` stays 1 overnight | the recovery gate arms an end-pending when the end conditions hold | **opt-in** |
| `t_force_enabled_*` / `t_force_disabled_*` | no (state), but `from: "on"`/`"off"` means **`unavailable → on/off` never fires them at all** | force **permanently lost**: a recovery run while the switch is out reads it as "off", clears `frc` and drives to the scheduled target — and nothing re-establishes it. Conversely, with the re-sync trigger gated off, a force whose switch returned as `off` stays recorded in `frc` **forever** (#603) | `live_force` falls back to `helper_state_force` while that force's own entity is unreadable, **plus** an (ungated) `t_recovery` trigger on each force entity to re-sync `frc` once it is back | always — `frc` is persisted, so a stale one *causes* wrong movements; correcting it moves nothing |
| `t_force_pause_disabled` | no (state), same `from:` problem | the cover stays where the pause left it — nothing stale is persisted (`is_paused` is read live) | a `t_recovery` trigger on the pause entity, which drives back into the suspended force | **opt-in** — the only thing to repair here *is* a movement |
| `t_contact_*` | no (state) | `win` stale → **deadlock** (the gate blocks the very event that would clear it) | **gate exemption** for the two contact trigger ids | always |
| `t_manual_position` / `t_manual_tilt` | no (state/attribute) | manual intervention unrecorded → recovery overrules the user, and with the opt-in on it drives the cover back immediately (#603) | **two exemptions**: from the contact gate, and from the `automation_resumed` claim of the recovery gate (the handler never drives; it must record `man: 1` so `recovery_allowed` can respect it) | always |
| *(any trigger, on a resumed run, while a forecast shading condition is configured)* | — | `shading_start_warranted` renders false without forecast data → `recovered_pending` refuses a warranted shading, and the helper write clears `automation_resumed` → **permanent for that day** (#603, Bug Pattern T family) | the forecast-load gate also matches `automation_resumed`, not just the opening/shading/recovery trigger ids | **opt-in** (only `recovered_pending` consumes it) |
| `t_resident_update` | no (state) | `res` stale → poisons the fallback on the *next* dropout | `state_resident` falls back to `helper_json.res`; the recovery gate re-reads **and persists `res`** | always |
| `t_reset_timeout` / `t_reset_position` | **yes** (`man == 1` keeps them true) | **manual override never resets** — the cover stays under manual control forever | the recovery gate's `override_expired` (re-evaluates the reset rules and clears `man`). This is why the manual gate sits in `recovery_allowed` (blocking only the *drive*) and not in the gate's conditions: a branch skipped on `man == 1` could never lift an expired override | always — clearing an expired override moves nothing, and gating it would strand the cover in manual **forever** |
| `t_reset_fixedtime` | yes, until midnight | override reset one day late | self-heals next day; also `override_expired` | always |
| `t_shading_reset` (23:55) **while the automation is off** | **yes** | `shd`/`pnd` from an earlier day still read as active → the next trigger drives into a days-old shading position | the recovery gate's `stale_day` → `recovered_shade`, `pending_is_stale` (**without** stamping `ts.shd`) | always — this one *prevents* a wrong drive rather than catching one up |
| *(the automation itself is switched off and on, **or re-saved** — a UI save re-creates the entity)* | — | **nothing fires at all** — no entity changed, `homeassistant: start` does not fire, and every latching trigger is already true at attach time | the **resume trigger** (`this.last_changed` + 60 s offset) fires it; `automation_resumed` makes the recovery gate claim any trigger as a backstop | always — the resume trigger is the one `t_recovery` trigger without the opt-in gate |
| *(helper is `unknown`)* | — | init/repair step unreachable → automation permanently dead | helper gate blocks on `unavailable` **only** | always |

`override_expired` is a global variable, not a branch-local one, because `recovery_allowed` and the `man` write both need it, and the reset triggers latch (see the table above). It clears `man` without driving, a deliberate Invariant 7 exception (same class as the midnight reset).

**Rule for any new gate:** before adding a condition that stops a run, list every trigger it can suppress and ask *"if this fires exactly once and I drop it, does anything ever fire again?"* If the answer is no, the gate needs an exemption (contact triggers), a repair path (helper init), or a re-evaluation in the recovery gate (override, shading, force, base). Two of the three gates in this design needed one — assume the next one does too.

**Not repairable, by design:** `auto_global_condition` (the user's own global condition). If it is false when the recovery run fires, the run is dropped and nothing re-triggers when it later becomes true — CCA cannot watch an arbitrary user condition. This is pre-existing behavior for every trigger, not new.

**The direction-specific additional conditions gate a caught-up base flip (CCA 2026.07.13 V7).**
`recovered_base` re-derives the base state from the schedule/calendar alone. The
user-supplied `auto_up_condition` / `auto_down_condition` gate **every** opening/closing
trigger in the normal flow, so a scheduled movement they suppressed was never "missed" —
but the recovery used to replay it anyway (real-world report: opening blocked by an
additional condition all morning; a restart flipped `bas` to `opn` and the cover opened
after the end-pending).

The fix is structural, and its shape is forced by two HA constraints: `!input` conditions
only evaluate at fixed YAML positions (`conditions:`/`if:`), and **variables set inside a
branch do not escape it**. So the flip *direction* — which decides *which* condition
applies — has to be a `choose:`, and everything downstream of the base state has to hang
off a shared body:

```
choose:
  - "catching up an opening"  → recovery_catch_up and recovered_base == 'opn' and helper base != 'opn'
                                + condition: !input auto_up_condition   → new_base: 'opn'  → *recovery_apply
  - "catching up a closing"   → … !input auto_down_condition            → new_base: 'cls'  → *recovery_apply
default:                        no flip, or the condition said no       → new_base: helper → *recovery_apply
```

`&recovery_apply` is a **list anchor behind `choose: [] / default:`** (the grouping idiom
already used by `helper_update`) and is defined *inside* the action tree, so Invariant 14
does not apply to it — it is never pre-rendered. All three paths run the identical body, so
refusing a flip costs **nothing but the flip**: the hygiene still runs. `recovered_state`
consumes `new_base`, not `recovered_base` — the cascade must reason about the base the gate
settled on, or the recovery would drive into a flip it just refused. (`TestCascadeParity`
therefore feeds `new_base`; the parity obligation of Invariant 13 is unchanged.)

`auto_global_condition` was and stays respected (it drops the whole recovery run).
The **ventilation / shading additional conditions are deliberately not** part of this: they
gate handlers the recovery does not replay — it re-arms a shading *pending* and lets the
existing execution flow (which does evaluate them) do the movement.

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

### Bug Pattern S: `shading_start_max_duration` budget consumed by pre-window wait (Issue #524)

**Symptom:** Shading-start conditions are met well *before* the opening time (e.g. independent-temperature mode at dawn). The pending arms, `ts.due` is correctly deferred to the window start (Bug Pattern L). Inside the window the start is gated off by an additional condition (`auto_shading_start_condition`) or unstable conditions, so the loop retries. But the retry loop aborts with `"Shading Start aborted: Timeout or invalid (blocked)"` much earlier than the configured `shading_start_max_duration` would suggest — e.g. only ~1 h of in-window retry on a 2 h budget.

**Cause:** The "Shading detected" arming branch set `ts.arm: "now"` at the (pre-window) arming moment, and the max-duration checks compute `now - helper_ts_pending_arm`. When the pending arms an hour before the window opens, that hour is counted against the budget even though no real retry happens during it (the cover only waits for the window). When `ts.due` is deferred directly to the window start, the "waiting for time window" branches (which re-anchor `ts.arm` to `now` on each pre-window retry) never run, so `ts.arm` stays at the early arming time and the budget is silently shortened.

**Fix:** In the "Shading detected" arming branch, anchor `ts.arm` to the start of the shading window when arming early. Compute a `shading_start_arm` variable mirroring `shading_start_due` but without the `+ waitingtime`/`+1`: `max(now, window_start)` where `window_start` is `today_at(time_up_early_today)` (time field) or `calendar_open_start` (calendar), and plain `now` when the window is already open or time control is disabled. The "waiting for time window" retry branches keep `arm: "now"` — they already push the anchor forward to ~window-open by re-arming every `waitingtime` seconds.

**Note:** This is distinct from the underlying *configuration* cause that usually surfaces this symptom: an `auto_shading_start_condition` that stays `false` through the whole window (e.g. "outdoor temp > 14 °C" when it is 13.7 °C) will still abort after the (now correctly-sized) budget. The additional condition is a *gate*, not a trigger — if its entity is not also a shading trigger source, a value that only crosses the threshold later in the day will not re-arm the pending.

---

### Bug Pattern T: Weather forecast not loaded on non-`t_open_1` opening triggers breaks `shading_start_warranted` (Issue #514 follow-up)

**Symptom:** A shading-start pending is armed before the opening time and the shading conditions are *still* met when the opening time fires. The cover should stay in shading (the opening handler defers to the shading execution per Bug Pattern R). Instead the cover opens normally — but only for users on **calendar-controlled opening** (`t_calendar_event_start`) or any non-`t_open_1` opening trigger (`t_open_2/4/5`). The trace shows the "Opening skipped: Shading start pending" branch was *not* selected, "Normal opening" ran, and the pending was cleared.

**Cause:** The forecast-load gate (line ~4207) only ran `weather.get_forecasts` when the trigger matched `^(t_shading_start|t_open_1)`. Other opening triggers were excluded. With the forecast not loaded, `weather_forecast` is undefined, `forecast_temp_raw` and `forecast_weather_condition_raw` fall through to `None`, and `forecast_temp_valid`/`forecast_weather_valid` evaluate to `false` whenever the user has configured those conditions. `shading_start_warranted` therefore evaluates to `false`, the "Opening skipped: Shading start pending" branch (which gates on `shading_start_warranted` per the Bug Pattern R fix) is skipped, and execution falls through to "Normal opening". `independent_temp_valid` is affected too (depends on `forecast_temp_raw`), so the independent-temperature path also breaks under the same conditions.

**Fix:** Widen the regex to `^(t_shading_start|t_open|t_calendar_event_start)` so the weather forecast is loaded on every opening-related trigger. This mirrors the top-level "Check for opening" branch gate (`^(t_open|t_calendar_event)`) plus the existing shading-start triggers, ensuring `shading_start_warranted` is evaluated against fresh forecast data whenever the opening handler may need it. The closing handler discards pending unconditionally and never reads `shading_start_warranted`, so it does not need the forecast.

**Why only this user setup hit it:** The original `t_open_1` covered the most common time-based opening. Bug Pattern R (#514, CCA 2026.06.07) added the `shading_start_warranted` gate without revisiting the forecast-load gate — the moment the user's setup uses a calendar trigger or a late/brightness/sun-elevation opening trigger, the gate's premise (forecast already loaded) silently breaks.

**Second recurrence (#603, CCA 2026.07.13 V6):** the recovery gate's `recovered_pending` is a third consumer of `shading_start_warranted`, and the resumed-run backstop (`automation_resumed`) reaches it through **any** trigger id — `t_close_*`, `t_resident_update`, the contact triggers. None of them match the gate's regex, so the forecast was again not loaded, `recovered_pending` refused a warranted shading, and the helper write cleared `automation_resumed` → the miss was permanent for that day. Fix: the gate matches `automation_resumed` in addition to the trigger ids.

**Third recurrence (CCA 2026.07.13 V6):** the **calendar-load gate** two steps below the forecast gate had the identical shape and was nearly missed by the forecast fix above: its trigger-id allow-list (`^t_open`, `^t_close`, `^t_shading_start`, `^t_shading_end`, `^t_calendar_event`) matched neither `t_recovery` nor a resumed run. For calendar-controlled users the recovery therefore ran without `calendar_open_start`/`calendar_close_start`: the calendar clauses of `is_daytime_phase`/`is_evening_phase` rendered false, `recovered_base` silently fell back to the stale helper (the orphan-audit row "missed calendar opening/closing → repaired by `recovered_base`" was dead code for exactly these users), and `recovered_due`/`recovered_arm` lost the window-start deferral (Bug Pattern L family). Fix: the gate's OR gets `trigger.id == 't_recovery' or automation_resumed`, mirroring the forecast gate. Tests: `test_calendar_events_are_loaded_for_the_recovery`, `test_calendar_events_are_loaded_on_a_resumed_run_claimed_by_any_trigger`.

**Rule (the recurring shape):** whenever a new code path consumes `shading_start_warranted` — or any variable that depends on the forecast **or on the parsed calendar events** — check *which trigger ids can reach it*. A trigger-id allow-list upstream of a value-based consumer breaks silently every time the set of reaching triggers grows. `tests/test_restart_recovery.py::TestRecoveryTriggers::test_forecast_is_loaded_on_a_resumed_run_claimed_by_any_trigger` pins the resumed-run case.

---

### Bug Pattern U: Shading start skipped when cover sits below the shading position (Issue #530)

**Symptom:** Shading conditions are met *before* the opening time, so at opening time the cover is still fully closed (position `0`). The opening handler correctly defers to `t_shading_start_execution` (Bug Pattern R), but the execution then does nothing: no drive, no helper write, `shd` stays `0`, `pnd` stays `'beg'`. The cover hangs closed all morning and the slats never tilt into the shading angle. Trace shows the execution reaching the inner drive `choose` with **all** branches false (`Consider lockout` / `Start Shading` / `Save shading state for the future`), then falling off the end with no `stop`.

**Cause:** The "Start Shading" branch position guard (line ~5437) only allowed driving *downward* to the shading position: `current_above_shading` (and, for tilt covers, `current_above_shading or current_position == shading_position`). With `shading_position` above `close_position` (e.g. `3` vs `0`), a fully-closed cover is **below** the shading position → `current_above_shading` is false and `current_position != shading_position` → the guard fails. "Consider lockout" needs an open window (false here) and "Save shading state for the future" needs `effective_state == 'cls'` — but after the opening trigger set `bas: 'opn'`, `effective_state == 'opn'` (shading not yet active, `shd == 0`). All three branches miss → dead zone.

**Fix:** Add a third alternative to the "Start Shading" position-check OR: drive when the cover is **below** the shading position **and** the base state wants it open (so shading must cap an otherwise-open cover by *raising* it to the shading position):
```yaml
- and:
    - "{{ position_comparisons.current_below_shading }}"
    - "{{ effective_state == 'opn' }}"
```
The `effective_state == 'opn'` gate is essential: when `effective_state == 'cls'` (base closed, e.g. overnight) the cover must stay closed and "Save shading state for the future" stores the intent without driving — do **not** raise the cover at night. This mirrors the opening handler's "Shading detected. Move to shading position" branch, which already drives from any direction via `not in_shading_position`.

---

### Bug Pattern V: "Shade only once per day" never blocks for users who don't touch the cover by hand

**Symptom:** With `prevent_shading_multiple_times` enabled, the cover still shades multiple times a day. After the morning shading ends (sun leaves the facade, cover returns to open), the afternoon shading conditions re-trigger and the cover shades **again**. The repeated shading-end movements also make the cover appear to *open* multiple times (shade → open → shade → open).

**Cause:** The once-per-day guard was

```jinja2
prevent_flags.shading_multiple_times and ((now().day != helper_ts_shade|timestamp_custom('%-d')|int) or helper_ts_man <= helper_ts_shade)
```

The second OR-clause `helper_ts_man <= helper_ts_shade` ("no manual change happened after the last shading") is **always true** when the user never moves the cover by hand, because `ts.man` defaults to `0` and `0 <= ts.shd` holds for any non-zero `ts.shd`. The day-check is therefore short-circuited and the guard never blocks a second shading. The clause was originally added for the opening/closing guards to handle `ts.opn`/`ts.cls` being polluted by non-driving base-state syncs (Issue #311) — but for shading it only disables the feature.

**Fix:** Drop the manual clause for shading and make the guard purely calendar-based, comparing the **full date** (not just day-of-month, which collapsed across months and treated a fresh `ts.shd == 0` as "day 1"):

```jinja2
prevent_flags.shading_multiple_times and now().strftime('%Y-%m-%d') != helper_ts_shade | timestamp_custom('%Y-%m-%d')
```

The `t_shading_start_execution` bypass (third OR-clause) is kept so an already-armed pending can still execute. Manual override is still respected via the separate `not (helper_state_manual and override_flags.shading)` gate.

**`ts.shd` is the only consumer of this guard, and it is not polluted like `ts.opn`/`ts.cls`** — it changes only on a real `shd` 0↔1 transition (Invariant 8). The opening/closing guards **keep the manual clause** because their timestamps *are* polluted by non-driving syncs, so removing the clause there would reintroduce Issue #311. The user-reported "opening multiple times" symptom is a side-effect of the shading loop, not an independent opening bug.

**The date compare in the opening guard was fixed separately.** It used `now().day != helper_ts_open | timestamp_custom('%-d') | int` — a **day-of-month** compare, which collapses across months: a `ts.opn` from exactly one month ago reads as "already opened today" and suppresses the opening. It now compares the full date (`'%Y-%m-%d'`), like the shading guard. This is orthogonal to the manual clause, which stays. The **closing** guard needs no fix — it compares `helper_ts_close < today_at(time_down_early_today)`, which is already date-safe.

**Why the midnight reset (BRANCH 11) needs no special handling:** `t_shading_reset` fires at **23:55 the same day** (`now() >= today_at('23:55:00')`), so even though it clears `shd` 1→0 and writes `ts.shd: "now"`, the stamp lands on the *current* day — never the next one. The full-date guard compares `ts.shd`'s day against today, so the following day is still a different date → shading is allowed. The old CHANGELOG #365 failure (reset stamping the *new* day and blocking it) cannot occur with the 23:55 trigger; no `ts.shd` omission is required.

---

### Bug Pattern W: Shading-tilt adjustment ignores resident `allow_shade`

**Symptom:** With `resident_allow_shading` **unset** ("Allow sun protection when resident is still present" disabled) and a resident present, the cover still tilts its slats into the shading position. The helper shows `shd=1` and `res=1` but the cover visibly enters shading mode despite the resident block.

**Cause:** When the shading-start conditions are met while a resident is present, the execution handler's "Save shading state for the future" branch (gated by `not resident_flags.allow_shade`) stores the intent — `shd: 1`, `pnd: 'non'`, no drive. This makes `helper_state_is_shaded` true. A subsequent `t_shading_tilt_*` trigger then enters the "Check for shading tilt" branch, which gated on `is_shading_enabled`, `helper_state_is_shaded`, tilt-possible, `auto_shading_tilt_condition`, `force_allows_shade`, window-closed and manual-override — but **not** on `resident_flags.allow_shade`. So `*tilt_move_action` drove the slats into the shading angle while the resident was present.

**Fix:** Add `- "{{ resident_flags.allow_shade }}"` to the "Check for shading tilt" branch conditions, matching every other shading-drive branch (start execution #5459, shading-end #5680, resident-leaving SHADED #6303, force-recovery SHADING #6947, and the inline equivalent in "Window closed - Return to shading" #6123).

**Rule:** Every branch that physically moves the cover (position *or* tilt) into the shading position must gate on `resident_flags.allow_shade`. The shading-tilt adjustment is a shading movement, not an exception.

---

### Bug Pattern X: Closing handler re-drives ventilation on every closing trigger (Issue #538)

**Symptom:** The cover is in the ventilation position because the window is tilted. A subsequent closing trigger — typically the sun-based `t_close_5`, which fires repeatedly through the evening closing window — re-drives the cover to the ventilation position again (`set_cover_position` + `set_cover_tilt_position`) instead of leaving it alone. The user sees the cover "override the ventilation position" and end in an undefined position on every trigger.

**Cause:** The close handler's "Window tilted. No lockout. Move to ventilation position instead of closing" branch (line ~5197) drove **unconditionally** whenever `force_allows_ventilate` was true:

```yaml
- if: "{{ force_allows_ventilate }}"
  then: ...drive position + tilt...
```

The close handler already has an idempotent "Already in close position - only update base state" branch, but had **no** equivalent guard for the ventilation case. The contact handler's ventilation-start branches (line ~6288 / ~6417) already used the correct guard. This was an asymmetry, not a deliberate design.

**Fix:** Mirror the contact handler — gate the drive (and the `man: 0` reset) on `(effective_state != 'vnt' or not in_ventilate_position)` in the `if:`, per Invariant 1 (position check in the drive guard, not the branch conditions). The `*helper_update` still always runs:

```yaml
man: "{{ 0 if force_allows_ventilate and (effective_state != 'vnt' or not in_ventilate_position) else helper_json.man | default(0) | int }}"
if: "{{ force_allows_ventilate and (effective_state != 'vnt' or not in_ventilate_position) }}"
```

This also fixes an incidental Invariant 7 violation (the old `man: 0` fired even when no drive happened).

**Config caveat (not solvable by the blueprint alone):** On tilt/venetian covers the tilt movement changes the reported `current_position`, so the cover may rest at a position several points away from the configured `ventilate_position` (Issue #538: commanded position `6` + tilt `100` → reported position `10`). With a tight `position_tolerance` (e.g. `1`), `in_ventilate_position` stays `false`, so even the new guard keeps re-driving. The user must raise `position_tolerance` (or adjust `ventilate_position`) so the cover's resting position is recognized as "in ventilation position". The blueprint guard removes the *redundant* re-drive only once the cover is recognizable as vented.

---

### Bug Pattern Y: Manual move to the reset position swallowed when no override is active (Issue #546)

**Symptom:** With *"Reset in position"* enabled (`reset_override_config` contains `reset_in_position`, e.g. `reset_override_position = 100`), the user manually moves the cover to the reset position while CCA is in **automatic** mode (`man == 0`). The helper never records a manual change (`man` stays `0`, `ts.man` unchanged). A later event — typically closing a tilted window — then drives the cover to the scheduled/`effective_state` position instead of holding the position the user just set by hand. The user reports "I opened the cover manually but it did not change the helper" and "the cover closes when I close the window".

**Cause:** The manual-detection branch ("Checking for manual position changes") condition

```yaml
- "{{ not (trigger.id == 't_manual_position' and in_reset_override_position) }}"
```

suppressed **every** manual position trigger fired while the cover is within tolerance of the reset position — regardless of `man`. But the matching reset trigger `t_reset_position` (line ~3941) only fires when `helper.man | int == 1`. This asymmetry creates a dead zone: when `man == 0`, a manual move to the reset position is **neither** recorded as a manual change (suppressed by the condition) **nor** cleared by a reset (`t_reset_position` needs `man == 1`). The move is lost, the base state is never synced, and `effective_state` continues to reflect the old schedule.

**Fix:** Gate the suppression on `helper_state_manual`, matching the `t_reset_position` precondition:

```yaml
- "{{ not (trigger.id == 't_manual_position' and in_reset_override_position and helper_state_manual) }}"
```

- `man == 1` + move to reset position → still suppressed. This is the *"reopen to the reset position to resume automatic control"* gesture (the feature's intent, #506): detection stays quiet and `t_reset_position` clears the override after the dwell time. **Unchanged.**
- `man == 0` + move to reset position → now detected as a normal manual change. The base state is synced (directly via the "Manual: opened/closed" sub-branch, or — when the open position is not recognized because the relevant `auto_*` is disabled — via the reset handler's "restore OPEN/CLOSE base state" after the dwell). Subsequent events then follow the correct `effective_state`.

**Rule:** A manual-detection suppression that exists only to mute a *reset gesture* must carry the same precondition as the reset it is muting. Suppressing detection when there is nothing to reset silently discards a real manual change.

**Config note:** Choosing `reset_override_position = 100` (= open) intentionally means "moving the cover fully open resumes automatic control" — so once the override has been cleared the cover follows the schedule again. The fix only ensures the *first* manual move (while `man == 0`) is no longer dropped; it does not turn the open position into a permanent manual hold.

---

### Bug Pattern Z: Tilted-window ventilation never triggers in a schedule-less setup (Issue #553)

**Symptom:** In a **shading-only** setup with no open/close schedule (`auto_options` has neither `auto_up_enabled` nor `auto_down_enabled`, `time_control: time_control_disabled`), a tilted or opened window **never moves a closed cover to the ventilation position**. This worked in v5. The helper shows `bas: 'opn'`, `win: 'tlt'`, and the cover sits at the closed position with no movement. The contact handler's "Window tilted - No drive, sync helper window state" branch (which gates on `effective_state == 'opn'`) catches the event and only syncs `win: 'tlt'` — the drive branch ("Window tilted - Partial ventilation", gated on `effective_state != 'opn'`) is skipped.

**Cause:** `bas` initializes to `'opn'` in every init path (fresh init, v6 parse fallback `default('opn')`, v5 migration unless the v5 state was explicitly `close`) and is **only ever** switched to `'cls'` by the scheduled close handler (`t_close_*`, which needs `auto_down_enabled` + a time/calendar source). Without a schedule, `bas` stays `'opn'` forever → `base_target == 'opn'` → the VENT floor condition (`base_target != 'opn'`) is never true → a closed cover ignores a tilted window. The `2026.05.24` changelog had documented "remove the time schedule (so `bas` never reaches `opn`)" as the way to restore v5 behavior — but removing the schedule does **not** make `bas` non-`opn`, so that workaround never worked.

**Fix:** Gate the BASE=OPN-beats-VENT rule on whether an opening automation actually exists. New `trigger_variables` flag (the `not is_time_control_disabled` clause shipped here was too narrow — see Bug Pattern AL for the current definition):

```yaml
is_opening_scheduled: "{{ is_up_enabled and not is_time_control_disabled }}"
```

In `effective_state`, replace the VENT floor condition:

```jinja2
{% set base_open_scheduled = base_target == 'opn' and is_opening_scheduled %}
{% if w == 'tlt' and allow_vent and not base_open_scheduled %}
  vnt
{% else %}
  {{ base_target }}
{% endif %}
```

This is **surgical** — it only changes the VENT-floor decision. When the window is **not** tilted, `effective_state` still returns `'opn'` for `bas == 'opn'`, so shading-end (gated on `effective_state != 'cls'`), the contact "return to open" branch, and every other base=opn consumer are unaffected. Scheduled setups (`is_opening_scheduled == true`) keep the `2026.05.24` BASE=OPN-beats-VENT behavior unchanged.

**Why not Option 1 (treat `bas` as `'cls'` for the whole cascade):** That was the maintainer's originally-documented intent, but making `effective_state` return `'cls'`/`'vnt'` wholesale breaks the shading-end handler, whose branch gate is `effective_state != 'cls'` — shading would never end. The VENT floor must be the *only* thing affected; gating just that line is the correct minimal change.

---

### Bug Pattern AA: Global trigger gate makes the #554 end-pending cancel unreachable (Issue #554)

**Symptom:** Shading-end is pending (`pnd == 'end'`). During the end waiting time the shading conditions are met again (sun comes back), so per the documented guarantee — *"Shading ends if one of the conditions is not fulfilled for the entire waiting time"* — the pending end should be canceled. The dedicated cancel branch ("Shading re-detected. Cancel pending shading end", added for #554) exists in the actions, but never runs: no trace is even recorded for the `t_shading_start_pending_*` trigger. If the end conditions happen to be met again at `t_shading_end_execution` time, shading ends regardless of the interruption.

**Cause:** The global trigger gate (conditions block, "GLOBAL CONDITIONS") suppresses `t_shading_start_pending_[1-6]` whenever the helper shows `shd == 1` — its purpose is noise suppression (don't re-run the automation for start triggers while shading is already active). But during an end-pending, `shd` is *always* still `1` (shading stays active until the end executes). The gate therefore stopped the automation before the actions ran, making the #554 cancel branch dead code in exactly the scenario it was written for.

**Fix:** The gate lets `t_shading_start_pending_[1-6]` through when the helper shows an armed end-pending (`"pnd"\s*:\s*"end"` regex — value `"end"` is unique to `pnd`, no other field can hold it):

```jinja2
{% set is_shaded = helper not in invalid_states and helper | regex_search('"shd"\s*:\s*1\s*[,}]') %}
{% set is_end_pending = helper not in invalid_states and helper | regex_search('"pnd"\s*:\s*"end"') %}
{{ not is_shaded or is_end_pending }}
```

Additionally, the "Check for shading start" branch entry OR ("Check the helper status or the target status") gets `helper_state_pending_end` as a third alternative — matching the two escape hatches the earlier #554 fixes already added to the position-check OR and the once-per-day OR — so the cancel is also reachable while the window is open/tilted (an end-pending can arm with the window open; the contact handler holds lockout/vent, but the interruption must still cancel the pending).

**Rule:** A fix in the actions is only real once every gate *upstream* of it (trigger `enabled`, trigger `for`, **global conditions**, branch conditions) provably lets the triggering event through in the exact scenario being fixed. When adding an action branch keyed to a trigger id, always re-check the global trigger gate for that id.

**Deliberate asymmetry (reporter's "FWIW"):** The gate still suppresses `t_shading_end_pending_[1-7]` while shading is inactive (`shd == 0`), even though a shading-**start** pending may be armed. This is intentional: the start side is documented as a *retry loop* ("After the waiting time expires, the automation re-evaluates ALL configured conditions. Only if they are still valid at this point, the cover actually moves") — momentary interruptions during the start wait are tolerated by design, and the execution re-check plus `shading_start_max_duration` budget already handle unmet conditions. Canceling a start-pending on an end trigger would also break the pre-window arming flows (Bug Patterns L/S/R). Do not "harmonize" the end side of the gate.

---

### Bug Pattern AB: Opening deferred to Shading End although shading is inactive (Issue #565)

**Symptom:** The cover sits at the shading position at opening time while the helper shows `shd: 0` and `pnd: 'non'` (e.g. the user moved it there manually, or positions happen to coincide). The opening trigger fires, the trace ends with `"Open time: In shading position, base state updated (movement via Shading End)"`, and the cover never opens — it stays at the shading position for the rest of the day.

**Cause:** The "Normal opening of the cover" branch guarded only on `not in_shading_position` — the physical position alone — assuming that a cover at the shading position is *shaded* and the Shading End flow will open it later. Execution fell through to the default branch, which only sets `bas: 'opn'` and defers the movement. But with `shd == 0` that handoff is impossible: the global trigger gate suppresses all `t_shading_end_pending_[1-7]` triggers unless the helper contains `"shd":1` — the gate upstream makes the deferral dead code (Bug Pattern AA territory).

**Fix:** Gate the deferral on the helper's actual shading state:

```yaml
- "{{ not in_shading_position or not helper_state_shade }}"
```

With `shd == 1` + in shading position, the default branch still defers to Shading End (whose triggers pass the global gate because `shd == 1` — the handoff works). With `shd == 0`, "Normal opening" fires and drives the cover open. This also covers the stale-pending case (`pnd == 'beg'`, `shd == 0`, cover at shading position, conditions no longer warranted): Bug Pattern R's fall-through now genuinely reaches the drive instead of dead-ending in the default branch.

**Rule:** A deferral to another flow must be gated on the *helper state* that makes that flow reachable, never on the physical position alone. Position says where the cover is; only the helper says *why* — and the "why" decides which flow owns the next movement (same family as the Bug Pattern AA rule: verify the receiving flow's upstream gates actually let it run).

---

### Bug Pattern AC: Force-disable recovery reads window contacts without the ventilation gate (Issue #566)

**Symptom:** Ventilation automation is disabled (`auto_ventilate_enabled` not in `auto_options` — e.g. because a defective tilt sensor permanently reports "tilted"). Shading is active, the cover sits at the shading position. A force function is turned off → the recovery drives the cover to the **ventilation position** although ventilation is disabled and the tilt sensor should be ignored entirely.

**Cause:** When the ventilation automation is disabled, the contact sensors are ignored throughout CCA — the contact triggers carry `enabled: "{{ is_ventilation_enabled and ... }}"`, the contact handler, the closing-lockout branch, the shading-end lockout/ventilation branches and the resident-handler ventilation branches all gate on `is_ventilation_enabled`. The force-disable recovery branches, however, read `states(contact_window_opened)` / `states(contact_window_tilted)` **directly** and bypassed that gate: the "return to VENTILATION (window tilted)" branch drove to the ventilation position, and the negative window checks in "return to CLOSE / SHADING / OPEN (base=opn)" blocked those branches on a (stuck) contact. Only the sibling "return to OPEN (window open — lockout)" branch already checked `is_ventilation_enabled`.

**Fix:** Apply the gate to every direct sensor read in the recovery `choose`:

- "return to VENTILATION (window tilted)": add `- "{{ is_ventilation_enabled }}"` (mirrors the lockout recovery branch).
- "return to CLOSE (base=cls)", "return to SHADING", "return to OPEN (base=opn)": scope the window-contact exclusions, e.g. `not (is_ventilation_enabled and contact_window_tilted != [] and states(contact_window_tilted) in ['true', 'on'])`.

With ventilation disabled, the recovery now falls through to the correct shading/open/close target instead of driving to ventilation or dead-ending in the recovery `default:` (which would clear `frc` without any movement).

**Second recurrence (CCA 2026.07.13 V6) — the restart recovery, and the scoping moved into the cascades.** The restart-recovery gate's `recovered_window` read the contacts unscoped too, and unlike `effective_state` (whose `'vnt'`/`'lock'` consumers all gate in their branches) it **drives directly** on the result: with ventilation disabled and a stuck contact, every restart *and every save of the automation* drove the cover to the ventilation position — or to open via `'lock'`, which additionally overrules a manual override (`recovery_allowed` passes on `recovered_state == 'lock'`). Ironically, `lockout_blocks_shading` three lines below was already scoped. The fix applies the AC rule at the *source*: the live-contact reads inside **both** `effective_state` and `recovered_window` are scoped to `is_ventilation_enabled` (one commit, Invariant 13), so `w` is `'cls'` while ventilation is disabled and contacts are configured. The no-contacts helper fallback (`h.win`) is untouched — a user driving `win` via the helper alone keeps working. Tests: `TestRecoveredWindow::test_ventilation_disabled_means_the_contacts_do_not_exist`, plus three vent-disabled rows in `TestCascadeParity`.

**Rule:** Every direct `states(contact_window_opened/tilted)` read in a branch condition or drive guard must be scoped to `is_ventilation_enabled` — since CCA 2026.07.13 V6 the cascade-internal `w` derivations (`effective_state`, `recovered_window`) enforce this at the source. When the ventilation automation is disabled, the window contacts do not exist as far as CCA is concerned — this includes lockout (the trigger gate already treats it that way). Note this is about the feature toggle `auto_ventilate_enabled`, not the resident flag `resident_allow_ventilation` (Invariant 6 remains untouched).

---

### Bug Pattern AD: Calendar title gate on `message` attribute misses concurrent events (Issue #568)

**Symptom:** One calendar carries two events with **different titles but the same start time** (e.g. "Open Cover" and "Open Schlafraume", both Saturday 08:30, driving different CCA instances). Only one automation runs; the other is stopped by the global conditions (trace: "Stopped because a condition failed", runtime ~0.04 s) and its cover never opens.

**Cause:** The global conditions gated `t_calendar_event_*` triggers on `state_attr(calendar_entity, 'message')` matching `calendar_open_title` or `calendar_close_title`. A calendar entity's `message`/`start_time`/`end_time` attributes only ever expose a **single** (current-or-next) event — with two simultaneous events, HA picks one and the other is invisible. The automation whose title matched the hidden event was suppressed. The same attribute-based gate also failed at an event **end** when no upcoming event exists (`message` is `none`).

**Fix:** Remove the title check from the global conditions entirely — a condition context cannot call `calendar.get_events`, and the `message` attribute is structurally unable to represent concurrent events. The precise check lives in the actions instead ("Calendar trigger relevance check", directly before the main `choose:`): after `calendar.get_events` has loaded today's events and the variables block has parsed them per title (`calendar_open_event`/`calendar_close_event` → `calendar_open_start/end`, `calendar_close_start/end`), the step `stop`s calendar-triggered runs when **none** of the automation's own parsed event boundaries caused the state transition:

```jinja2
{% set flip_to = as_timestamp(trigger.to_state.last_changed) %}
{% set flip_from = as_timestamp(trigger.from_state.last_changed) if trigger.from_state is not none else 0 %}
boundary is relevant iff flip_from < boundary <= flip_to + 60
```

The interval `(flip_from, flip_to + 60]` — previous on/off flip to current flip plus tolerance — is used instead of a plain "boundary == now" comparison for two reasons: `mode: queued` can delay execution well past the trigger (so `now()` is unusable), and a lagging calendar integration can flip the entity state after the nominal event boundary (so a tight tolerance around `flip_to` alone could false-negative). The asymmetry is deliberate: a false **pass** merely costs an idempotent no-op run (the opening/closing branches still gate on `is_opening_phase`/`is_closing_phase` etc.), while a false **stop** silently loses an open/close — so the gate is generous.

**Why not `trigger: calendar` platform triggers (which expose `trigger.calendar_event.summary`):** `calendar_entity` defaults to `[]`, and the calendar trigger schema (`cv.entity_id`) rejects a list — the blueprint would fail validation for every user without a calendar. `enabled:` does not skip schema validation. The state triggers (`to: "on"` / `to: "off"`) must stay.

**Known limitation (unchanged):** the state trigger only fires on real `off`↔`on` transitions of the calendar entity. If a matching event starts while another event is already running (overlap, not same-start), the entity stays `on` and **no trigger fires at all** — that is a trigger-level gap this action gate cannot close.

**Rule:** Never gate calendar-trigger relevance on the calendar entity's state attributes — they show one event only. Relevance must be decided against the `calendar.get_events` result (same family as Bug Pattern AA: the gate upstream must provably let the event through in the scenario being handled).

---

### Bug Pattern AE: Shading start ignores the ventilation floor when the window is already tilted

**Symptom:** With a window **tilted** (not fully open) and `shading_position` below `ventilate_position` (e.g. shading 30, vent 50), the cover drops to the **shading position (30)** when shading starts — below the ventilation floor. It should hold the **ventilation position (50)** while the window is tilted and only move to the shading position once the window is closed.

**Cause:** The shading-start execution had no VENT-floor handling. Its only drive branch, "Start Shading", drove straight to `shading_position` regardless of a tilted window. `effective_state` correctly returns `'vnt'` for tilted + shading (VENT prio 4 > SHADING prio 6), and the **contact handler** holds the floor for the reverse order (shade first, then tilt) — but the shading-start path did not. So the bug only manifested in the order **tilt first, then shading starts** (the reverse order was already correct).

**Fix:** New branch "Shading start - hold ventilation floor (window tilted)" placed **before** "Start Shading" in the execution `choose`. It fires when the window is tilted (and not opened — Invariant 5), ventilation is enabled and force/resident-allowed, shading is resident-allowed, and `position_comparisons.shading_below_ventilate` holds. It drives to `ventilate_position` / `ventilate_tilt_position`, sets `shd: 1`, `win: 'tlt'`, clears pending (`pnd: 'non'`, `ts.due: 0`, `ts.arm: 0`), and sets `man: 0` only when it actually drives (`not in_ventilate_position`, Invariant 7). When the window later closes, the contact handler's "Window closed - Return to shading" lowers the cover to the real shading position.

**Scope:** Only the common case `shading_position` below `ventilate_position` is floored (`position_comparisons.shading_below_ventilate`). When `shading_position` is at/above `ventilate_position` the floor does not bind and "Start Shading" drives to the shading position as before. The `lockout_tilted_shading_start` option still takes precedence (treats a tilted window like a fully-open one → cover stays open during shading). The latent `effective_state == 'vnt'` divergence for the rare `shading_position` *above* `ventilate_position` config is intentionally left untouched (out of scope, not the reported case).

---

### Bug Pattern AF: Unconfigured status helper kills variable rendering before the friendly config check

**Symptom:** With the mandatory `cover_status_helper` not configured, every run of the automation dies at trigger time with `Error rendering variables: TypeError: cannot use 'list' as a dict key (unhashable type: 'list')` (Python ≥ 3.13 wording of "unhashable type"). The actions' "MANDATORY HELPER VALIDATION" block — which exists precisely to log a clear "Cover Status Helper is required but not configured" error and stop — never runs, because the top-level `variables:` block is rendered *before* the actions and aborts the run.

**Cause:** `helper_json` called `states(cover_status_helper)` without a `!= []` guard. The input's `default: []` makes the argument a list, and `hass.states.get([])` fails on the dict lookup. Every other state read in the `variables:` block already carried the `x != [] and states(x)` guard — `helper_json` was the single unguarded one. The same unguarded read existed in trigger templates (`t_shading_start/end_execution`, `t_shading_tilt_*`, `t_reset_timeout`, `t_reset_position`), the global conditions (shading pending gate), and the v5→v6 migration check in the actions.

**Fix:** Guard every reachable `states(cover_status_helper)`: in `helper_json` and the global-conditions gate via `... if cover_status_helper != [] else 'unavailable'` (falls through to the existing invalid-state handling → fresh default JSON), in the migration check via a preceding `{{ cover_status_helper != [] }}` condition, and in the helper-reading triggers via `and cover_status_helper != []` in their `enabled:`. With no helper configured the run now reaches the mandatory validation, logs the friendly error, and stops.

**Rule:** Every `states(x)` / `state_attr(x, ...)` on an input whose `default` is `[]` must be guarded with `x != []` (short-circuit) — in *every* context: `variables:`, trigger `value_template`s, global conditions, and action conditions. This is the same upstream-gate family as Bug Pattern AA: a user-facing validation in the actions is dead code if variable rendering upstream can throw first.

---

### Bug Pattern AG: Opening deferred into shading while the lockout window is open (2026.06.28 V3 regression, forum report)

**Symptom:** The lockout window is **fully open** (or **tilted** with `lockout_tilted_shading_start` enabled) at the scheduled opening time and the shading conditions are met. The cover does not open — it stays at its current position (e.g. still closed after a force function or restart) for the rest of the morning. The trace ends with `"Opening: Shading pending armed"` (or `"Opening skipped: Shading start pending"`), and the later shading execution ends with `"Shading Start skipped: Lockout enabled"`.

**Cause:** The opening handler has two branches that hand the movement over to the shading execution instead of opening: "Opening skipped: Shading start pending" (defer, Bug Pattern R) and "Opening: Shading warranted, arm pending" (#555, new in `2026.06.28 V3`). Neither checked the window contacts. But the shading execution's "Consider lockout protection when shading starts" branch only **stores** the intent (`shd: 1`, `win: 'opn'`) and stops — it never drives the cover. So with the lockout active, the receiving flow can never satisfy the opening obligation: the handoff dead-ends and the cover stays below the open position although `effective_state == 'lock'` demands it. The #555 branch made this common (it fires on every sunny morning with an open window at opening time); the defer branch had the same gap since #514 for a pending armed pre-window.

**Fix:** Both branches gate on the same lockout-window check as the execution's "Consider lockout" branch (scoped to `is_ventilation_enabled` per Bug Pattern AC):

```yaml
- "{{ not (is_ventilation_enabled and ((contact_window_opened != [] and states(contact_window_opened) in ['true', 'on']) or (lockout_tilted_when_shading_starts and contact_window_tilted != [] and states(contact_window_tilted) in ['true', 'on']))) }}"
```

When the lockout applies, execution falls through to "Normal opening", which drives the cover open (a no-op via the `cover_move_action` tolerance guard when the contact handler already opened it) and clears `pnd`/`ts.due`/`ts.arm`. A plain tilted window **without** the `lockout_tilted_shading_start` option still arms/defers — the execution then holds the ventilation floor (Bug Pattern AE) or shades, as designed. Trade-off: the stored-shading-intent handoff (window closes later → "Return to shading") is not established in the lockout case; shading starts when the next shading trigger re-fires. That restores the pre-`2026.06.28 V3` behavior — lockout safety beats remembered shading.

**Rule:** A handoff into another flow must be gated on what the receiving flow can actually *do* in that scenario — the shading execution's lockout branch stops without movement, so it can never fulfill a deferred opening. Same family as Bug Pattern AB (gate deferrals on the receiving flow's reachability) and AA (verify the receiving flow's upstream gates).

---

---

### Bug Pattern AH: Time-control disable path unreachable through the UI (Issue #544)

**Symptom:** Unchecking the *"⏲️ Time Control"* checkbox in `auto_options` has no effect for installations created after the options consolidation (~2026.05). Brightness-/sun-only setups stay gated by the default Early/Late time windows; there is no way to disable time control through the UI.

**Cause:** `is_time_control_disabled` required **both** `'time_control_enabled' not in auto_options` **and** `'time_control_disabled' in time_control` — but the `time_control` selector no longer offered a `disabled` option, so the second clause could never become true for new installs. The state "`time_control_enabled` missing from `auto_options`" is ambiguous by itself: it means either "legacy pre-consolidation install (keep time control)" or "new user deliberately unchecked (wants it off)" — the checkbox alone cannot be made authoritative without silently disabling time control for every legacy install.

**Fix (maintainer decision — deliberate breaking change):** The `time_control_enabled` checkbox in `auto_options` is the single authoritative switch; the legacy `time_control` selector only picks the *source* (time fields vs calendar) and its old `time_control_disabled` value is no longer evaluated:

```yaml
is_time_control_disabled: "{{ 'time_control_enabled' not in auto_options }}"
is_time_field_enabled: "{{ 'time_control_enabled' in auto_options and 'time_control_input' in time_control }}"
is_calendar_enabled: "{{ 'time_control_enabled' in auto_options and 'time_control_calendar' in time_control and calendar_entity != [] }}"
```

Gating `is_time_field_enabled`/`is_calendar_enabled` on the checkbox is essential: the time/calendar triggers carry `enabled: "{{ is_time_field_enabled }}"` / `is_calendar_enabled`, so without the gate the Late trigger would still fire while time control is "disabled". The checkbox stays in the `default:` list (new installs get the Late safety net by default). The `time_control_disabled` option is **not** offered in the dropdown — one switch, one mechanism. Pre-consolidation configs that had chosen `time_control_disabled` remain disabled (checkbox absent), matching their original intent. The config validator (`docs/validator/validator.js`) mirrors the logic and warns about the breaking change.

**Accepted breakage:** Pre-consolidation installs with `time_control_input`/`time_control_calendar` (no `time_control_enabled` stored) silently lose time control after the update until the automation is re-saved with the checkbox enabled — for pure time-schedule users this stops opening/closing entirely. The ambiguity ("value missing = legacy install or deliberate uncheck") cannot be resolved from stored data; the maintainer chose the clean end state over keeping a permanently ambiguous hybrid clause, with prominent CHANGELOG/FAQ communication instead of silent compat.

**Rule:** When one UI input must be authoritative and the stored data cannot distinguish legacy absence from deliberate absence, do not encode the ambiguity into a hybrid AND-clause forever — pick the authoritative input, document the one-time breakage loudly, and make every dependent flag (`is_time_field_enabled`, `is_calendar_enabled`, trigger `enabled:` gates) follow the same single switch.

---

### Bug Pattern AI: Unavailable cover corrupts the helper via the 101 position sentinel

**Symptom:** After a HA restart or an outage of the cover integration, CCA keeps reacting to time/sun/contact triggers while the cover itself is `unavailable`. Symptoms vary: movements are silently skipped (the cover is mistaken for "already open"), runs abort mid-sequence with `HomeAssistantError: Entity cover.x is not available` so the helper is never written, and — the worst case — a helper write derived from the bogus position **overwrites a still-correct state**, e.g. an active shading (`shd: 1`) from before the restart.

**Cause:** The global conditions only validated the **triggering** entity (`trigger.to_state.state not in invalid_states`). The cover was never checked. With the cover unavailable, `state_attr(blind, 'current_position')` is `None` and `current_position` falls back to the `101` sentinel — which is not a neutral value: `|101 − open_position(100)| ≤ position_tolerance(5)` makes `in_open_position` **true**. So the automation reasons about a cover that "is open" and persists conclusions drawn from a phantom position.

**Fix:** A global condition over `critical_entities` — every entity whose invalid state would make the cascade compute a *wrong* target must be usable, not just the trigger source. Use the shared `invalid_states` constant, **not** `!= 'unavailable'`: an `unknown` entity (restart before restore, deleted entity) is just as broken. Paired with the `t_recovery` trigger set + the recovery gate, because a blocked automation silently loses every event of the outage window. See the design decision *"Restart / outage handling: block on state-critical entities, recover via `t_recovery`"* for the entity list, the group semantics, why condition-only sensors are excluded, and why the check is on the **state** and not on the position sentinel.

**Rule:** A guard that stops the automation from acting on bad data must be paired with a way to *catch up* once the data is good again — otherwise the guard converts a corruption bug into a silent-miss bug. Blocking is only half a fix; the recovery path is the other half. And the guard must cover *every* input the cascade reads, not just the one that surfaced the bug: a dropped window contact reads as "closed" and silently disables the lockout exactly like a dropped cover reads as "open".

---

### Bug Pattern AJ: Shading-end tilt-only branch outranks lockout/ventilation and hardcodes the open tilt (Issue #583)

**Symptom:** With *"Stay shaded: Don't open cover when sun shading ends"* (`prevent_opening_after_shading_end`) **and** *"Using the ventilation position when the sun shading is ended"* (`ventilation_after_shading_end`) both enabled, a window **tilted** at shading end leaves the cover at the shading position with slats tilted to 50 — instead of moving to `ventilate_position`/`ventilate_tilt_position`. Independently, the tilt-only slat angle ignored the configured `open_tilt_position` (hardcoded `50`; the input's default is also 50, so only users who changed it noticed).

**Cause A (ordering):** "Only tilt open after shading ends" was placed **before** "Lockout protection when shading ends" and "Ventilation after shading ends" in the shading-end execution `choose:` and carries no window-contact condition — it consumed every execution run on tilt covers with the prevent flag set, swallowing the higher-cascade LOCKOUT (prio 2) and VENT (prio 4) branches (same family as Bug Pattern AA/AB: a correct branch is dead code when an earlier branch consumes its scenario).

**Cause B (hardcoding):** `target_tilt_position: 50` instead of the `open_tilt_position` input, despite the comment "Moving the cover to open tilt position".

**Fix:** Reorder the execution `choose:` to pending → lockout → ventilation → tilt-only → move-cover (cascade order), and use `{{ open_tilt_position | int }}` in the tilt-only branch. With the window closed, or ventilation not configured/enabled, the tilt-only branch still fires as before. Deliberate consequence: with both options enabled and a tilted window, the cover now *rises* from the shading to the ventilation position — VENT is a floor and outranks SHADING; "stay shaded" means "don't open fully", not "stay below the ventilation floor". Tests: `tests/test_shading_end_priority.py`.

**Rule:** Within a `choose:`, branch order must follow the priority cascade. A branch that implements a lower-cascade behavior (shading convenience) must never be placed above lockout/ventilation branches for the same trigger — and any "the remaining cases" branch must actually be reached only by the remaining cases.

---

### Bug Pattern AK: Pending execution path ends without a helper write → pending stuck until midnight

**Symptom:** A shading start (or end) never executes and never retries. The helper shows `pnd: 'beg'` (or `'end'`) with a `ts.due` in the past, and no further `t_shading_*_execution` run appears in the traces. New pending triggers are blocked (arm branches gate on `not helper_state_pending_*`). The state only clears at the 23:55 midnight reset.

**Cause:** The execution triggers are template triggers on `now() >= ts.due`. For a past `ts.due` the template stays `true` forever — there is no new FALSE→TRUE edge, so the trigger never re-fires. Any execution path that ends **without** a helper write (neither re-arm nor clear) therefore freezes the pending. Two instances found and fixed (CCA 2026.07.01):

- The shading-start drive choose (lockout / start shading / save-for-future) had **no default**. A non-tilt cover resting exactly at the shading position (neither `current_above_shading` nor `current_below_shading`), or a cover held at the ventilation floor (`effective_state == 'vnt'`, third OR-alternative requires `'opn'`), matched no branch → fall-through without helper write.
- "Move cover after shading end" wrapped its whole body in `if not prevent_flags.opening_after_shading_end` with **no else**, followed by `stop:`. With the prevent option set and tilt not possible (the tilt-only branch requires tilt), the sequence stopped without a helper write.

**Fix:** Give every drive choose inside the execution handlers a `default:` that records the state and clears the pending, and give every `if:` before a `stop:` an `else:` that clears the pending. See the "Every execution path must be terminal" rule in Invariant 8.

---

### Bug Pattern AL: The VENT floor gate reads "opening is scheduled" as "opening is *time*-scheduled"

**Symptom:** In a setup that opens the cover by **sun elevation** or **brightness** with time control switched **off** (`auto_up_enabled` + `auto_sun_enabled` / `auto_brightness_enabled`, no `time_control_enabled`), the morning opening drives the cover to the open position as expected — but tilting a window afterwards **pulls it back down** to the ventilation position. With time control enabled the identical situation keeps the cover open. The helper shows `bas: 'opn'`, `win: 'tlt'`, and the trace shows `effective_state == 'vnt'`.

**Cause:** `is_opening_scheduled` — the gate that lets BASE=OPN beat the VENT floor (Bug Pattern Z) — was `is_up_enabled and not is_time_control_disabled`. Its purpose is to tell a **real** `bas: 'opn'` (written by the opening handler) apart from the **init default** (`bas` starts at `'opn'` and only the close handler ever moves it). But `bas` reaches `'opn'` through *any* opening trigger, and time control is only two of the four sources: `t_open_4` (brightness) and `t_open_5` (sun elevation) are gated on their own feature flags alone, and the opening branch explicitly passes them through while time control is off (`is_time_control_disabled` is the first alternative of its scenario OR). So a sun-driven opening set `bas: 'opn'` legitimately, and the gate then classified it as the init default and applied the VENT floor to it.

**Fix:** Mirror the `enabled:` gates of the opening triggers instead of the time control switch:

```yaml
is_opening_scheduled: >-
  {{ is_up_enabled and (
       is_time_field_enabled or
       is_calendar_enabled or
       (is_brightness_enabled and default_brightness_sensor != []) or
       (is_sun_elevation_enabled and default_sun_sensor != [])) }}
```

The sensor-presence clauses are not cosmetic: `t_open_4` / `t_open_5` carry `enabled: "{{ is_brightness_enabled and default_brightness_sensor != [] }}"` (resp. the sun sensor), so a feature flag without its sensor enables no trigger and must not lift the floor. #553 stays fixed by construction — a shading-only setup has no `auto_up_enabled`, and `auto_up_enabled` with *every* source switched off (which has no opening trigger either, so `bas` really is stuck at its default) also still ventilates. `recovered_state` reads the same variable, so the recovery mirror follows automatically (Invariant 13).

**Rule:** A flag that asks "did an automation really write this state?" must be derived from the **triggers that write it**, not from one of the feature switches that happens to enable some of them. Whenever a new source for an existing handler is added, every "does this handler exist?" flag has to be re-derived — the same upstream/downstream mismatch as Bug Pattern AA, just in the variables instead of the gates. `tests/test_opening_schedule_gate.py` pins the flag against the real trigger `enabled:` templates so a fifth opening source cannot silently drift.

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

### Boolean variables must render as a single `{{ … }}` expression

HA parses a rendered template with `literal_eval`. `{{ some_bool }}` renders `True`/`False` and parses back to a bool — but a **bare word inside a `{% if %}` block** does not:

```jinja2
{% if resident_sensor == [] %}false{% else %}{{ … }}{% endif %}   ← renders the STRING "false"
```

`literal_eval("false")` fails (Python needs `False`), so HA keeps the string — and a non-empty string is **truthy**. A variable meant to be `False` silently becomes `True`. This nearly shipped in `state_resident`: with no resident sensor configured it would have reported "resident present", which flips `resident_flags.allow_open` to `false` and closes the cover instead of opening it.

**Rule:** any variable consumed as a boolean must be one `{{ … }}` expression (use inline `if`/`else` inside it). Multi-branch `{% if %}` blocks are fine only for variables consumed as **strings** (`effective_state`, `recovered_state`, …) or numbers.

---

## Version Bumping

The version string exists in **two** locations — both must be updated together:

1. **Description** (user-facing): line ~7 → `**Version**: YYYY.MM.DD`
2. **Variable** (runtime): the `version:` entry at the top of the `variables:` block → `version: "YYYY.MM.DD"` (find it with `grep -n 'version: "20' <blueprint>`)

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
