# CLAUDE.md — Cover Control Automation (CCA) Blueprint

## Overview

`blueprints/automation/cover_control_automation.yaml` is a Home Assistant automation blueprint (Jinja2 + YAML). It controls roller blinds/shutters based on time, sun position, window contact sensors, and presence detection.

---

## Helper JSON Schema (v6)

State is persisted as a JSON string in an `input_text` helper:

```json
{"bas":"opn","shd":1,"win":"opn","frc":"non","res":1,"man":0,
 "ts":{"opn":0,"cls":0,"shd":0,"shs":0,"she":0,"shr":0,"man":0},
 "v":6,"t":0}
```

| Field | Values | Meaning |
|-------|--------|---------|
| `bas` | `opn`/`cls` | Base state (time-based: open / closed) |
| `shd` | `1`/`0` | Shading active |
| `win` | `cls`/`tlt`/`opn` | Window state (closed / tilted / open) |
| `frc` | `non`/`opn`/`cls`/`shd`/`vnt` | Active force function |
| `res` | `1`/`0` | Resident present |
| `man` | `1`/`0` | Manual override active |
| `ts.opn` | Unix timestamp | Last time base state switched to open |
| `ts.cls` | Unix timestamp | Last time base state switched to closed |
| `ts.shd` | Unix timestamp | Last time shading state changed (0↔1) |
| `ts.shs` | Unix timestamp | Shading pending start: when pending-start was armed |
| `ts.she` | Unix timestamp | Shading pending end: when pending-end was armed |
| `ts.shr` | Unix timestamp | Shading retry anchor: when current retry sequence (start OR end) began |
| `ts.man` | Unix timestamp | Last manual override event |

> Note: `ts.win` and `ts.res` were removed during v6 beta. Existing helpers retain those keys until the next helper write, which silently drops them.

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
- `helper_state_window` / `helper_json.win` → **Helper** (last persisted state)

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

**ts.shs / ts.she (shading pending timestamps):**
- These must not be reset in win-only helper updates (when only `win` is updated without a drive)

**ts.shr (shading retry anchor):**
- Single field shared by both shading-start and shading-end retry sequences (mutually exclusive in normal operation, guarded by Invariant 11)
- Set to `"now"` exactly once when either retry sequence begins (in "Shading detected. Save next execution time and pending status" for start, "Shading end detected. Save next execution time and pending status" for end)
- Preserved across all retry-continuation branches (do not include `shr` in `update_values.ts` there — `helper_update` keeps the existing value)
- Reset to `0` in every terminal branch of either sequence:
  - Start: Drive, Lockout-skip, Save-for-future, both Abort branches
  - End: Tilt-only, Lockout, Ventilation, Move-cover (both then/else), Stop retry, stale-pending cleanup (#395)
  - Midnight reset (BRANCH 11, "Reset shading status"): clears `shs`/`she`, must therefore also clear `shr`
- Read by both `shading_start_max_duration` and `shading_end_max_duration` checks via `helper_ts_shade_retry` — gives a stable retry-window anchor independent of the Invariant-8 guard on `ts.shd`

### ⚠️ Invariant 11: Mutual exclusivity of shading-start and shading-end pending

Pending-start (`ts.shs > 0`) and pending-end (`ts.she > 0`) must never both be active simultaneously. With sane configuration (hysteresis > 0 between start and end thresholds), this state is unreachable. With misconfigured conditions it could otherwise produce ping-pong: start fires → end fires → start fires → …

**Guard:** Both pending-establishment branches gate on the opposite pending state:

- "Shading detected" (start) requires `not helper_state_pending_end`
- "Shading end detected" requires `not helper_state_pending_start`

This also keeps the shared `ts.shr` retry anchor unambiguous (Invariant 8).

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

### Midnight reset (BRANCH 11) sets `man: 0` without driving

The "Reset shading status that is no longer required" branch writes `man: 0` even though it does not drive the cover. This is an intentional exception to Invariant 7.

**Rationale:** Midnight is the natural reset point for the daily automation cycle. Clearing `man` here ensures stale manual overrides do not block the next day's automation. In practice the branch only fires when shading was active (or pending) at midnight — and in those scenarios the user typically did not override manually, so `man` is already `0`. The explicit reset is a defensive safeguard and is documented as a deliberate exception.

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
**Cause B:** `ts.shs/ts.she` are reset in win-only helper updates.

**Fix:** Guard in `helper_update` — only apply `ts.shd` when `new_shd != current.shd`. Do not reset `ts.shs/ts.she` in win-only updates.

### Bug Pattern I: Shading-start retry aborts on fresh day (Issue #416)

**Symptom:** First retry attempt of the day aborts immediately when the start conditions are blocked by additional conditions or manual override; the `shading_start_max_duration` window is effectively zero on a fresh helper.

**Cause:** The duration check used `helper_ts_shade` (= `ts.shd`) as anchor. Pending establishment does not transition `shd`, so the Invariant-8 guard preserves `ts.shd` at its previous value (yesterday's shading-end or `0`). `now() - ts.shd` is therefore much larger than `shading_start_max_duration` → check fails → retry aborts.

**Fix:** Dedicated `ts.shr` field that records the retry-sequence start. Set in "Shading detected" (start) and "Shading end detected" (end), preserved across continues, cleared in all terminal branches of both sequences. Duration checks for both `shading_start_max_duration` and `shading_end_max_duration` now use `helper_ts_shade_retry`. The same field serves both directions because the sequences are mutually exclusive (Invariant 11).

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

### Bug Pattern J: Manual move to free position preserves stale shading state (Issue #447)

**Symptom:** User manually moves the cover to a position that does not match any defined position (e.g. 79 with open=100, shading=65, close=0). A short time later the automation opens the cover via shading-end and clears `man=0`, even though `reset_override_timeout` has not elapsed.

**Cause:** The "Manual: position cannot be assigned (unknown)" branch sets `man: 1` but preserves the existing `shd`, `shs`, `she` and `shr`. If `shd=1` was set earlier (e.g. by "Consider lockout protection when shading starts" or "Save shading state for the future") without the cover ever reaching the shading position, that stale flag — together with `helper_state_is_shaded` in the shading-end gate — lets shading-end arm and fire over the manual move.

**Rule:** Manual moves to a position not assignable to any defined state are terminal events for any pending shading sequence. The branch must clear `shd`, `shs`, `she` and `shr` consistent with "Manual: opened" and "Manual: closed".

**Fix:** In the "Manual: position cannot be assigned (unknown)" `update_values`:
```yaml
shd: 0
man: 1
ts:
  shd: 'now'
  man: 'now'
  shs: 0
  she: 0
  shr: 0
```

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
