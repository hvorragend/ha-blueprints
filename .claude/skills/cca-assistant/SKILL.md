---
name: cca-assistant
description: >
  Expert assistant for developing and debugging the Cover Control Automation (CCA)
  Home Assistant blueprint. Use this skill whenever the user works on the CCA YAML
  blueprint, asks about state logic, JSON helper structure, shading/force/resident
  branches, trigger conditions, template variables, or debug traces. Also trigger
  when reviewing code changes, writing commit messages, or discussing the priority
  cascade (force, lockout, base-open, vent, privacy, shading, base-close — highest
  to lowest). This skill captures the full technical context, constraints, and
  working principles of the CCA project so Claude can assist without re-explaining
  fundamentals every session.
---

# CCA Assistant Skill

## Project Context

Cover Control Automation (CCA) is a Home Assistant YAML automation blueprint for
intelligent roller shutter and blind control. It manages covers based on time
schedules, brightness, sun elevation, window state, and resident presence.

- **Forum**: https://community.home-assistant.io/t/680539
- **GitHub**: https://github.com/hvorragend/ha-blueprints
- **Validator**: https://hvorragend.github.io/ha-blueprints/validator/
- **Trace Analyzer**: https://hvorragend.github.io/ha-blueprints/trace-analyzer/

---

## JSON Helper Schema (v6 compact, stored in `input_text`)

```json
{"bas":"opn","shd":0,"pnd":"non","win":"cls","frc":"non","res":0,"man":0,
 "ts":{"opn":0,"cls":0,"shd":0,"due":0,"arm":0,"man":0},"v":6,"t":0}
```

| Field | Values | Meaning |
|-------|--------|---------|
| `bas` | `opn` / `cls` | Base state (time-scheduled ground state) |
| `shd` | `1` / `0` | Shading active (target marker, independent of pending) |
| `pnd` | `non` / `beg` / `end` | Shading pending phase (none / start-armed / end-armed) |
| `win` | `cls` / `tlt` / `opn` | Window sensor state |
| `frc` | `non` / `opn` / `cls` / `shd` / `vnt` | Force override |
| `res` | `1` / `0` | Resident present |
| `man` | `1` / `0` | Manual override active |
| `ts.opn` | Unix timestamp | Last time base state switched to open |
| `ts.cls` | Unix timestamp | Last time base state switched to closed |
| `ts.shd` | Unix timestamp | Last time shading state changed (0↔1) |
| `ts.due` | Unix timestamp | Fire time of armed pending (`0` when `pnd == 'non'`) |
| `ts.arm` | Unix timestamp | First-arming anchor of current retry sequence (`0` when `pnd == 'non'`) |
| `ts.man` | Unix timestamp | Last manual override event |

### Pending field semantics (`pnd` enum)

- `pnd='non'` → no pending phase active (idle)
- `pnd='beg'` → shading **start pending** (waiting for conditions / retry)
- `pnd='end'` → shading **end pending** (waiting for conditions / retry)

Only one phase can be pending at a time (mutually exclusive by schema).
`pnd='non'` always implies `ts.due == 0` and `ts.arm == 0`.

**`ts.due`** is re-armed on every retry: `now + waiting_time`.
**`ts.arm`** is set once when the sequence starts and preserved across retries,
used by `shading_start_max_duration` and `shading_end_max_duration`.

### Derived helper state variables

| Variable | Definition |
|----------|-----------|
| `helper_state_shade` | `helper_json.shd == 1` (target marker, regardless of pending) |
| `helper_state_is_shaded` | `helper_json.shd == 1 and pnd != 'beg'` (truly active, not pending) |
| `helper_state_pending_start` | `helper_json.pnd == 'beg'` |
| `helper_state_pending_end` | `helper_json.pnd == 'end'` |
| `helper_state_base` | `helper_json.bas` → `'opn'` or `'cls'` |
| `helper_state_window` | `helper_json.win` → persisted (may be stale!) |
| `helper_state_manual` | `helper_json.man == 1` |

---

## Priority Cascade (`effective_state`)

```
1. FORCE    → frc != "non"                                       → Force position
2. LOCKOUT  → win == "opn"                                       → Open position ('lock')
3. BASE=OPN → bas == "opn" AND no privacy/shading/restriction    → Open position ('opn')
4. VENT     → win == "tlt" AND base would close/shade/privacy    → Ventilation position ('vnt')
5. PRIVACY  → resident && closing_enabled                        → Close position ('cls')
6. SHADING  → shd == 1 && allow_shade                            → Shading position ('shd')
7. BASE=CLS → bas (with allow_open gate)                         → Close position ('cls')
```

`effective_state` returns: `lock | opn | vnt | cls | shd`

**Implementation detail:** `effective_state` first computes `base_target` (the
cover state without VENT consideration), then applies VENT only when
`win == 'tlt'` and `base_target != 'opn'`.

```
base_target logic:
  1. privacy_active (resident + closing_enabled) → 'cls'
  2. shd == 1 AND allow_shade                    → 'shd'
  3. bas == 'opn' AND not allow_open             → 'cls'
  4. else                                        → h.bas
```

**Rationale for BASE=OPN before VENT:** A tilted window signals ventilation
intent — and a fully open cover provides maximum airflow. VENT is a *floor*
only when the cover would otherwise go below ventilation position.

**Critical**: `effective_state == 'opn'` can result from EITHER `base='opn'`
OR `force='opn'`. Never assume `base` is `'opn'` just because `effective_state`
is `'opn'`.

---

## Key Variables

### Position variables
```yaml
in_open_position      # Current position within tolerance of open_position
in_close_position     # Current position within tolerance of close_position
in_shade_position     # Current position within tolerance of shading_position
in_ventilate_position # Current position within tolerance of ventilate_position
```

### State variables
```yaml
state_resident        # Live sensor: states(resident_sensor) — always current
state_base            # helper_json.bas → 'opn' or 'cls'
effective_state       # Priority cascade result: lock|opn|vnt|cls|shd
```

### Force variables
```yaml
is_forced_open        # Force open active
is_forced_close       # Force close active
is_forced_shade       # Force shade active
is_forced_ventilate   # Force ventilate active
force_allows_ventilate  # not (is_forced_open or is_forced_close or is_forced_shade)
is_paused             # Force pause entity active
```

### Resident flags (based on live sensor, not helper)
```yaml
resident_flags:
  opening_trigger     # 'resident_opening_enabled' configured
  closing_trigger     # 'resident_closing_enabled' configured
  allow_open          # 'resident_allow_opening' configured OR not state_resident
  allow_shade         # 'resident_allow_shading' configured OR not state_resident
  allow_ventilate     # 'resident_allow_ventilation' configured OR not state_resident
```

### Override flags (manual override gates)
```yaml
override_flags:
  opening             # 'ignore_opening_after_manual' configured
  closing             # 'ignore_closing_after_manual' configured
  ventilation         # 'ignore_ventilation_after_manual' configured
  shading             # 'ignore_shading_after_manual' configured
```

### Prevent flags (daily repetition control)
```yaml
prevent_flags:
  shading_multiple_times   # Prevent shading more than once per day
  opening_multiple_times   # Prevent opening more than once per day
  closing_multiple_times   # Prevent closing more than once per day
```

### Environment variables
```yaml
environment_allows_opening   # Brightness and/or sun elevation allow opening (OR logic)
environment_allows_closing   # Brightness and/or sun elevation require closing (OR logic)
```

### Timestamp helpers
```yaml
helper_ts_open          # helper_json.ts.opn (Unix timestamp)
helper_ts_close         # helper_json.ts.cls
helper_ts_shade         # helper_json.ts.shd
helper_ts_pending_due   # helper_json.ts.due (fire time of armed pending)
helper_ts_pending_arm   # helper_json.ts.arm (retry anchor)
helper_ts_man           # helper_json.ts.man
```

---

## YAML Technical Constraints

### `trigger_variables` — Limited Template only
No `states()`, `is_state()`, or `state_attr()` allowed here. Only static values
and simple Jinja2 expressions. Move state-reading variables to action `variables:`.

### `ts_now` — Always set at point of use
```yaml
{% set ts_now = as_timestamp(now()) | round(0) %}
```
Set inside each sequence branch locally, never as a global variable.
Delays between steps would make a global value stale.

### Helper updates — use `*helper_update` anchor
Never write the helper update inline; always use the YAML anchor.
The anchor handles JSON merging, timestamp guards, and optional logbook logging.

### Three YAML anchors
- `&cover_move_action` — actual cover movement with position tolerance
- `&tilt_move_action` — tilt positioning with wait strategy
- `&helper_update` — JSON state persistence + logbook

---

## Architectural Invariants (Reference)

Full details in CLAUDE.md. Key rules:

1. **Never put position checks in branch conditions** — move into `if:` guards
   inside the branch sequence. The branch must always be consumed.
2. **Always call `*helper_update`** at the end of every branch.
3. **Realtime vs. helper state** — use `states(sensor)` for current values,
   `helper_json.*` is persisted and may be stale.
4. **`resident_flags.*` uses live sensor** — no stale-state problem.
5. **`opened` always takes priority over `tilted`** — every tilted branch
   must check `not (contact_window_opened active)`.
6. **Lockout is independent of `resident_allow_ventilation`** — safety feature.
7. **`man: 0` only when driving** — not in pending, lockout-only, or pure state changes.
   Exception: midnight reset (BRANCH 11).
8. **Timestamp guards** — `ts.shd` only when `shd` changes; `ts.arm` preserved
   across retries; `pnd='non'` clears `ts.due` and `ts.arm` together.
9. **`ts_now` at point of use** — never global.
10. **`trigger_variables:` limited context** — no `states()`.
11. **`pnd` is mutually exclusive** — start and end cannot be pending simultaneously.
12. **Logbook uses `trigger.id` + `update_values`** — no reason-inference table.

---

## Design Decisions (Intentional Deviations)

### Resident handler bypasses manual override
The resident sensor handler does not check `helper_state_manual` / `override_flags.*`.
Presence transitions are a hard reset — intentional, do not "harmonize".

### Midnight reset (BRANCH 11) sets `man: 0` without driving
Intentional exception to Invariant 7. Clears stale overrides for next day's cycle.

---

## Branch Structure (Main choose blocks)

### Opening (BRANCH 1-4)
- Check for opening → already-open guard → shading-detected sub-branch → normal opening
- Uses `prevent_flags.opening_multiple_times` daily guard

### Closing (BRANCH 5-8)
- Check for closing → lockout protection → tilted-ventilation → already-close guard → normal closing
- Base state (`bas: 'cls'`, `ts.cls: 'now'`) always updated regardless of physical position

### Shading Start (BRANCH 9)
- Detection → pending arm (`pnd: 'beg'`, `ts.due`, `ts.arm`) → execution trigger
- Lockout skip → drive → save-for-future → blocked/retry → abort branches
- Uses `shading_start_max_duration` with `helper_ts_pending_arm` as anchor

### Shading Tilt
- Adjusts tilt position while shading is active

### Shading End (BRANCH 10)
- Detection → pending arm (`pnd: 'end'`, `ts.due`, `ts.arm`) → execution trigger
- Tilt-only → lockout → ventilation → move-cover → blocked/retry → abort branches
- Uses `shading_end_max_duration` with `helper_ts_pending_arm` as anchor

### Contact Sensor (BRANCH)
- Window opened → lockout (always runs, independent of `resident_allow_ventilation`)
- Window tilted → partial ventilation (gated by `resident_flags.allow_ventilate`)
- Window closed → return to shading/open/close based on `effective_state`

### Resident Sensor (BRANCH)
- Leaving (ON→OFF): targets ventilation-full → ventilation-tilt → shaded → open → close
- Arriving (OFF→ON): lockout → ventilation-hold → privacy-close branches

### Midnight Reset (BRANCH 11)
- Resets `shd: 0`, `pnd: 'non'`, `man: 0` when shading was active at midnight

### Force / Manual / Override
- Force enable/disable handlers with recovery to `effective_state`
- Manual position/tilt detection → sets `man: 1`
- Override reset (fixed time / timeout)

---

## `update_values` Pattern

Every branch sets `update_values` before calling `*helper_update`:
```yaml
- variables:
    update_values:
      bas: 'opn'
      shd: 0
      pnd: 'non'
      man: 0
      ts:
        opn: 'now'
        due: 0
        arm: 0
```

The `helper_update` anchor merges these into the current helper JSON.
Timestamps support `'now'` (replaced with `as_timestamp(now())`) or explicit values.
Omitted fields are preserved from the current helper state.

Guards in `helper_update`:
- `ts.shd` only updated when `shd` actually changes
- `pnd`/`ts.due`/`ts.arm` not reset in win-only updates

---

## Debugging

### Logbook (`enable_logbook`)
When enabled, `*helper_update` writes a logbook entry with `trigger.id`,
`effective_state`, position, sensor states, and raw `update_values` JSON.
Optional `log_extra` string for branches with additional context (pending/retry details).

### Trace analysis
- Use the CCA Trace Analyzer for uploaded JSON traces
- Key fields: `last_step`, which `choose/N` branch fired, `result: {choice: N}`
- Check `changed_variables` for `update_values`, `effective_state`, `helper_json`
- `trigger.id` is sprechend (e.g. `t_open_1`, `t_shading_start_pending_2`)

### Common bug patterns
| Symptom | Likely cause |
|---------|-------------|
| Branch fires every trigger unnecessarily | Missing guard on "already in state" |
| Force recovery goes to wrong state | `state_base` stale, not updated during Force |
| Shading detected as inactive when closed | `state_is_shaded` vs `state_shade` confusion |
| Resident wake-up not opening cover | Stale `state_resident` in helper during transition |
| `prevent_multiple_times` not working | `ts.opn`/`ts.cls` not updated when cover already in position |
| Tilted branch fires when window fully open | Missing `not contact_window_opened` check in tilted branch |
| Lockout disabled without ventilation config | `resident_flags.allow_ventilate` gates entire contact handler |
| Manual override cleared unexpectedly | `man: 0` in non-movement blocks |
| Shading retry aborts on fresh day | Duration check uses `ts.shd` instead of `ts.arm` |

---

## Trigger IDs (45 total)

**Opening:** `t_open_1`, `t_open_2`, `t_open_4`, `t_open_5`
**Closing:** `t_close_1`, `t_close_2`, `t_close_4`, `t_close_5`
**Resident:** `t_resident_update`
**Calendar:** `t_calendar_event_start`, `t_calendar_event_end`
**Force Open:** `t_force_enabled_open`, `t_force_disabled_open`
**Force Close:** `t_force_enabled_close`, `t_force_disabled_close`
**Contacts:** `t_contact_tilted_changed`, `t_contact_opened_changed`
**Force Vent:** `t_force_enabled_ventilate`, `t_force_disabled_ventilate`
**Shading Start:** `t_shading_start_pending_1` to `_7`, `t_shading_start_execution`
**Force Shade:** `t_force_enabled_shading`, `t_force_disabled_shading`, `t_force_pause_disabled`
**Shading Tilt:** `t_shading_tilt_1` to `_4`
**Shading End:** `t_shading_end_pending_1` to `_6`, `t_shading_end_execution`
**Reset:** `t_shading_reset`, `t_reset_fixedtime`, `t_reset_timeout`
**Manual:** `t_manual_position` (×3), `t_manual_tilt`

---

## Input Sections (18 sections, ~90 inputs)

| Section | Purpose |
|---------|---------|
| blind | Cover entity selector |
| cover_status_helper | Input text helper for JSON storage |
| feature_section | Automation options, time control mode, brightness/sun operator |
| position_section | Position source, cover type, open/close/vent/shade positions, tolerance |
| tilt_position_section | Tilt wait mode, delay, tilt positions |
| time_section | Up/down times (early/late, workday/non-workday), workday sensor, calendar |
| brightness_section | Brightness sensor, thresholds, hysteresis, duration |
| sun_section | Sun sensor, elevation mode, up/down thresholds or sensors, duration |
| contacts_section | Window opened/tilted sensors, lockout options, ventilation options, delays |
| shading_section | Start/end conditions (AND/OR), azimuth, elevation, brightness, forecast, weather, timing |
| resident_section | Resident sensor, resident behavior config |
| override_section | Manual override ignore config, reset config, reset time/timeout |
| delay_section | Fixed and random drive delays |
| condition_section | Global + per-action conditions (up, down, ventilate, shading start/tilt/end) |
| force_section | Force recovery, force pause, per-action force entities |
| actions_section | Before/after actions for each drive type, manual action |
| configcheck_section | Config validation toggle, debug level |
| logging_section | Logbook enable toggle |

---

## Commit Message Style

Short, lowercase, imperative English. Format:
```
TYPE: short imperative summary

optional 1-3 lines of detail
```
Types: `fix` / `feat` / `refactor` / `chore` / `docs`

---

## Language Conventions

- **CLAUDE.md**: English
- **Code comments** in blueprint YAML: English
- **Chat responses**: German
