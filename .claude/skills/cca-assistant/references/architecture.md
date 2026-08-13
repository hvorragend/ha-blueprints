# CCA Architecture Reference

Read this before changing the priority cascade (`effective_state` / `recovered_state`),
the transition anchors (`apply_transition`, `drive_with_actions`, `helper_update`),
or anything that touches `trigger_variables:`.

---

## Priority Cascade (`effective_state`)

```
1. FORCE    → frc != "non"                                       → Force position
2. LOCKOUT  → win == "opn"                                       → Lockout position (defaults to open)
3. BASE=OPN → bas == "opn" AND is_opening_scheduled AND no privacy/shading/restriction → Open position
4. VENT     → win == "tlt" AND base would close/shade/privacy    → Ventilation position
5. PRIVACY  → resident && closing                                → Close position
6. SHADING  → shd == 1 && allow_shade                            → Shading position
7. BASE=CLS → bas                                                → Close position
```

The variable `effective_state` returns the currently active state from this cascade (`lock`, `opn`, `vnt`, `cls`, `shd`).

**Rationale for BASE=OPN before VENT:** A tilted window signals ventilation intent — and a fully open cover provides maximum airflow. So when the time schedule says "open" (`bas=opn`) and nothing else lowers the cover, opening wins over the tilted-vent floor. VENT is a *floor* only when the cover would otherwise go below ventilation position (close, shading, privacy-close, or base=opn with `allow_open=false`).

**BASE=OPN beats VENT only when an opening automation actually exists** (`is_opening_scheduled`). `bas` initializes to `'opn'` and is only ever switched to `'cls'` by the close handler — so in a shading-only setup with no opening automation, `bas` stays `'opn'` permanently. Without the gate the VENT floor could never apply there (Issue #553, Bug Pattern Z). When no opening automation exists, a tilted window therefore still produces `vnt`.

The flag mirrors the `enabled:` gates of the **triggers that write `bas='opn'`**, not the time control switch: the opening handler is reached by four sources — time fields (`t_open_1/2`), calendar (`t_calendar_event_start`), brightness (`t_open_4`) and sun elevation (`t_open_5`) — and the **resident-leaving handler** (`t_resident_update` with `resident_opening_enabled`) is the fifth source: its `leave_target == 'opn'` case writes `bas: 'opn'` too. Brightness and sun open the cover with time control switched **off** (the opening branch passes them through via `is_time_control_disabled`), and a resident opening needs no other source at all — so their `bas: 'opn'` is a real intent too. Gating on `not is_time_control_disabled` misread it as the init default and let VENT drag an open cover down to the ventilation position (Bug Pattern AL); missing the resident source held a tilted window at the ventilation position when the resident left (Bug Pattern AO, Issue #616).

Implementation: `effective_state` first computes `base_target` (the cover state without VENT consideration: `cls`, `shd`, or `opn`), then applies VENT when `win == 'tlt'` and `allow_vent` (the resident ventilation gate) and `not (base_target == 'opn' and is_opening_scheduled)` and `not (base_target == 'shd' and shading_over_ventilation)`.

**The `shading_over_ventilation` option inverts VENT vs. SHADING — that pair only.** The
harm of the VENT floor scales with `ventilate_position − shading_position`: with the stock
positions (30/25) it is cosmetic, with a terrace-door setup (95/35) a permanently tilted
window disables shading for the whole warm season while the helper still reads `shd: 1`.
The option is a checkbox in `auto_ventilate_options`, resolved in `trigger_variables:`
(pure list membership — the cascade needs it, so it must not live in the later
`variables:` block). The gate is bound to `base_target == 'shd'`, so LOCKOUT, PRIVACY-close
and BASE=CLS keep the floor. A user-supplied `!input` condition (e.g.
`auto_ventilate_condition`) can **not** carry this decision: `effective_state` is a Jinja
variable and cannot evaluate one, so a branch honouring it would diverge from the cascade
that `state_gates`, `recovered_state`, the resident VENT leaves and the contact handler all
read. Sites that follow the flag besides the two cascades: the shading-start vent-floor
branch (stands down), the contact handler ("Window tilted - Sun shading takes precedence",
placed above the partial-ventilation leaf so first-match wins), the `not window_any_now`
gates of branches 3 / 3b (tilt stage and alternate depth must keep tracking while tilted)
and the `shd` arm of the force-disable `recovery_target` chain (`vent_blocks_shading`).
The closing handler's tilted leaf is deliberately unchanged — it clears `shd` anyway, so
the transition ends in a legitimate `vnt`.

**LOCKOUT target (`effective_lockout_position`):** LOCKOUT drives to the optional
`lockout_position` input ("Full Ventilation Position"), which falls back to
`open_position` when unset — for setups where "open" is not "cover fully up" (e.g.
a terrace-door blind whose open position is 0 % with open slats). Every lock
consumer must read `effective_lockout_position` / `in_lockout_position`, never the
raw open position: `state_targets.lock`, `state_gates.lock`, the contact-opened
branches, and — critically — the two flows that deliberately drive to the open
target while the lockout window may be open: "Normal opening of the cover" (the
Bug Pattern AG fall-through) and the shading-end "Move cover after shading end"
(reachable at the lockout position because the shading-end lockout branch gates on
`current_below_ventilate`). Both swap their target to `effective_lockout_position`
when `effective_state == 'lock'`; with the input unset that is byte-for-byte the
old behavior. The lock tilt target stays `open_tilt_position`.

---

## Transition Architecture (CCA 2026.07.03)

The action tree follows an **event → reducer → reconciler** structure within the
limits of HA YAML (user-supplied `!input` conditions can only be evaluated in
`conditions:`/`if:` — so branch *dispatch* stays a `choose:` skeleton, while
state computation and actuation are centralized). Variables assigned inside
`if`/`choose` normally update the enclosing script scope; `repeat` is the
important local-scope exception. This outer-scope behavior requires Home
Assistant 2025.4, which is why the blueprint declares `min_version: "2025.4.0"`;
lowering it silently breaks the transition anchors and recovery decisions.

**Every leaf branch computes exactly two things, then calls one shared anchor:**

```yaml
sequence:
  - variables:
      will_drive: "{{ <drive gate> }}"       # only when a gate exists
      drive_plan:                             # actuation plan (reconciler output)
        run: "{{ will_drive }}"               # plan permission (default false)
        move: "full"                          # 'full' (default) | 'tilt' (tilt only)
        action_set: "up"                      # before/after action selector
        target: "{{ open_position | int }}"
        target_tilt: "{{ open_tilt_position | int }}"
        tilt_first: false                     # reposition tilt to 0 first
        delay_s: "{{ drive_delay_standard }}" # pre-drive delay (0 = none)
      update_values:                          # state transition (reducer output)
        bas: "opn"
  - *apply_transition
  - stop: "..."
```

A branch may additionally set `log_user: "<short English phrase>"` — the reason
line for the cover logbook (`enable_logbook_cover`, Invariant 12). Leave it
unset in pure state syncs and in pending/retry cycles.

`&apply_transition` performs, in fixed order: project a real position/relevant
tilt delta → optional delay → live pause/instance ownership check → for a
full drive, select and run the before-action → re-check ownership live → set
`drive_dispatched` at the first alignment/cover/tilt service stage, with another
live check before the cover and tilt stages after intervening waits → run the
after-action only if some stage was dispatched. When
`prevent_default_cover_actions` is configured, the user after-action is the
movement carrier; after the same live ownership checks, entry into that
custom-only pipeline sets `drive_dispatched` so the action runs and owns `d`
and the automatic `man: 0` clear. A raw `move: tilt` plan has no
before-action and enters the same live-gated `*tilt_move_action` directly
→ optional cover-logbook line (only with `enable_logbook_cover`, and only when
the branch drove or set `log_user`) → **unconditional** `*helper_update`.
The logbook step sits *before* the persist so the anchor still ends in the
helper write (pinned by `TestApplyTransitionAnchorShape`). Because the helper write is structural,
every path through a leaf branch is terminal (Invariant 2 / Bug Pattern AK by
construction). `*helper_update` merges `update_values` into the helper
**re-read live at write time**, not into the trigger-time `helper_json`
snapshot — under `mode: queued` that snapshot can be minutes stale and merging
into it resurrects state that intervening runs already cleared (Bug Pattern
AQ / #641); the snapshot is only the fallback for an invalid or pre-v6 live
value. `tests/test_apply_transition_architecture.py` enforces this:
no raw `*helper_update` / `*drive_with_actions` / `*tilt_move_action` outside
the anchor definitions and the v5→v6 migration persist.

**Event normalization** (post-forecast variables block): the live sensor idioms
are computed once per run and referenced by all branch conditions —
`window_opened_now`, `window_tilted_now`, `window_any_now`, `lockout_now.closing/
shading_start/shading_end`, `shading_once_guard_ok`, `drive_delay_standard`.
An invalid (unavailable/unknown) contact reads as "off" in every handler —
tilted branches gate on `not window_opened_now`, never on an explicit
"opened reads closed" check (a stricter `window_opened_clear` variant existed
until 2026.08.13 and caused Bug Pattern AT / #650).
The contact handler re-reads the sensors **after its settle delay** into local
`contact_opened_now` / `contact_tilted_now` / `was_ventilating` — do not replace
those with the trigger-time globals. `override_blocks.opening/closing/
ventilation/shading` (top variables block) centralizes the manual-override
gates (`helper_state_manual and override_flags.X`).

**Reconciler projection** `state_targets` and **drive gates** `state_gates`:
`state_targets` maps each state (`lock`/`opn`/`vnt`/`shd`/`cls`) to
`{target, target_tilt, action_set}`; `state_gates` maps each state to the
standard drive gate `force_allows_X and (effective_state != X or not
in_X_position)`. The `lock` gate is deliberately stricter: it requires
`live_force == 'non'`, `effective_state == 'lock'` and a position delta, so a
contact or resident event cannot move to lockout while Force owns the cover.
Branches that "drive to state X" (force enable, force
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

**`will_drive` is plan permission, not proof of movement.** Branches put the
effect gates into `drive_plan.run` and omit `man` from ordinary updates. The
terminal actuation anchors add position/tilt tolerances and live ownership;
only their `drive_dispatched` result lets `helper_update` stamp `d` and clear
`man`, so queued snapshots and no-op targets cannot impersonate a drive. The
explicit exception is custom-actions-only mode: CCA cannot inspect the user's
action sequence, so entering that configured movement pipeline after all gates
is the dispatch contract.

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
