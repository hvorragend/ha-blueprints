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

## Reference Files — read the matching file BEFORE working on its area

This SKILL.md is the overview and quick index. The detailed, authoritative
material lives in `references/` next to this file — it is the single source of
truth. Do not code against the summaries below in one of these areas without
loading the reference first:

| Task touches… | Read |
|---|---|
| Priority cascade (`effective_state`/`recovered_state`), transition anchors, `state_targets`/`state_gates`, limited template contexts | [references/architecture.md](references/architecture.md) |
| Branch conditions, drive gates, `update_values`, timestamps (`ts.*`), pending logic | [references/invariants.md](references/invariants.md) (full rationale for all 14 invariants) |
| Anything that looks inconsistent and invites "harmonizing" (resident/override gates, pending preserve vs. discard, invalid sensor states, #558/#580) | [references/design-decisions.md](references/design-decisions.md) |
| Availability gates, `t_recovery`, `automation_resumed`, the recovery gate — or adding any new gate that can stop a run | [references/recovery.md](references/recovery.md) (includes the orphan-audit checklist) |
| Debugging a regression, changing global conditions / trigger `enabled:` / helper-JSON regexes / flow handoffs | [references/bug-patterns.md](references/bug-patterns.md) (patterns A–AO with cause and fix) |

The always-binding rules (the 14 invariants as one-liners, code style, quality
gates, version bumping) are indexed in `.claude/CLAUDE.md`.

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
| `ts.opn` / `ts.cls` | Unix timestamp | Last base-state switch to open / closed |
| `ts.shd` | Unix timestamp | Last shading state change (0↔1) |
| `ts.due` | Unix timestamp | Fire time of armed pending (`0` when `pnd == 'non'`) |
| `ts.arm` | Unix timestamp | First-arming anchor of current retry sequence (`0` when `pnd == 'non'`) |
| `ts.man` | Unix timestamp | Last manual override event |

### Pending field semantics (`pnd` enum)

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
3. BASE=OPN → bas == "opn" AND is_opening_scheduled AND no privacy/shading/restriction → Open ('opn')
4. VENT     → win == "tlt" AND base would close/shade/privacy    → Ventilation position ('vnt')
5. PRIVACY  → resident && closing_enabled                        → Close position ('cls')
6. SHADING  → shd == 1 && allow_shade                            → Shading position ('shd')
7. BASE=CLS → bas (with allow_open gate)                         → Close position ('cls')
```

`effective_state` returns: `lock | opn | vnt | cls | shd`. VENT is a *floor*,
not a target: BASE=OPN beats it only when an opening automation actually exists
(`is_opening_scheduled`, derived from the `enabled:` gates of every `bas='opn'`
writer incl. the resident opening — Bug Patterns Z + AL + AO). The `base_target`
implementation and the full rationale
are in [references/architecture.md](references/architecture.md).

**Critical**: `effective_state == 'opn'` can result from EITHER `base='opn'`
OR `force='opn'`. Never assume `base` is `'opn'` just because `effective_state`
is `'opn'`.

---

## Key Variables

### Position variables
```yaml
in_open_position      # Current position within tolerance of open_position
in_close_position     # Current position within tolerance of close_position
in_shading_position   # Current position within tolerance of effective_shading_position
in_ventilate_position # Current position within tolerance of ventilate_position
effective_shading_position  # shading_position or shading_position_alt (#580) —
                            # every shading consumer must read this, never the raw input
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
is_paused             # Force pause entity active — part of EVERY drive gate
live_force            # Force re-derived from live entities, helper fallback (Tier 2)
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
  opening / closing / ventilation / shading   # 'ignore_X_after_manual' configured
override_blocks:
  opening / closing / ventilation / shading   # helper_state_manual and override_flags.X
```

### Prevent flags (daily repetition control)
```yaml
prevent_flags:
  shading_multiple_times / opening_multiple_times / closing_multiple_times
```

### Normalized event flags (computed once per run — use these, not raw sensor idioms)
```yaml
window_opened_now / window_tilted_now / window_any_now / window_opened_clear
lockout_now.closing / .shading_start / .shading_end
shading_once_guard_ok
drive_delay_standard
environment_allows_opening / environment_allows_closing
```

### Timestamp helpers
```yaml
helper_ts_open / helper_ts_close / helper_ts_shade / helper_ts_man
helper_ts_pending_due   # helper_json.ts.due (fire time of armed pending)
helper_ts_pending_arm   # helper_json.ts.arm (retry anchor)
```

---

## Working Rules (quick index)

Full rationale in [references/invariants.md](references/invariants.md) and
[references/architecture.md](references/architecture.md); the one-line index of
all 14 invariants is in `.claude/CLAUDE.md`. The ones that bite most often:

- Every leaf branch computes `will_drive` + `drive_plan` + `update_values`, then
  calls `*apply_transition` — never `*helper_update` / `*drive_with_actions` /
  `*tilt_move_action` directly (enforced by `tests/test_apply_transition_architecture.py`).
- Position checks belong in the `will_drive` gate, never in branch conditions.
- `trigger_variables:` is a limited template context — no `states()` there.
- `ts_now` is always set at the point of use, never globally.
- Anchor bodies (`&cover_move_action`, `&tilt_move_action`, `&drive_with_actions`,
  `&helper_update`, `&apply_transition`) are pre-rendered on every run — all
  runtime-context references inside them need template guards. `&shading_start_retry`
  is deliberately defined at first use instead.
- Every cascade change lands in `effective_state` AND `recovered_state`, same
  commit (`TestCascadeParity`).

### `update_values` / `helper_update` merge semantics

The `helper_update` anchor merges `update_values` into the current helper JSON:
timestamps accept `'now'` (replaced with `as_timestamp(now())`) or explicit
values; omitted fields are preserved. Guards: `ts.shd` only updates when `shd`
actually changes; `pnd`/`ts.due`/`ts.arm` are not reset in win-only updates.
The canonical leaf-branch skeleton is in
[references/architecture.md](references/architecture.md).

---

## Action Tree Structure

**Pre-dispatch steps** (before the main `choose:`): helper init/repair,
v5→v6 migration, forecast load, calendar load + relevance check, and the
**recovery gate** (claims every trigger on a resumed run; see
[references/recovery.md](references/recovery.md)). A new pre-dispatch step that
can `stop:` a run needs a `PRE_DISPATCH_DEFINITIONS` entry in the trace tools.

**Dispatch branches** (order pinned by `tests/test_trace_tools_branch_map.py`):

- **Opening** — check → already-open guard → shading-detected/defer sub-branches → normal opening
- **Closing** — check → lockout protection → tilted-ventilation → already-closed guard → normal closing
- **Shading Start** — detection → pending arm (`pnd: 'beg'`) → execution (lockout skip / vent floor / drive / save-for-future / retry / abort)
- **Shading Tilt** — adjusts tilt while shading is active
- **Alternate shading position (3b)** — re-drives depth while `shd == 1` when `shading_position_alt_entity` flips (#580)
- **Shading End** — detection → pending arm (`pnd: 'end'`) → execution (pending → lockout → ventilation → tilt-only → move-cover, cascade order)
- **Contact Sensor** — opened → lockout (always runs); tilted → ventilation (gated by `resident_flags.allow_ventilate`); closed → `return_target` chain
- **Resident Sensor** — leaving: `leave_target` chain + VENT-tilted leaf; arriving: `arrive_target` + VENT-hold leaf
- **Midnight Reset (23:55)** — clears `shd`/`pnd`/`man`
- **Force enable/disable** — incl. `recovery_target` chain on disable; force pause resume
- **Manual detection** — position/tilt → `man: 1` (never drives)
- **Override reset** — fixed time / timeout / in-position

---

## Debugging

### Logbook (`enable_logbook`)
When enabled, `*helper_update` writes a logbook entry with `trigger.id`,
`effective_state`, position, sensor states, and raw `update_values` JSON.
Optional `log_extra` string for branches with additional context (pending/retry
details). `trigger.id` is the source of truth for "which path ran".

### Trace analysis
- Use the CCA Trace Analyzer for uploaded JSON traces
- Key fields: `last_step`, which `choose/N` branch fired, `result: {choice: N}`
- Check `changed_variables` for `update_values`, `effective_state`, `helper_json`
- A run that ends in a pre-dispatch step (recovery gate, calendar relevance
  check) carries no `choose/M` — the trace tools resolve it via the step alias.

### Regressions
Match the symptom against [references/bug-patterns.md](references/bug-patterns.md)
(A–AO, each with symptom / cause / fix / derived rule) before writing a fix —
most "new" bugs are a documented pattern reaching a new code path.

---

## Trigger IDs

**Opening:** `t_open_1`, `t_open_2`, `t_open_4`, `t_open_5`
**Closing:** `t_close_1`, `t_close_2`, `t_close_4`, `t_close_5`
**Calendar:** `t_calendar_event_start`, `t_calendar_event_end`
**Contacts:** `t_contact_opened_changed`, `t_contact_tilted_changed`
**Resident:** `t_resident_update`
**Shading Start:** `t_shading_start_pending_1`–`_8` (`_8` = custom condition sensor), `t_shading_start_execution`
**Shading End:** `t_shading_end_pending_1`–`_8` (`_8` = custom condition sensor), `t_shading_end_execution`
**Shading Tilt:** `t_shading_tilt_1`–`_4`
**Alternate shading position:** `t_shading_position_alt`
**Force:** `t_force_enabled_open/close/shading/ventilate`, `t_force_disabled_open/close/shading/ventilate`, `t_force_pause_disabled`
**Manual:** `t_manual_position` (×3 sources), `t_manual_tilt`
**Reset:** `t_shading_reset` (23:55), `t_reset_fixedtime`, `t_reset_timeout`, `t_reset_position`
**Recovery:** `t_recovery` (shared id on ~20 triggers: `homeassistant: start`, the resume trigger, one per recovering source), `t_automation_reloaded` (the `automation_reloaded` event — the resume prompt for reload/save, where the resume template is blind; unclaimed runs are stopped pre-dispatch — see [references/recovery.md](references/recovery.md))

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

- **CLAUDE.md, reference docs, code comments**: English
- **Chat responses**: German
