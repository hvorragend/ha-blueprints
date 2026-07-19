# CCA Restart / Outage Handling (the recovery)

Read this before touching: the global availability gates, any `t_recovery`
trigger, the recovery gate, `recovered_*` variables, `automation_resumed`,
or before adding ANY new gate/condition that can stop a run (the orphan-audit
rule at the end applies to every new gate).

---

### Restart / outage handling: block on state-critical entities, recover via `t_recovery`

Two halves of one mechanism. Neither works without the other.

**The catch-up half is opt-in, and since CCA 2026.07.13 V6 it is a three-way choice**
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
  suspended). Inside the gate, `will_drive`
  (= `recovery_catch_up and not is_paused and recovery_allowed`) gates the drive, the
  direction `choose:` gates the re-derived base state (writing `bas: 'cls'` for a
  swallowed closing is a *deferred* movement — a later branch would drive into it),
  and `recovered_pending` refuses to arm a shading pending (it would drive later too).
  Note `recovered_base` itself stays **unconditional** — only the *write* (`new_base`)
  is gated.
- **Always active: the `t_recovery` triggers of the five gate sources** (cover, status
  helper, custom position sensor, both window contacts — CCA 2026.07.13 V6). Third
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
made (CCA 2026.07.13 V6):

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
{% for entity in critical_entities if states[entity] is not none %}
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

**Saving the automation is the same *event*, and it is by far the most common one.** When a user edits the blueprint inputs in the UI, HA removes the automation entity and adds it back, so `last_changed` is stamped with the save time and every trigger is attached anew. Verified against a live instance: after a restart every automation shares one `last_changed`, while the four re-saved ones each carry their own save timestamp. HA reloads **only the edited automation** (a save on some other automation does not disturb a CCA instance — its own attached triggers merely receive the reload *event*, see piece 1b), but `automation.reload` / *"Reload automations"* / a restart re-attaches **all** of them, so every CCA instance resumes at once — `max: 25` covers that. A save is **not** mechanically identical to a toggle, though, and the prompt differs (Bug Pattern AM): a toggle keeps the entity, so the resume *template* sees it come back; a reload re-creates the entity before its first state write, so only the reload *event* reports it.

Two consequences worth knowing, neither of them a defect: with `enable_recovery` on `always`, every save runs the full catch-up, so *changing a setting can move the cover* (a save is a re-attach, so `is_restart_run` is true — `outage` mode does not catch up on one). And a run that is inside a `delay:` when the save lands is killed with the queue, so its helper write is lost — the resume hygiene re-reads `win`/`frc`/`res` and repairs it, but `bas` is only re-derived when the catch-up is allowed.

**There is no way to tell a save from a multi-day absence**, and no reason to try: `last_changed − helper.t` is arbitrarily large in both cases (a quiet night leaves the helper hours old), and the hygiene is a no-op on a fresh helper anyway. Do not add a "the helper is recent, skip the recovery" heuristic — it would silently disarm the resume path for exactly the users whose automation sat idle before going down.

Three pieces, and the first one is the only non-obvious part.

**1. The resume trigger — how to fire on a condition that is already true.** The attach
moment is read **live** from the automation's own state, not from `this` (Bug Pattern AM,
issue #617): HA's `_async_enable` is explicitly *"not expected to write state to the state
machine"*, so on `automation.turn_on` the `this` snapshot taken at trigger attach still
holds the **pre-enable** state — `this.last_changed` is the switch-**off** moment, and a
template trusting it is already true at the arming render and can never fire. The only
snapshot field that cannot go stale is `this.entity_id`; `trigger_variables` captures it
as `automation_entity`, and the template reads the switch-on time from the state machine,
gated on the state actually being `'on'`:

```jinja2
{% set automation_state = states[automation_entity] if automation_entity != '' else none %}
{% set attached = as_timestamp(automation_state.last_changed, 0)
     if automation_state is not none and automation_state.state == 'on' else 0 %}
{{ attached > 0 and (helper.t | default(0) | int) > 0 and
   as_timestamp(now()) > attached + 60 and
   (helper.t | default(0) | int) < attached }}
```

At the attach render the state machine still reads `'off'` → `attached == 0` → `false` →
**armed** (a template trigger arms only on a false setup render). The `off → on` write that
follows the attach lands as a tracked state change — the template reads
`states[automation_entity]` — and re-renders: now within the 60 s offset → still false. A
minute later it flips → fires `t_recovery`. Once the recovery has written the helper, `t`
overtakes the attach time → `false` again → re-armed for next time. **Without the offset
this trigger would fire before a regular trigger of the same minute could cancel it**; and
without the live read it would never fire at all — the exact trap it exists to escape. It
polls nothing: an automation that was never off never fires it (its own `last_changed` is
ancient, and the helper has been written since). It also covers a restart when the
`homeassistant_started` attach happens within the offset of the entity's first state write.

**1b. The reload event — the path no template can see.** A reload or UI save re-creates the
automation entity, and `async_added_to_hass` attaches the triggers **before** the entity
platform writes the first state: `this` is `None`, so there is no entity id to capture and
`automation_entity` is `''` — the resume template stays dark for this path, permanently
(its variables are frozen at attach). The `automation_reloaded` **event trigger**
(`t_automation_reloaded`) covers it: HA fires that event once per reload — and every UI
save of the blueprint inputs is a reload of the edited automation — *after* the new
entities are attached, so the freshly resumed instance receives it and the recovery gate
claims the run via `automation_resumed` (action scope, where `this` is re-read at run
time and reliable). The event reaches **every** automation, not just the saved one; a run
the gate does not claim is stopped silently by the *"Reload event without a resume"*
pre-dispatch step (it has a `PRE_DISPATCH_DEFINITIONS` entry in both trace tools). The
event also makes the sibling claims (`instance_activated`, `midnight_reset_missed`)
prompt on a reload instead of waiting for the next regular trigger.

**The template also mirrors the availability gates** (CCA 2026.07.13 V6): `critical_ready` (cover, plus the custom position sensor when it is the source) and `contact_ready` (the Tier-2 rule verbatim: a stateless contact only blocks while `helper.win != 'cls'`, scoped to `is_ventilation_enabled`). This is not decoration — the trigger has exactly **one** false→true edge, and an edge that fires into a run the gates block is *consumed*: the template stays true, never re-fires, and `automation_resumed` stays armed until the first regular trigger, which the claim then eats. With the opt-in **off** that claimed run is a hygiene-only `stop:` — a restart where the cover takes longer than ~90 s to come back (Zigbee hub after a host reboot) would swallow e.g. the 07:00 opening, and with the opt-in off no gated `t_recovery` source exists to run the hygiene earlier. With the readiness clauses the edge arrives exactly when the run can pass the gates (the `states()` reads register listeners, so the cover's return re-evaluates the template). The user's `auto_global_condition` can still block the run — not mirrorable, pre-existing, documented under "Not repairable, by design". Tests: `TestResumeTrigger::test_it_waits_for_the_cover_to_be_usable` and siblings.

**2. Any trigger on a resumed run is claimed by the recovery.** `automation_resumed` (`helper_ts_write < this.last_changed`) is a second entry condition of the recovery gate, and **that is why the recovery gate runs before the dispatch**. The cover only ever moves through a trigger, so making every trigger recalculate first means acting on an untrusted helper is *structurally impossible*, not merely unlikely. It self-clears the moment the recovery writes the helper. This is the safety net under piece 1: even if the resume trigger never fired, nothing can move on stale state.

**3. The manual-override gate moved out of the entry conditions.** The recovery gate used to be skipped entirely on `man == 1`. That would mean a stale shading or a dead pending survives the recovery whenever an override is active. The gate now lives in `recovery_allowed`, so the **helper hygiene always runs** and only the *drive* is blocked (lockout still overrules, Invariant 6).

**Stale day — the midnight reset that never ran.** `stale_day` = the helper was last written on an earlier date. BRANCH 11 clears `shd`/`pnd` every night at 23:55; if the automation was off, it did not. So a shading from three days ago still reads as active and the first trigger would drive the cover into the shading position — at night, even. The recovery therefore emulates that reset: `recovered_shade` drops `shd`, `pending_is_stale` also fires on `stale_day`, and `ts.opn`/`ts.cls` are zeroed (they gate the once-per-day open/close guards and must not suppress today's run).

**But `ts.shd` is deliberately *not* stamped** when `shd` is cleared 1→0 here — and since CCA 2026.07.19, BRANCH 11 omits the stamp too: its random delay plus queued runs can push the 23:55 write past midnight, where the stamp lands on the *new* day and the once-per-day guard blocks that whole day (Bug Pattern V, updated there). Both clears now leave `ts.shd` at the last real `shd` transition, which is always a same-day-or-earlier stamp and never suppresses the coming day.

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
mistake CCA 2026.07.13 V6 fixed: with the opt-in off, the *only* ungated entries into the
gate were the resume trigger (needs a re-attach) and the force entities (need the *force*
entity to have dropped out). A mid-runtime outage of the cover, the helper or a contact
produced neither — so every "always" row below was dead on paper for exactly the scenario
the gates create. The five gate sources are now ungated too; check any new "always" row
against *which trigger actually fires it*.

| Trigger | Latches? | Cost of a dropped run | Repaired by | Opt-in? |
|---|---|---|---|---|
| `t_open_*` / `t_close_*` / `t_calendar_event_*` | no (window closes) | missed opening/closing | the recovery gate's `recovered_base` (re-derived from schedule/calendar), written via `new_base` — **but only when the direction's `auto_up_condition`/`auto_down_condition` still allows it** (V6): a movement the user's condition suppressed was not missed | **opt-in** |
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
| `t_shading_reset` (23:55) **while the automation is off** | **yes** | `shd`/`pnd` from an earlier day still read as active → the next trigger drives into a days-old shading position | the recovery gate's `stale_day` → `recovered_shade`, `pending_is_stale` (**without** stamping `ts.shd`) — and since 2026.07.19 the `midnight_reset_missed` **claim** makes sure a recovery actually runs: `stale_day and (shd or pnd)` turns the next trigger of any kind into one, so the repair no longer depends on something else entering the gate | always — this one *prevents* a wrong drive rather than catching one up |
| *(the automation itself is switched off and on, **or re-saved** — a UI save re-creates the entity)* | — | **nothing fires at all** — no entity changed, `homeassistant: start` does not fire, and every latching trigger is already true at attach time | a toggle: the **resume trigger** (live read of the automation's own `last_changed` + 60 s offset — **not** `this`, whose timestamps are pre-enable; Bug Pattern AM); a reload/save: the **`automation_reloaded` event trigger** (`this` is `None` at a reload attach, so the template path is dark there); `automation_resumed` makes the recovery gate claim any trigger as a backstop for both | always — neither the resume trigger nor the reload event carries the opt-in gate |
| *(`instance_active` is off — this instance is not in charge)* | — | **every** trigger of the off period is dropped, so all the latching rows above happen at once, and the helper is arbitrarily old when the instance comes back | `t_instance_activated` (prompt) + the `instance_activated` claim (backstop for a swallowed edge) → the recovery gate re-derives everything | always — an activation is exempt from the opt-in (but **not** from `is_restart_run`) |
| *(`instance_active` itself drops out)* | — | sixth gate source: while it is unusable the gate blocks every run — and the outage may have eaten a hand-over's `off → on` flank, which HA never keeps | its own ungated `t_recovery` trigger — and, unlike the five other gate sources, the return run is **not** hygiene-only with the catch-up off: the helper froze while the gate blocked, so `instance_activated` reads true on the return and the run takes over (deliberate — a dropout return is indistinguishable from a swallowed hand-over, losing a real one strands the cover, and the false positive drives to the cascade target anyway) | always — **even with the catch-up off** |
| *(helper is `unknown`)* | — | init/repair step unreachable → automation permanently dead | helper gate blocks on `unavailable` **only** | always |

`override_expired` is a global variable, not a branch-local one, because `recovery_allowed` and the `man` write both need it, and the reset triggers latch (see the table above). It clears `man` without driving, a deliberate Invariant 7 exception (same class as the midnight reset).

**Rule for any new gate:** before adding a condition that stops a run, list every trigger it can suppress and ask *"if this fires exactly once and I drop it, does anything ever fire again?"* If the answer is no, the gate needs an exemption (contact triggers), a repair path (helper init), or a re-evaluation in the recovery gate (override, shading, force, base). Two of the three gates in this design needed one — assume the next one does too.

**Not repairable, by design:** `auto_global_condition` (the user's own global condition). If it is false when the recovery run fires, the run is dropped and nothing re-triggers when it later becomes true — CCA cannot watch an arbitrary user condition. This is pre-existing behavior for every trigger, not new.

**The direction-specific additional conditions gate a caught-up base flip (CCA 2026.07.13 V6).**
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

```text
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

## Several instances, one cover: `instance_active` (CCA 2026.07.19)

The multi-instance pattern (one CCA automation per season / presence mode / whatever, each
with its own helper and its own settings, an external automation picking which one is live)
is **an emergent property of the recovery**, not a new mechanism: a take-over is exactly what
the recovery gate already does — re-derive `bas` from the schedule, re-read `win`/`res`/`frc`
live, drop a stale shading, re-evaluate the shading conditions, drive to `recovered_state`.
`instance_active` only supplies the *gate* and the *entry point*; every line of the take-over
is the recovery.

**Why a first-class input and not just `automation.turn_off`.** Toggling the automation does
work — the re-attach stamps `this.last_changed` and the resume trigger fires ~60 s later
(Half 1b). But the obvious user-side alternative, gating the instance with
`auto_global_condition`, is **silently broken**, and that is what the input exists to prevent:
the triggers still fire, the runs are dropped, and when the condition goes true again *nothing
fires* — `this.last_changed` never moved, so `automation_resumed` cannot see it, no latching
trigger re-fires, and the first regular trigger acts on a helper that may be months old. It is
the "Not repairable, by design" row of the orphan audit, turned into a feature by accident.
`instance_active` is that gate **made repairable**: CCA owns it, so it can watch it and heal it.
(Since 2026.07.19 the worst artifact of a foreign gate self-heals too: `midnight_reset_missed` — see
below — claims the first run after any blockade that let a shading survive midnight. The rest
of the staleness, `bas`/`man`, is re-derived or latched as documented in the audit rows.)

**Two pieces, mirroring Half 1b exactly** — and for the same reason, so do not collapse them:

1. **`t_instance_activated`** (`from: [off, false]` → `to: [on, true]`) — the *prompt*. Makes
   the take-over immediate instead of waiting for the next trigger. Not gated on
   `is_recovery_enabled`. With `instance_active_value` set (a dropdown option, an inverted
   boolean), a second trigger shape carries the same id: any valid → valid change of the
   entity, with arrivals at a foreign value dropped by the gate. `not_from:
   [unavailable, unknown]` keeps it exactly as restart-proof as the plain flank — the
   `recovery_catch_up` exemption for this trigger id relies on that, in both shapes.
2. **`instance_activated`** (`helper.t < switch.last_changed`) — the *claim*. A state trigger
   has exactly one edge, and the availability gates can swallow it (the cover was still coming
   back). The claim turns **any** later trigger into the take-over and self-clears on the first
   helper write. Same shape as `automation_resumed`, and it is what makes the feature robust
   rather than merely likely to work — `automation_resumed` itself cannot stand in for it,
   because an activation re-attaches nothing: `this.last_changed` does not move, so that claim
   cannot see the event at all. Unlike `automation_resumed` it fires on a fresh helper
   (`t == 0`): a brand-new instance's first activation *is* a take-over.

**The gate has no trigger exemptions**, and that is deliberate — the one place where it differs
from the contact gate. An inactive instance must not even record a cover movement as manual:
the *other* instance made it, and a stored `man: 1` comes back to block this instance's own
take-over (`recovery_allowed`). The contact gate exempts `t_manual_position`/`t_manual_tilt`
because that handler records something CCA needs; here there is nothing to record, because CCA
is not in charge.

**The take-over catches up regardless of `enable_recovery`.** The opt-in guards against
*restarts* moving the cover; an activation is an explicit "you are in charge now", and an
instance that takes charge and leaves the cover where the previous one parked it has done
nothing at all.

**But the two activation signals are not equally strong, and `recovery_catch_up` must not treat
them as one** — doing so was a real bug during development:

- **`t_instance_activated` is unambiguous.** Only a real `off → on` flank fires it; a restart
  returns the entity as `unavailable → on`, which its `from: [off, false]` does not match. It
  therefore needs **no** `is_restart_run` guard — and must not have one: that flag stays true
  for 300 s after a re-attach, and **saving the automation is a re-attach**. Guarded, the
  sequence "save the automation → flip the switch to try the hand-over" leaves the cover
  standing — which is the first thing anyone does with this feature.
- **`instance_activated` is a timestamp proxy** (`helper.t < switch.last_changed`), and on a
  restart the gating entity is recreated with everything else, so its `last_changed` points at
  the boot and the proxy reads true. This one **must** stay behind `is_restart_run`, or the
  exemption would smuggle every restart past the opt-in — exactly what the opt-in promises not
  to do.

Pinned by `TestCatchUpOnActivation` (both halves, in both directions).

**`override_expired` is voided by an activation**, whatever the reset rules say. This is the
one bug the feature would otherwise have shipped with: an instance that went inactive with
`man == 1` comes back with `recovery_allowed` false, never positions the cover, and — with a
reset rule that cannot fire on its own (`is_reset_disabled`, or reset-in-position while the
cover is elsewhere) — stays blocked **for good**. The override belongs to the previous shift;
while the instance was off it could not even see the cover being moved, so there is nothing
left for it to protect.

**Bug Pattern T, fourth recurrence, caught at design time:** the take-over run consumes
`shading_start_warranted` (via `recovered_pending`) and the parsed calendar boundaries (via
`recovered_base`) — and thanks to the claim it can arrive under **any** trigger id. Both load
gates therefore match `t_instance_activated` **and** `instance_activated`, not just the trigger
id. Any new consumer of a load-gated value must re-ask *which trigger ids can reach it*.

**Half 0 applies too.** A *gone* (disabled/deleted) gating entity would make the gate block
every run forever with no log line — so the gate lets `states[x] is none` through
(`instance_active == [] or states[instance_active] is none or states(...) in ['on', 'true']`)
and the mandatory entity validation names it and stops the run. `unavailable` (a real dropout)
**does** block, and the switch carries its own ungated `t_recovery` trigger: it is a sixth gate
source, so its outage eats the latching triggers exactly like the other five. Unlike the other
five, though, its return run is **not** hygiene-only with the catch-up off: the helper froze
while the gate blocked, so `instance_activated` reads true on the return — and a hand-over
whose `off → on` flank fell into the outage looks exactly the same, because HA only keeps the
final `on`. The safe read is to take over: losing a real hand-over strands the cover, while the
false positive drives to the position the cascade wants anyway. (This only matters for
physically-backed gating entities — `switch`, `binary_sensor` — which can drop out mid-runtime;
the recommended `input_boolean` only goes `unavailable` around a restart, and there
`is_restart_run` already holds the proxy back.) Pinned by `TestSwitchDropoutTakesOver`.

**One helper per instance — a shared one is possible and wrong.** CCA cannot enforce it (it
cannot see its siblings), so this is a documentation-only rule. The reason is what the helper
holds: **not one fact about the cover that is not re-derived live anyway** (`win`, `res`, `frc`
are read from the entities on every take-over). Everything it *uniquely* stores is an
**interpretation under one instance's settings** — `bas` ("*my* schedule says open"), `shd`
("*my* shading is active" — the sibling may not even have shading enabled), `pnd`/`ts.due`/
`ts.arm` (armed with *my* waiting times and thresholds), `man` ("someone overrode *me*"),
`ts.opn`/`ts.cls`/`ts.shd` (the once-per-day guards of *my* settings). Sharing does not share
state, it mixes readings. Three concrete failures:

- `recovered_shade` only drops `shd` on `stale_day`, so a **same-day** hand-over makes the
  incoming instance inherit a shading it has no concept of.
- `recovered_pending` deliberately preserves a non-stale pending, so the incoming instance
  inherits an armed pending and executes it against *its* conditions.
- The global conditions are evaluated **once per run**: an outgoing run sitting in a `delay:`
  finishes and writes the helper *after* the flip. With separate helpers it writes its own and
  nobody cares; with a shared one it clobbers the take-over — and its fresh `t` can even defeat
  the `instance_activated` claim (the `t_instance_activated` trigger id in `recovery_catch_up`
  is what keeps the drive alive there, a second reason that clause is not redundant).

The only thing sharing would buy is cross-instance once-per-day guards. Not worth it; the
handbook points users at an `input_boolean` in the additional shading condition instead.

**`instance_active` vs. the force pause — opposite mechanisms, and the pause must not be
abused for this.** The pause suppresses the **drive**; the run still executes and still writes
the helper (`bas`/`shd`/`win`/`frc` all updated — that is what makes the resume instant), and
nothing about the pause itself is persisted. `instance_active` suppresses the **run**; the
helper freezes and goes stale, which is why it needs the full take-over on return and the pause
needs no recovery at all. Same rule, opposite sides: the pause's `t_recovery` trigger is
**opt-in gated** (its return leaves nothing stale to correct — the only thing to do would be to
*drive*, which causes a movement), while `instance_active` is an **ungated gate source** (while
it is unusable the gate blocks every run, and its return run must be free to take over — see
above — because the outage may have hidden a hand-over).

Using the pause for mutual exclusion **almost** works and fails on exactly one thing: a paused
instance still watches, and `t_manual_position` is not gated by the pause (the manual handler
never drives, so no drive gate touches it). It therefore records the *sibling's* drives as
`man: 1` and comes back refusing to move. That is the same failure the instance gate's **lack
of trigger exemptions** is designed to prevent — the two facts are one fact.

**An in-flight run of the outgoing instance cannot move the cover after the flip
(CCA 2026.07.19).** The instance gate lives in the global conditions, and HA evaluates
those at *trigger* time — a run that was already queued, or sitting in a pre-drive delay
(up to minutes), when the hand-over happened would have driven to its stale target long
after the flip, racing the incoming instance's take-over. The loser of that race is the
user: the incoming instance reads the late movement as a manual override (it lands outside
its `helper.t + drive_time + 60` settle window) and then refuses to position the cover —
the exact failure the "switching automation must not drive" rule warns about, caused by
CCA itself. The actuation anchors (`cover_move_action`, `tilt_move_action`,
`drive_with_actions`) therefore re-read the instance gate **and the force pause** live at
the moment of movement (see the design decision "The force pause is part of every drive
gate" for the pause half and the accepted `man: 0` corner). The late run's helper write
still happens and is harmless — it writes this instance's *own* helper, which the next
activation re-derives anyway. The gone-entity rule of Half 0 is mirrored
(`states[x] is none` passes), so the mandatory entity validation stays the one place that
reports a deleted switch. Pinned by
`tests/test_apply_transition_architecture.py::TestActuationPointLiveGates`.

**Known limitations, accepted, documented in the handbook:** the once-per-day guards
(`ts.opn`/`ts.cls`/`ts.shd`) are per-helper, so a mid-day hand-over grants one more
open/close/shade; and the switching automation **must not drive the cover itself** — the
incoming instance reads that movement as a manual override and then refuses to position the
cover. Both are inherent to "one helper per instance" and are not worth a cross-instance
mechanism.

Tests: `tests/test_instance_active.py`.

---

## The missed-midnight-reset claim: `midnight_reset_missed` (CCA 2026.07.19)

A third self-clearing claim next to `automation_resumed` and `instance_activated`, for the one
blockade neither of them can see: runs dropped by a **foreign gate** (typically a long-false
`auto_global_condition`) with no re-attach and no owned entity to watch.

The trick is that CCA already has a daily heartbeat with a *persisted* footprint: the 23:55
reset clears `shd`/`pnd` every night. So `stale_day and (shd or pnd)` is **proof of a
blockade** — that state cannot survive a day boundary any other way — and the claim turns the
next trigger of any kind into a recovery, instead of letting it drive into a days-old shading
position (or defer an opening into a dead pending flow).

What it is deliberately **not**: a helper-age watchdog. A clean-but-old helper is normal — a
config whose opening/closing comes from the calendar *time control* (`t_calendar_event_*`,
not the `instance_active` gating calendar) may legitimately skip whole weekends, and the
23:55 reset only fires with shading enabled, so there is no daily-write guarantee to lean
on. Claiming clean-but-old runs would
swallow a real opening or closing with the catch-up off — the same reasoning that keeps
`is_restart_run` in front of the `instance_activated` proxy. The claim therefore requires the
surviving shading state, not the age. Residual, accepted: a blockade that leaves a *clean*
helper (`bas` drift, a latched override reset) is still only repaired when a recovery runs for
another reason — `bas` is re-derived by the regular handlers anyway, and `override_expired`
stays the documented answer for `man`.

Mechanically it is a fourth member of the recovery-gate claim group (manual triggers exempt,
as always), it satisfies both load gates (Bug Pattern T — the claimed run consumes forecast
and calendar data under any trigger id), and `recovery_catch_up` treats it like any outage
(drive in `outage`/`always`, hygiene-only in `never`). The helper write clears `stale_day`,
which clears the claim.

Tests: `tests/test_midnight_reset_missed.py`.

---
