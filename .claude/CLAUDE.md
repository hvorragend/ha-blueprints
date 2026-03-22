# CLAUDE.md — Cover Control Automation (CCA) Blueprint

## Overview

`blueprints/automation/cover_control_automation.yaml` is a Home Assistant automation blueprint (Jinja2 + YAML). It controls roller blinds/shutters based on time, sun position, window contact sensors, and presence detection.

---

## Helper JSON Schema (v6)

State is persisted as a JSON string in an `input_text` helper:

```json
{"bas":"opn","shd":1,"win":"opn","frc":"non","res":1,"man":0,
 "ts":{"opn":0,"cls":0,"shd":0,"shs":0,"she":0,"win":0,"man":0,"res":0},
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
| `ts.*` | Unix timestamp | Timestamp of last change per field |

---

## Priority Cascade (`effective_state`)

```
1. FORCE    → frc != "non"          → Force position
2. LOCKOUT  → win == "opn"          → Open position (lockout protection)
3. VENT     → win == "tlt"          → Ventilation position
4. PRIVACY  → resident && closing   → Close position
5. SHADING  → shd == 1 && allow     → Shading position
6. BASE     → bas                   → Base position (opn/cls)
```

The variable `effective_state` returns the currently active state from this cascade (`lock`, `vnt`, `cls`, `shd`, `opn`).

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

### ⚠️ Invariant 4: `resident_leaving` — evaluate `allow_shade`/`allow_ventilate` against the new status

In the `resident_leaving` handler, `resident_flags.allow_shade` is based on `state_resident` — which reads from `helper_json.res` (not yet updated → still `1`). This causes `allow_shade` = `not state_resident` = `false` when `resident_allow_shading` is not configured.

**Wrong:**
```yaml
- "{{ resident_flags.allow_shade }}"  # Reads stale helper state!
```

**Correct:**
```yaml
- "{{ new_resident_status == 0 or resident_flags.allow_shade }}"
# simplified: new_resident_status == 0 is always true in the leaving context
```

Since `new_resident_status` is always `0` in the leaving context, the guard can be simplified to `new_resident_status == 0`.

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

### Bug Pattern B: `resident_flags.allow_shade/allow_ventilate` in the `resident_leaving` handler

**Symptom:** After resident leaves, cover moves to open position instead of shading or ventilation position.

**Cause:** `resident_flags.allow_shade` is based on `state_resident` = `helper_json.res` = still `1` (old value). So `allow_shade` = `false` when `resident_allow_shading` is not configured → branch skipped.

**Fix:** Use `new_resident_status == 0` instead of `resident_flags.allow_shade` in the `resident_leaving` handler:
```yaml
- "{{ new_resident_status == 0 or 'resident_allow_shading' in resident_config }}"
```

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

### Bug Pattern G: `helper_state_window` instead of realtime sensor in `resident_arriving` handler

**Symptom:** When cover was already at open position when the window was opened, `resident_arriving` does not recognize the lockout state → cover incorrectly closes.

**Cause:** `helper_json.win` is only updated when a drive occurs. If the cover was already open, `win` stays `cls` in the helper.

**Fix:** Always use realtime sensors in the `resident_arriving` handler:
```yaml
# Wrong: helper_state_window != 'opn'
# Correct:
- "{{ contact_window_opened != [] and states(contact_window_opened) in ['true', 'on'] }}"
```

---

## Running Unit Tests

```bash
pip install pytest jinja2 pyyaml
pytest tests/ -v
```

Tests verify the priority cascade for critical scenarios without a real Home Assistant instance.
