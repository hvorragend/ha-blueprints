# CCA Architecture Reference

Read this before changing the priority cascade (`effective_state` / `recovered_state`),
the transition anchors (`apply_transition`, `drive_with_actions`, `helper_update`),
or anything that touches `trigger_variables:`.

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

