# CCA Restart / Outage Handling (the recovery)

Read this before touching: the global availability gates, any `t_recovery`
trigger, the recovery gate, `recovered_*` variables, `automation_resumed`,
or before adding ANY new gate/condition that can stop a run (the orphan-audit
rule at the end applies to every new gate).

---

### Restart / outage handling: block on state-critical entities, recover via `t_recovery`

Two halves of one mechanism. Neither works without the other.

**The recovery half is opt-in (`enable_recovery`, default `false`, CCA 2026.07.13).**
Users reported unwanted cover movements right after a HA restart — the recovery is
*supposed* to move the cover when the cascade demands it (e.g. applying a stored
shading intent or catching up a missed opening), but many users prefer "never touch
the covers after a restart" over catching up.

**The dividing line is cause vs. prevent, not "recovery code vs. other code".**
A mechanism is opt-in when it can *cause* a movement; it is always active when it
can only *prevent* a wrong one. That single rule places all three pieces:

- **Opt-in.** A *source* `t_recovery` trigger whose source can only be *caught up*
  carries `enabled: "{{ is_recovery_enabled and ... }}"` — filter at the trigger,
  same rationale as #550: no run, no trace, no drive. That is every source whose
  state CCA does **not** persist: cover, helper, position sensor, contacts, resident,
  brightness, sun, forecast, custom shading sensor, calendar, workday — **and the
  force pause** (`is_paused` is read live and nothing about it is stored, so its
  return leaves no stale claim; the only thing to do would be to drive back into the
  force the pause suspended). Inside the gate, `will_drive`
  (= `is_recovery_enabled and not is_paused and recovery_allowed`) gates the drive, `new_base` gates
  the re-derived base state (writing `bas: 'cls'` for a swallowed closing is a
  *deferred* movement — a later branch would drive into it), and `recovered_pending`
  refuses to arm a shading pending (it would drive later too). Note `recovered_base`
  itself stays **unconditional** — only the *write* (`new_base`) is gated. It feeds
  `recovered_state`, and that only matters on a run that is allowed to drive anyway.
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
off (the default). "opt-in" = the repair *causes* a movement (it catches something up),
so the switch buys it. "always" = the repair only *prevents* a wrong movement, so it
runs either way — via the resumed-run hygiene or an always-on fallback.

| Trigger | Latches? | Cost of a dropped run | Repaired by | Opt-in? |
|---|---|---|---|---|
| `t_open_*` / `t_close_*` / `t_calendar_event_*` | no (window closes) | missed opening/closing | the recovery gate's `recovered_base` (re-derived from schedule/calendar), written via `new_base` | **opt-in** |
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

**Known limitation — recovery bypasses the direction-specific additional conditions:**
`recovered_base` re-derives the base state from the schedule/calendar alone
(`is_up_enabled and is_daytime_phase` / `is_down_enabled and is_evening_phase`).
The user-supplied `auto_up_condition` / `auto_down_condition` — which gate **every**
opening/closing trigger in the normal flow, including the Late safety net — are
**not** evaluated by the recovery gate. A scheduled movement that the user's additional
condition deliberately suppressed is therefore "caught up" by the recovery as if
it had merely been missed (real-world report: opening blocked by an additional
condition all morning; a restart flipped `bas` to `opn` and the cover opened after
the end-pending). Structural cause: `!input` conditions can only be evaluated at
fixed YAML positions (`conditions:`/`if:`), and which condition would have to
apply depends on the dynamically computed recovery target; evaluating them would
require splitting the recovery leaf per flip direction. Documented trade-off:
`auto_global_condition` **is** respected (it is a global condition, so it drops
the whole recovery run) — users who suppress scheduled movements via additional
conditions should mirror that logic in the global condition or leave
`enable_recovery` off (the default).

---
