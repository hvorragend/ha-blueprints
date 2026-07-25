# CLAUDE.md — Cover Control Automation (CCA) Blueprint

## Overview

`blueprints/automation/cover_control_automation.yaml` is a Home Assistant automation blueprint (Jinja2 + YAML). It controls roller blinds/shutters based on time, sun position, window contact sensors, and presence detection.

This file holds only the always-binding rules. The detailed rationale, the design
decisions, the recovery architecture and the full regression catalog live in
`.claude/skills/cca-assistant/references/` — read the matching file **before**
changing the area it covers (see the map below). After any change, run
`pytest tests/ -v`; many of the rules below are pinned by tests.

## Read this before you touch that

| Before changing… | Read first |
|---|---|
| `effective_state` / `recovered_state`, the cascade, `state_targets`/`state_gates`, transition anchors, `trigger_variables:` | `.claude/skills/cca-assistant/references/architecture.md` |
| Any branch condition, drive gate, `update_values`, timestamps, pending logic | `.claude/skills/cca-assistant/references/invariants.md` |
| Anything that looks asymmetric/inconsistent and tempts you to "harmonize" it | `.claude/skills/cca-assistant/references/design-decisions.md` |
| Availability gates, `t_recovery`, `automation_resumed`, recovery gate — or **adding any new gate/condition that can stop a run** | `.claude/skills/cca-assistant/references/recovery.md` |
| Branch conditions, global conditions, trigger `enabled:`, helper-JSON regexes, deferrals/handoffs between flows | `.claude/skills/cca-assistant/references/bug-patterns.md` |

If a change touches one of these areas and you have not read the file, assume the
"obvious" fix reintroduces a documented bug — that is how most patterns in the
catalog happened.

---

## Helper JSON Schema (v6)

State is persisted as a JSON string in an `input_text` helper:

```json
{"bas":"opn","shd":1,"pnd":"non","win":"opn","frc":"non","res":1,"man":0,
 "ts":{"opn":0,"cls":0,"shd":0,"due":0,"arm":0,"man":0},
 "v":6,"t":0,"d":0}
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
| `ts.opn`/`ts.cls` | Unix ts | Last base-state switch to open / closed |
| `ts.shd` | Unix ts | Last shading state change (0↔1) |
| `ts.due` | Unix ts | Fire time of armed pending (`0` when `pnd == 'non'`) |
| `ts.arm` | Unix ts | First-arming anchor of the retry sequence, preserved across retries (`0` when `pnd == 'non'`) |
| `ts.man` | Unix ts | Last manual override event |
| `t` | Unix ts | Last helper write (every run stamps it) |
| `d` | Unix ts | Last write of a run that drove the cover (`drive_plan.run`) |

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

`effective_state` returns `lock | opn | vnt | cls | shd`. VENT is a *floor*, not a
target: BASE=OPN beats it only when an opening automation actually exists
(`is_opening_scheduled`, derived from the `enabled:` gates of every `bas='opn'`
writer incl. the resident opening — Bug Patterns Z + AL + AO). Full rationale and
the `base_target` implementation: `references/architecture.md`.

---

## Architectural Invariants — ALWAYS FOLLOW

One line each; full rationale, examples and edge cases in
`references/invariants.md`. Violating any of these is a bug even if tests pass.

1. **Never put position checks in branch conditions** — they belong in the branch's `will_drive` gate. A priority branch must always be consumed.
2. **Every branch ends in `*apply_transition`** — its helper write is unconditional. Never call `*helper_update` / `*drive_with_actions` / `*tilt_move_action` directly from a branch (structurally enforced by `tests/test_apply_transition_architecture.py`).
3. **Realtime vs. helper state** — `states(sensor)` is live; `helper_json.*` is stale until the write. `effective_state` reads live contacts only while `is_ventilation_enabled`. In resident handlers always read the live sensors.
4. **`resident_flags.*` reads the live sensor** — no stale-state problem; don't add workarounds.
5. **`opened` beats `tilted`** — every tilted branch must check that the opened contact is not active.
6. **Lockout is independent of `resident_allow_ventilation`** — it is a safety feature; gate only the tilted sub-branch.
7. **`man: 0` only when actually driving** — encoded via the `will_drive` pattern; never in pending timers or pure state syncs. (Documented exceptions: midnight reset, `override_expired`.)
8. **Timestamp rules** — `ts.shd` only on a real `shd` 0↔1 change; `ts.arm` preserved across retries; `pnd: 'non'` implies `ts.due`/`ts.arm` = 0; every pending execution path must be terminal (re-arm or clear); contact-handler branches must not touch `pnd`/`ts.due`/`ts.arm`; `d` only when `drive_plan.run` was true (never on pure state syncs — the manual-detection settle window keys off it).
9. **`ts_now` at point of use** — never a global variable (delays make it stale).
10. **`trigger_variables:` is a limited template context** — no `states()` / `is_state()` / `state_attr()`; move state reads into action-scope `variables:`.
11. **`pnd` is a single enum** — start and end pending are mutually exclusive by schema; both arming branches gate on the opposite pending to prevent ping-pong.
12. **Logbook = `trigger.id` + `update_values` dump** — no reason-inference table; add `log_extra` only where genuinely needed.
13. **`recovered_state` must mirror `effective_state`** — every cascade change lands in both, same commit; extend `TestCascadeParity`, never weaken it.
14. **Anchor bodies are pre-rendered on every run** — every runtime-context reference inside an anchor body needs a template guard (`repeat is defined`, `| default(...)`); those guards are load-bearing.

---

## Code Style

- **No implementation comments in the blueprint YAML** (no "why this is placed here" notes — that belongs in the reference docs or commit messages) and **no Jinja2 `{# … #}` comments** in templates.
- **Boolean variables must render as a single `{{ … }}` expression.** A bare `false` word from a `{% if %}` block renders as the *string* `"false"`, which is truthy after `literal_eval` fails. Multi-branch `{% if %}` blocks are only allowed for variables consumed as strings or numbers.
- Guard every `states(x)` / `state_attr(x, …)` on an input whose `default` is `[]` with `x != []` — in every context (Bug Pattern AF).
- Use YAML anchors for repeated sequences; extract shared expressions into `variables:`; do not over-abstract.
- Every `choose:` branch and every drive/helper step needs a unique `alias:` (traces are the primary remote-support tool).

## Language Conventions

- **CLAUDE.md, reference docs, code comments**: English.
- **Chat responses**: German.

---

## Version Bumping

The version string exists in **two** locations — update both together:

1. Description (user-facing): line ~7 → `**Version**: YYYY.MM.DD`
2. Runtime variable: `version:` at the top of the `variables:` block (`grep -n 'version: "20' <blueprint>`)

Changelog: `docs/CHANGELOG.md` (symlinked from `blueprints/automation/CHANGELOG.md`), new `# CCA YYYY.MM.DD` section on top, existing emoji conventions (🐛 Fix, 🔧 Improvement, ✨ Feature).

---

## Quality Gates (before every commit)

- `pytest tests/ -v` — all tests pass (`pip install pytest jinja2 pyyaml`).
- No logic gaps: every reachable sensor-state combination has a defined outcome; the cascade is respected in every branch.
- No HA warnings/errors: no schema violations, no Jinja2 runtime errors, no undefined variables (guard with `| default()`), current action syntax.
- Every input has a `name:` and a non-technical `description:`; optional inputs have `default:`/constrained selectors; no internal field names in user-facing text.
- The helper JSON is the primary debug artifact — keep every field meaningful and current; log a warning on unexpected states.
- Adding/removing/reordering a branch of the main dispatch `choose:` requires updating the trace tools' branch maps (`tests/test_trace_tools_branch_map.py` pins this; details in `references/recovery.md`).
