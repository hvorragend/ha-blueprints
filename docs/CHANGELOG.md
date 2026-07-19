**Note:** Previous changes are archived here: [CHANGELOG_OLD.md](https://hvorragend.github.io/ha-blueprints/CHANGELOG_OLD).

# CCA 2026.07.19

- 🔧 **Improvement:** A configuration with **Morning Opening / Evening Closing enabled but no trigger source at all** — ⏲️ Time Control unchecked (or its calendar without an entity) and no Brightness/Sun sensor configured — is now reported instead of failing silently. Such a cover can never move automatically, and after the `2026.07.12` breaking change this is exactly the state that configurations from before ~2026.05 wake up in (user reports: *"evening closing and morning opening no longer work at all"*). The **✔️ Check Configuration** run (manual start) now names the problem in the log, and the [online validator](https://hvorragend.github.io/ha-blueprints/validator/) reports it as an **error** — including the case where a leftover legacy `time_control: time_control_disabled` silently selects no time source even though the checkbox is on
- 🔧 **Improvement:** The **⏲️ Time Control texts** no longer describe the feature only as a *constraint* on other triggers. For a pure fixed-time schedule ("just close at 22:00", no sensors) the Early/Late time fields **are** the schedule — unchecking ⏲️ Time Control disables opening/closing entirely. The checkbox label, the section help texts, the handbook and the FAQ now say so explicitly, and the FAQ gained a step-by-step checklist for *"I checked Time Control and it still does not open/close"*
- 🔧 **Improvement:** The validator's messages about **parameters removed in older CCA versions** now say explicitly that the leftover lines are ignored, harmless, and can simply be deleted — they previously read as if the configuration itself were broken
- 🐛 **Fix:** The handbook link in the description of the **Sun Shading / Sun Protection** section pointed to the contact-sensor page (`handbook/contacts#contact_delay_status`) instead of the shading page. It now links to `handbook/shading`
- 🔧 **Improvement:** A **sun shading that survived midnight** is now treated as proof that CCA was blocked for a whole day (the nightly 23:55 clean-up would otherwise have cleared it — think of a global condition that stayed false for days). The next run tidies up **first** instead of acting on the days-old shading state — previously it could drive straight into a shading position from last week. Deliberately conservative: an old-but-clean status is left alone, because quiet stretches are normal — a setup whose opening and closing times come from the calendar *time control* ("Open Cover"/"Close Cover" events) may legitimately skip whole weekends without a single run
- 🐛 **Fix:** The nightly 23:55 clean-up could **block the following day's sun shading** when its status write slipped past midnight — it waits a random moment (up to a minute), and a movement still waiting out a long drive delay can hold the queue even longer. The write then recorded the shading as changed on the *new* day, and with *"Shade cover only once per day"* enabled that whole day's shading was suppressed. The clean-up no longer touches the shading timestamp — it never needed it, and the day-boundary race disappears with it
- 🐛 **Fix:** A **⏸️ Force Pause switched on while a movement was already waiting out its drive delay did not stop that movement**. The pause was checked when the movement was *planned*, not when the cover actually started to move — with a fixed or random drive delay of several minutes, a cover could still drive well into the pause. The pause is now re-checked at the very moment the cover would move: a pause that arrives during the delay stops the movement (and keeps the *before/after actions* quiet, as promised since `2026.07.13`)
- 🔧 **Improvement:** 🎚️ **Hand-over hardening** for the multi-instance feature: a run of the outgoing automation that was already underway when the switch flipped — typically waiting out a drive delay — can no longer move the cover afterwards. Without this, the previous instance could drive the cover to its own, now outdated target *after* the new instance had already positioned it, and the new instance would then record that late movement as a **manual override** and refuse to touch the cover. Like the pause, the hand-over switch is now re-checked at the moment of movement
- ✨ **Feature:** 🎚️ **Several CCA automations can now share one cover** — one for summer and one for winter, one for when you are at home and one for when you are away, a "holiday" one you switch on twice a year. Each has its own status helper and its own complete set of settings. The new input **"Only run this automation while this switch is on"** (`instance_active`, empty by default — nothing changes if you leave it so) is what makes this safe: while its switch is off, that automation does **nothing at all** for the cover — no opening, no closing, no shading, no lockout — and it does not react to the cover being moved by anything else either. You provide the switches (an `input_boolean` each) and a small automation of your own that makes sure only one of them is ever on; CCA does the hand-over. Or skip the switching automation entirely with the companion input **"... and it counts as on while it shows this value"** (`instance_active_value`): point every automation at **one shared Dropdown helper** (`input_select` — *Summer / Winter / Holiday*) and give each its own option — a dropdown always shows exactly one value, so exactly one automation is in charge, guaranteed by construction. The same field turns one `input_boolean` into a switch for **two** complementary automations (`on` in one, `off` in the other). A **calendar** works as the switch too — the automation is in charge **while a calendar event is running**, so a "holiday" instance driven by your vacation calendar takes over at event start and hands back at event end, all by itself (any event counts — event titles play no role, unlike in the calendar *time control*; use a dedicated calendar). **Switching an instance on means "you are in charge now"**: it re-reads the window contacts, presence, the force switches, the weather and its own schedule from scratch, and brings the cover to where *its* settings say it belongs. Nothing is inherited from the instance that was in charge before — including a manual override that this instance still had stored from the last time it ran, which belonged to the previous shift and is discarded. Because a hand-over is not a restart, it moves the cover **regardless of the 🔄 catch-up setting** — an instance that takes charge and then leaves the cover where the previous one parked it has done nothing at all. **One rule for your switching automation: do not move the cover yourself when switching over** — just flip the switches and let the incoming automation position the cover, or it will see your movement as a manual override and leave the cover alone. Note that the *"only once per day"* options count per automation (each has its own status helper), while force functions and the window contacts are shared and are picked up across a hand-over without a gap. 💡 **Bonus for single-automation setups:** point the switch at an `input_boolean` that is always on, and flipping it off and on becomes a **"re-sync now" button** — CCA discards a stored manual override, re-reads everything and drives the cover to where it belongs, immediately and regardless of the catch-up setting

---

# CCA 2026.07.13 V7

- 🐛 **Fix:** With *"Using the ventilation position when the sun shading is ended"* enabled and a window **tilted** at the end of the sun shading, tilt covers whose sun-shading position **equals the ventilation position** (a common venetian setup: closed/shading/ventilate all share the same cover position and only the slat angle differs) were not moved to ventilation — the slats were tilted to the **"🔼 Open Tilt Position"** (e.g. 100 %) instead of the **"💨 Ventilate Tilt Position"** (e.g. 60 %). The position check of the ventilation handling only recognized a cover *below* the ventilation position; a cover resting exactly *at* it fell through to the tilt-only handling. The check now also accepts a tilt cover at the ventilation position whose slats are not yet open beyond the ventilation angle — exactly like the window-contact handling has always done ([#608](https://github.com/hvorragend/ha-blueprints/issues/608))

---

# CCA 2026.07.13 V6

- 🐛 **Fix:** A **disabled entity** (switched off in Home Assistant's entity settings, or deleted) was treated like a device that is temporarily unreachable — but it is not: it never comes back, so none of CCA's fallbacks or recovery paths can ever correct it. The consequences were silent and permanent. A disabled **cover** (or position sensor) blocked **every single run of the automation, for good, without a single line in the log** to say why. A disabled **entity of a force function** froze that force function in the status helper **forever** — CCA deliberately keeps the last known force while its entity is unreadable, and no trigger was left that could ever clear it, so the cover stayed in the force position permanently. CCA now tells the two cases apart: a disabled or deleted entity is reported as a **configuration error, by name, in the log** (for a cover or position sensor the run then stops — but audibly instead of silently); a disabled force entity releases the force function instead of freezing it; a disabled *condition-only* sensor (brightness, sun, weather, calendar, workday) is reported as a warning and otherwise ignored, as if it were not configured. Re-enable the entity, or remove it from the automation settings
- ✨ **Feature:** 🔄 **Recovery is now a three-way choice** instead of an on/off switch: *never* (default, unchanged), *only after an outage of a device or integration*, or *always (also after a restart or a save)*. The complaints that made the recovery opt-in were about covers moving **after a Home Assistant restart** — but a Zigbee stick that dropped out for ten minutes over your closing time is a different event, and leaving the cover open all night is not what anyone asked for. The middle setting catches up exactly those outages and never moves the cover because of a restart, a reload, or a save — and the order in which your integrations happen to load during a start-up does not matter: a device that was already unreachable when Home Assistant started stays part of that start-up, however long it then takes to answer. Existing configurations keep working: the old *off* becomes *never*, the old *on* becomes *always*
- 🐛 **Fix:** The recovery re-derived a missed opening or closing from the **schedule alone** and ignored your **additional opening/closing conditions** — so a scheduled movement you had deliberately suppressed with such a condition was "caught up" as if it had merely been missed (reported: opening blocked all morning by an additional condition, then a restart opened the cover anyway). The additional condition of the relevant direction is now evaluated before a missed opening/closing is applied; if it says no, the movement is not replayed and CCA keeps the status it had. The *global condition* was, and stays, respected
- 🐛 **Fix:** When a **device or integration dropped out while Home Assistant kept running** — a gateway offline, an integration reloaded, an actuator briefly unplugged — and came back, **nothing happened at all** unless the 🔄 Recovery switch was on. That was wrong even for people who never want a catch-up: while a required entity is unusable, CCA blocks every run, and that silently eats events which never fire again. So a sun shading whose waiting period expired during the outage stayed armed until midnight (no shading that day), an **automatic override reset stayed pending forever** (the cover stuck under manual control), and a force function switched during the outage stayed recorded wrongly — which makes **every later event** move the cover incorrectly. The return of a cover, a status helper, a position sensor or a window contact now always cleans this up, regardless of the recovery setting. With the catch-up off that run only corrects the status and stops — it never moves the cover
- 🐛 **Fix:** With **calendar-controlled opening/closing**, the 🔄 Recovery never caught up a missed opening or closing — the recalculation after a restart or a save ran **without loading the day's calendar events**, so it could not tell what the schedule demanded and silently kept the outdated status. Same root cause as the weather-forecast fix below, one step further down: the calendar events are now loaded for every recalculation run. (Time-field schedules were not affected)
- 🐛 **Fix:** With the **ventilation automation disabled** but window contacts still configured — the classic case is a defective contact that permanently reports "open" or "tilted", which is exactly *why* one disables ventilation — the recalculation after a restart **or after every save of the automation** drove the cover to the ventilation position (or fully open, even overriding a manual override). Disabled ventilation means the window contacts do not exist as far as CCA is concerned (see `2026.07.05`), and that now holds **everywhere**: the whole status calculation ignores the contacts, not just the individual handlers
- 🐛 **Fix:** When the **cover needed longer than about a minute** to come back after a restart (a Zigbee hub rebooting, for example), the one-shot resume check fired while CCA was still blocked and was **used up** — and the **first regular event of the day** (say, the 07:00 opening) was then consumed by the status recalculation instead. With the 🔄 Recovery switch off (the default) that opening simply did not happen until the "at the latest" time. The resume check now waits until the cover and the other required sources are actually usable, so it can never burn itself on a blocked run
- 🐛 **Fix:** A **restart during the night** could **open the cover in the dark**: if the evening closing had been swallowed by an outage (typically while a sun shading was still active), the recalculation between midnight and the opening time treated the stored "open" as the valid ground state and drove the cover open — at 2 am, notification included. The night now counts as the previous evening continued: with a closing automation configured, "closed" is the scheduled state until the opening time. (Only with the 🔄 Recovery switch on; no closing automation configured → nothing is invented)
- 🔧 **Improvement:** The **force pause** now silences everything that belongs to a movement, not just the movement itself: while paused, the *before/after actions* no longer fire (no more "cover is opening" notifications for a cover that stays put) and a **manual override is no longer cleared**. Both follow the actual drive decision now — when the pause ends, the cover returns to its target as before
- 🐛 **Fix:** An **entity of a force function** that dropped out and came back **switched off** kept the force function recorded **forever** when the 🔄 Recovery switch was off (the default). Its own trigger only reacts to a real *on → off* change, so a return from "unavailable" straight to "off" never reached it — and CCA deliberately keeps reading the last known force function while its entity is unreadable, so nothing corrected it either. The cover then stayed in the force position for good: the force status is part of the status helper, so an outdated one does not just miss an event, it makes **every later event** move the cover wrongly. Re-reading the force functions when their entity reports again is now **independent of the recovery switch** — like the rest of the status clean-up, it only ever *prevents* a wrong movement and never causes one (with the switch off, this run corrects the status and stops, it does not drive the cover). The **force pause** deliberately keeps the switch: nothing about it is stored, so its return leaves nothing to correct — the only thing to do there would be to drive the cover back into the suspended force position, and that is a catch-up
- 🐛 **Fix:** A **manual cover movement** right after a restart (or right after saving the automation) was **swallowed**. CCA recalculates its state on the first trigger that follows — and it did that for the manual-detection trigger too, so the manual change was never recorded. With the 🔄 Recovery switch **on**, CCA then read "no manual override" and drove the cover straight back, fighting the movement you had just made by hand. The manual detection now always runs and records the override first; the recovery follows about a minute later and respects it
- 🐛 **Fix:** With the 🔄 Recovery switch **on** and a **weather condition** configured for sun shading (forecast temperature or weather situation), a shading that was due could be silently skipped after a restart or a save — but only when CCA's recalculation happened to be triggered by an event that has nothing to do with shading (a closing time, a presence change, a window contact). In that case the forecast was not loaded, the weather condition counted as "not met", and the shading was not started for the rest of that day. The forecast is now loaded for every recalculation run

---

# CCA 2026.07.13 V5

- 🐛 **Fix:** If you open the cover by **sun elevation or brightness with the time control switched off**, a **tilted window pulled the freshly opened cover back down** to the ventilation position — and it stayed there until the next day (or until a force function moved it). The rule that an open cover wins over the ventilation position ("a fully open cover ventilates best") only recognised an opening driven by the **time schedule or the calendar** as a real one; an opening driven by the sun or by brightness was mistaken for the untouched starting value and was overruled by the ventilation position. All four opening sources now count equally. Setups **without any opening automation** (sun shading only) are unaffected: there the ventilation position still applies to a tilted window, exactly as since `2026.05.31`

---

# CCA 2026.07.13 V4

- 🐛 **Fix:** An unavailable **entity of a force function** read as "switched off" — so an outage of that entity (it may be a switch or a binary sensor, not just a helper toggle) **silently cancelled the running force function** and let the cover drive to its scheduled position. This was permanent: the force triggers only react to a real *off → on* / *on → off* change, so an entity returning from "unavailable" straight to "on" never re-activated the force. CCA now keeps the **last known force function** while its entity has no usable status, and re-reads it as soon as the entity reports again — a force function that was genuinely switched off during the outage is still recognised and ended correctly
- 🐛 **Fix:** **Switching the automation off and on again** left it running on an outdated status. This is not the same as a restart: nothing reports it, so none of the recovery mechanisms introduced in 2026.07.12 took hold — the automation simply carried on with a status that could be days old. Particularly nasty across a change of date: the nightly clean-up at 23:55 obviously did not run either, so a sun shading from days ago still counted as active and the next event drove the cover into the shading position — at night, too. And an automatic override reset that came due while the automation was off could never happen again, so the cover stayed under manual control forever. CCA now notices that it was switched on again, cleans up everything the missed nightly reset would have cleaned up, and recalculates the target state from scratch — before anything else is allowed to move the cover. **The clean-up itself does not depend on the recovery switch (see `2026.07.13`):** it only removes an outdated status (an old sun shading, a waiting period that can no longer run, an override reset that came due in the meantime) and therefore never moves the cover — it only stops CCA from moving it *wrongly* later on. Whether the cover is then actually driven to the recalculated position is what the switch decides
- 🐛 **Fix:** The recovery after a restart or an outage did not write back the **resident status** it had just re-read. The stale value stayed in the status helper — and that is exactly the value CCA falls back to when the resident sensor drops out the *next* time, so a single outage could poison the privacy closing much later
- 🐛 **Fix:** When the recovery cleared a **manual override** whose reset had come due during the outage, it did not run the **action you configured for an override reset** (notification, scene, …). The override was lifted silently; the action now runs, exactly as it does on a normal reset
- 🐛 **Fix:** With **"Open only once a day"** enabled, an opening could be wrongly suppressed if the cover was last opened **exactly one month ago** — the check compared only the day of the month, not the full date. This mainly affected covers that had been idle for a long time (e.g. in a guest room, or after the automation had been switched off)
- 🐛 **Fix:** When the recovery **caught up a movement that was missed** during a restart or an outage (e.g. the 22:00 closing), it moved the cover but did **not** run the actions you configured for that movement (*"Action before/after closing"*, opening, ventilation, sun shading). A caught-up closing is a closing — those actions now run, exactly as the scheduled handler would have run them. They only run when the cover actually changes position: a recovery that finds everything already in place (the normal case after a restart) stays silent, and a pure slat-angle correction does not trigger them either
- 🐛 **Fix:** The recovery after a restart or an outage ignored the **alternate sun shading position**: it always drove to the *normal* shading position, even while the switch for the alternate position was on. A restart during an active alternate shading therefore dragged the cover back to the normal position — and it did not correct itself, because the recovery compared the cover against its own (wrong) target and considered it "already in position". The recovery now derives its target from the same projection as every other movement

---

# CCA 2026.07.13 V3

- ✨ **Feature:** New third **"🔄 Tilt Wait Mode"** option **"🔃 Tilt First, Then Position (Somfy J4 IO)"** ([#355](https://github.com/hvorragend/ha-blueprints/issues/355)). Some motors — notably the Somfy J4 IO family — automatically restore the previous slat position after every positioning run, and abort a positioning when another command arrives during the movement. With the standard order (position first, then tilt) this caused a triple movement (position → motor restores old tilt → CCA tilts to target) and forced a choice between dead time (*Fixed Delay*) and aborted positionings (*Wait Until Idle*). The new mode sends the **tilt command first and the position command afterwards**: the motor's own restore then re-applies exactly the target tilt after the movement, so no tilt command has to be sent — or waited for — after positioning. The **"🕛 Default Tilt Delay"** is applied between the tilt and the following position command in this mode. Only select this mode for motors that restore the slat position after positioning — on ordinary tilt covers the position movement would destroy the previously set tilt

---

# CCA 2026.07.13 V2

- ✨ **Feature:** New optional **"🧩 Custom Condition Sensor"** for sun shading ([#531](https://github.com/hvorragend/ha-blueprints/issues/531)). You can now bind your own `binary_sensor` or `input_boolean` and select it as an additional condition in all four shading condition lists (START/END, AND/OR). While the entity is **on** the custom START condition is met; while it is **off** the custom END condition is met. This enables hybrid setups the built-in conditions could not express — for example *"shade when the forecast matches **or** my own sensor says so"*: put both the forecast weather condition and the custom sensor into the START (OR) list, and an unreliable forecast can be overridden by a manually switched helper without giving up the sun-position conditions. A state change of the entity also acts as a shading trigger, so a template sensor you update during the day (e.g. from an hourly forecast) re-evaluates the shading conditions the moment it flips. Leave the field empty to keep the previous behavior — the condition is skipped automatically, even where it is selected in the lists

---

# CCA 2026.07.13

- ⚠️ **Change:** The **recovery after a restart or an outage** (introduced in `2026.07.12`) is now **opt-in and disabled by default**. Several users do not want their covers to move right after a Home Assistant restart — the recovery recalculates the target state from scratch and drives the cover if it is not where the cascade says it should be (e.g. catching up on a missed opening or applying a stored sun-shading intent). A new switch **"🔄 Recovery after a restart or an outage"** in the *Automation Options* section controls the feature: when **off** (default), the cover is never moved because of a restart, at the cost that events which fell into the restart/outage stay lost until the next regular trigger fires (the pre-`2026.07.12` behavior). When **on**, everything works exactly as introduced in `2026.07.12` — with one documented limitation (user report): the recovery derives a missed opening/closing from the **schedule alone**; the **additional opening/closing conditions are not re-evaluated**, so a scheduled movement that such a condition deliberately suppressed is caught up anyway. The **global condition** *is* respected (it drops the whole recovery run) — mirror the suppression logic there, or keep the recovery disabled. Two things stay **independent of this switch and always active**, because they only ever *prevent* a wrong movement and never cause one: the availability protection from `2026.07.12` (pausing while the cover, status helper, or position sensor has no usable state, plus the last-known fallbacks for window contacts and the resident sensor), and the **clean-up of the status helper** when CCA comes back after a restart or after being switched off and on again (see the entry on *"Switching the automation off and on again"* below) — an outdated status is not a missed event, it is a status that would make CCA move the cover *wrongly*, so it is cleaned up in any case. That never moves the cover by itself

---

# CCA 2026.07.12 V3

- 🔧 **Improvement:** Internal architecture rework ("transition architecture"), no functional change intended. Every branch of the action tree now computes exactly two things — the state transition (`update_values`) and an optional actuation plan (`drive_plan`: drive yes/no, target position/tilt, action set, pre-drive delay) — and hands both to a single shared epilogue (`apply_transition`) that performs *delay → drive → helper write* in a fixed order. The helper write is unconditional in that epilogue, so **every execution path is terminal by construction**: the "pending armed forever because a path ended without a helper write" bug class (e.g. [#395](https://github.com/hvorragend/ha-blueprints/issues/395) and the two 2026.07.01 fixes) can no longer be reintroduced by a single forgotten step. A new test suite enforces this structurally
- 🔧 **Improvement:** The live window-sensor state is evaluated **once per run** into shared flags (`window_opened_now`, `window_tilted_now`, plus per-context lockout flags) instead of ~30 inline copies of the raw sensor idiom across branch conditions. The same applies to the manual-override gates, the once-per-day shading guard, the "was ventilating before" check of the contact handler and the standard drive delay. Fewer places to keep consistent, identical semantics
- 🔧 **Improvement:** New explicit reconciler projection `state_targets`: a single map from each internal state (`lock`/`opn`/`vnt`/`shd`/`cls`) to its drive parameters. The force-enable, force-last-wins and force-pause-resume handlers now derive their targets from this map; the force-pause-resume handler collapses from five duplicate branches into one projection step (the resumed state is logged via the logbook and visible in the trace variables)
- 🔧 **Improvement:** Two ordering normalizations while unifying the drive epilogue: the "Normal opening" branch no longer waits its random drive delay when no drive is permitted anyway (the helper is simply updated immediately), and the shading-end open drive now runs its after-action directly after the movement (before the helper write), matching every other branch
- 🔧 **Improvement:** Second consolidation round ("target chains"): handlers that consisted of several nearly identical "drive back to the background state" branches are collapsed into one leaf each that computes the target via a first-match chain and derives its drive parameters from the shared `state_targets`/`state_gates` maps — the contact handler's three "window closed" return branches, the resident leaving/arriving handlers (5+3 branches → 2+2) and the force-disable recovery (5 branches → 2). Ventilation targets keep a dedicated leaf because they are gated by the user-supplied ventilation condition. Equivalence with the former branch order was verified by exhaustive truth-table simulation; the chosen target is visible in the automation trace and the logbook line. The per-target stop messages of the merged branches become one generic message per handler ("Return to background state/target executed")

---

# CCA 2026.07.12 V2

- 🐛 **Fix:** A shading-start execution could end **without any helper write** when none of the drive branches matched — e.g. a non-tilt cover resting exactly at the shading position, or a cover held at the ventilation floor (window tilted). The pending stayed armed forever (the execution trigger never re-fires for a past due time) and new shading attempts were blocked until the midnight reset. The drive choose now has a default that records the shading state and cleanly ends the pending sequence
- 🐛 **Fix:** With *"Prevent opening after shading end"* enabled on a cover **without tilt support**, the shading-end execution hit its stop without writing the helper — shading state and end-pending stayed armed forever and the cover was stuck at the shading position (same failure shape as [#395](https://github.com/hvorragend/ha-blueprints/issues/395)). The prevented path now keeps the cover where it is but properly clears the shading/pending state
- 🐛 **Fix:** The time-window trigger `t_shading_start_pending_7` bypasses the global "already shaded" gate (it is not covered by the `[1-6]` regex, deliberately — it must stay able to cancel a stale end-pending). It could therefore re-arm a shading-start pending although shading was already active or stored for the future, resetting the remembered state and restamping the shading timestamp. The pending-arm branch now additionally requires that shading is not already active/stored
- 🐛 **Fix:** In the *"Ventilation after shading ends"* branch the position check `if_lower_enabled and above_ventilate or position == ventilate_position` was evaluated as `(A and B) or C` — the equality alternative was not gated by the *"activate ventilation even if lower"* option, unlike the identical (correctly bracketed) check in the contact handler. Both now use the same bracketing
- 🐛 **Fix:** A manual move that matched two position windows with mismatched feature flags (e.g. cover physically in both the ventilate and open tolerance band, but automatic opening disabled) was silently dropped by the manual detection — no branch matched and the helper was never updated. The unknown-position case is now a real catch-all, so every detected manual change is recorded
- 🔧 **Improvement:** Internal simplification without behavior change: the shading-start retry logic (waiting-for-window / continue / abort) exists only once instead of twice; the six manual-detection branches share one tail (helper write, manual action, stop); the force-pause handler is a plain switch over the internal target state (the four force-specific branches were exact duplicates of the generic ones); force-enable and "last wins" force switching are one parametrized sequence each; the before/after-action + move + tilt drive idiom is a shared building block (`drive_with_actions`) instead of ~37 inline copies; dead variables and dead validation code removed. The blueprint shrinks by about 950 lines
- 🔧 **Improvement:** Typo fix in the seven helper-JSON plausibility regexes (`\{s*` → `\{\s*`); they only worked by accident
- ✨ **Feature (docs):** New **[CCA Handbook](https://hvorragend.github.io/ha-blueprints/handbook/)** on GitHub Pages: the complete configuration reference for every blueprint input, organized in 17 chapters. The collapsible `<details>` help blocks and the most verbose descriptions moved there; the blueprint UI now shows a concise summary plus a deep link to the matching handbook section

---

# CCA 2026.07.12

- ✨ **Feature:** New optional **Alternate Sun Shading Position** (in the *Cover Position* settings, next to the normal shading position). You can now define a second shading position together with a switch entity (a `binary_sensor` or `input_boolean`): while that entity is **on**, the cover shades to the alternate position; while it is **off** (or the fields are left empty), it shades to the normal position exactly as before. If the switch changes while the cover is **already shading**, the cover moves to the matching position right away (on tilt covers the shading tilt angle is re-applied after the move). This does **not** count as an additional sun shading, so *"Only shade once per day"* keeps working normally. Leave both fields empty to keep the previous behavior ([#580](https://github.com/hvorragend/ha-blueprints/issues/580))
- ✨ **Feature:** **Full recovery after a restart or an outage.** Because CCA is (deliberately) inactive while a required source is missing, every event of that period was lost — and nothing brought it back: a scheduled closing at 22:00 during a restart simply did not happen, and sun-shading triggers only fire on a *change* of their condition, so a change that occurred during the outage was gone for good. CCA now reports back when Home Assistant has started and whenever one of its sources becomes usable again. As long as something is still missing the run stays blocked, so **the last source to return performs the recalculation** — and it recalculates everything from scratch: the base state is re-derived from the time schedule or calendar (a missed opening/closing is caught up), the window contacts and the resident sensor are re-read (lockout, ventilation, privacy closing), an active force function is taken from the actual switches (so a force turned on or off during the outage is no longer stuck in the helper), and the **sun-shading conditions are re-evaluated** — if shading is due now, it starts; if it is over, it ends. A **manual override survives** the outage and is not overwritten; only the lockout protection (window fully open) takes precedence, as everywhere else. A shading waiting time whose expiry fell into the outage is cleared, because its trigger can no longer fire, and is re-armed from the current conditions
- 🐛 **Fix:** While a source CCA *depends on* had no usable state — typically during a Home Assistant restart or an outage of an integration — the automation kept running and worked with **wrong assumptions**. An unavailable **cover** reports no position, so CCA fell back to an internal placeholder that (depending on the position tolerance) reads as "already open": movements were skipped, drive commands to the unreachable cover aborted the run halfway so the status helper was never written, and a still valid state — for example an active sun shading from before the restart — could be **overwritten with a wrong one**. The same applies to an unavailable **status helper**, whose content falls back to a fresh default and would wipe the persisted state on the next write. The automation now waits until the cover, the status helper (and, if used, the position sensor) are usable again, so no wrong status can be recorded. This includes **cover groups** (a group is unavailable exactly when all of its members are)
- 🐛 **Fix:** An unavailable **window contact** read as "closed" and an unavailable **resident sensor** read as "away" — so a sensor dropout could silently disable the **lockout protection** or the privacy closing. Both now fall back to the **last known value from the status helper** instead of to a wrong assumption. This matters especially after a restart of the *hub*: battery-powered window and presence sensors only report when something actually changes, so they can be without a status for hours. CCA deliberately does **not** wait for them — it keeps working with the last known state, which is correct as long as nobody physically moves the window in the meantime. Only one situation makes CCA wait: a window contact without a status while the window was last known to be **open or tilted**. Acting would mean treating that window as closed and lowering the cover onto it; instead the cover holds its lockout/ventilation position until the contact reports again (which happens as soon as the window is moved). Moving the cover **by hand** is still recognized during that wait — the manual override is recorded as usual and survives the recovery. Sensors that only *influence* a decision — brightness, sun, weather, calendar, workday — never block the automation: a flaky outdoor sensor must not stop your cover from closing in the evening
- 🐛 **Fix:** A **manual override could stay active forever**. The automatic reset ("reset after a period of time" and "reset when the cover is moved to a defined position") is driven by a trigger that only fires at the *moment* its condition becomes true. If that moment fell into a Home Assistant restart — or into a period in which the automation was inactive — the trigger never fired again, and the cover stayed under manual control indefinitely: no schedule, no sun shading, no automatic anything, until it was moved by hand once more. The reset rules are now re-evaluated after a restart or an outage: an override whose reset was already due is cleared and the cover returns to automatic control
- 🐛 **Fix:** **Time Control could not be disabled through the UI** for installations created after the options consolidation (~2026.05). Unchecking the *"⏲️ Time Control"* checkbox in *Automation Options* had no effect: internally, disabling additionally required the legacy selector value `time_control: time_control_disabled` — but that value was no longer offered in the *"Time Control Type"* dropdown, so the disable path was unreachable. Brightness-/sun-only setups were therefore still constrained by the default Early/Late time windows (e.g. a sun-elevation closing kept being gated by the 16:00–22:00 window). The *"⏲️ Time Control"* checkbox is now the **single authoritative switch**: unchecking it disables all Early/Late time windows immediately. The *"Time Control Type"* dropdown only selects *how* time control is scheduled (time input fields or calendar) and is ignored while time control is off. **Warning:** without time windows there is no guaranteed *Late* opening/closing safety net — the cover only moves when a sensor condition is actually met ([#544](https://github.com/hvorragend/ha-blueprints/issues/544))
- 🐛 **Fix:** With *"☀️ Stay shaded: Don't open cover when sun shading ends"* enabled, the slats were tilted to a **hardcoded 50 %** when the sun shading ended, ignoring the configured *"🔼 Open Tilt Position"*. The two only differ when the open tilt was changed from its default of 50 %, which is why this went unnoticed for so long. The tilt-only handling now uses the configured open tilt position ([#583](https://github.com/hvorragend/ha-blueprints/issues/583))
- 🐛 **Fix:** When *"☀️ Stay shaded: Don't open cover when sun shading ends"* and *"💨 Using the ventilation position when the sun shading is ended"* were **both** enabled and a window was **tilted** at the end of the sun shading, the cover kept the shading position and only opened the slats — instead of moving to the **ventilation position** with the ventilation tilt. The tilt-only handling ran before the ventilation handling and swallowed it. Lockout protection and ventilation are now evaluated **first**, matching the priority cascade (lockout > ventilation > shading); the tilt-only handling still applies when the window is closed or the ventilation option is not enabled ([#583](https://github.com/hvorragend/ha-blueprints/issues/583))
- ⚠️ **Breaking change — backward compatibility removed:** The internal fallback that kept time control active for configurations without `time_control_enabled` in `auto_options` has been **removed without replacement**. **Installations created before the options consolidation (~2026.05) do not store this value — after this update their time control is DISABLED** (time-field and calendar opening/closing stops firing) **until the automation is re-saved once with the *"⏲️ Time Control"* checkbox enabled.** The symptom depends on the configuration: with **pure time/calendar control** the covers simply **stop moving** — but in a **hybrid setup with Brightness or Sun Elevation triggers**, those triggers keep firing and only lose their time fence, so the covers **open too early in the morning** (at the brightness/sun threshold, e.g. around sunrise instead of the configured earliest time) and can **close too late in the evening** ([#595](https://github.com/hvorragend/ha-blueprints/issues/595)). Installations configured after ~2026.05 are unaffected — the checkbox is part of the defaults and was stored automatically. The obsolete legacy selector value `time_control: time_control_disabled` is no longer evaluated; configurations that had chosen it stay disabled via the missing checkbox, exactly as originally configured ([#544](https://github.com/hvorragend/ha-blueprints/issues/544))

---

# CCA 2026.07.05 V2

- 🐛 **Fix:** When the mandatory **Cover Status Helper** was not configured, every run of the automation died immediately with the cryptic log error `Error rendering variables: TypeError: cannot use 'list' as a dict key (unhashable type: 'list')` — the friendly configuration error CCA is supposed to log ("Cover Status Helper is required but not configured") was never reached, so nothing worked and there was no hint why. The internal helper parsing read the helper entity's state without first checking whether a helper is configured at all. All helper reads are now guarded: without a configured helper the automation starts normally, reaches the built-in configuration check, writes a clear error to the system log and the logbook, and stops. The shading execution/tilt triggers and the manual-override reset triggers are also disabled while no helper is configured, so they cannot produce template errors either. **Reminder:** the Cover Status Helper (an `input_text` helper with a maximum length of 254) is mandatory — one per CCA automation
- 🐛 **Fix:** Since `2026.06.28 V3`, the **lockout protection** could be bypassed at the scheduled opening time: when the shading conditions were already met at opening time while the lockout window was **fully open** (or **tilted** with *"Lockout protection when starting the sun shading"* enabled), the opening handler handed the movement over to the sun-shading execution (arming/deferring a shading pending) instead of opening the cover. But the shading execution's lockout branch only records the shading intent and stops **without any movement** — so the deferred opening never happened and the cover could stay down (e.g. still closed after a force function or a restart) although the open window demands the open position. The opening handler now performs the normal opening in this situation; sun shading remains protected by the existing lockout skip and starts as usual once a shading trigger re-fires. The same gap existed for a shading pending armed **before** the opening time while the window was already open (forum report)

---

# CCA 2026.07.05

- ✨ **Feature:** Tilt-capable covers now have a **Tilt Position Tolerance** (next to the existing position tolerance, in the *Tilt Position Feature* settings). The cover status is now told apart by **position *and* tilt angle**, so several states that share the same position can be distinguished by their tilt — e.g. *closed*, *shading* and *ventilate* all at position 0 but with different tilt angles. The tolerance is an absolute dead-band that also absorbs small tilt-motor inaccuracies, mirroring the position tolerance. The same dead-band is applied to manual tilt-change detection, so a tiny tilt jitter reported by the cover is no longer mistaken for a manual intervention ([#558](https://github.com/hvorragend/ha-blueprints/issues/558))
- 🐛 **Fix:** When **one calendar** contains **two events with different titles but the same start time** (e.g. "Open Cover" for the living areas and "Open Schlafraume" for the bedrooms, both starting Saturday 08:30), only one of the two automations ran — the other was stopped by a global condition and its cover never opened. The condition checked the calendar entity's `message` attribute against the configured open/close titles, but that attribute only ever exposes a **single** event: with two simultaneous events, the hidden one never matched. The title check has been moved from the global conditions into the automation itself, where today's events are loaded via `calendar.get_events` and matched **per event** — reliable regardless of how many events start or end at the same moment. A calendar trigger is now ignored only when *none* of the automation's own open/close events starts or ends at that state change, so the noise suppression for unrelated calendar events is preserved ([#568](https://github.com/hvorragend/ha-blueprints/issues/568))
- 🐛 **Fix:** Calendar event titles were matched as a **substring**, so a cover configured with the open title *"Open Cover"* also reacted to events like *"Open Cover Bedroom"* on the same calendar. Because the parsing kept the **last** matching event of the day, such a cover could ignore its own *"Open Cover"* event (e.g. 06:00) and open at the time of the more specific event (e.g. 06:15) instead. Event titles are now matched **exactly** (ignoring upper/lower case and surrounding spaces) in the open/close event parsing — and therefore also in the calendar trigger relevance check, which builds on it. Several covers can therefore share one calendar with prefix-related titles — *"Open Cover"* and *"Open Cover Bedroom"* are now distinct. **Note:** If you relied on the old substring behavior (e.g. events named *"Open Cover (vacation)"* matching the title *"Open Cover"*), rename the events or the configured title so they match exactly ([#536](https://github.com/hvorragend/ha-blueprints/issues/536))
- 🐛 **Fix:** If the cover happened to sit at the **shading position** at opening time while shading was **not** active in the helper (`shd: 0`) — for example because it was moved there manually — the cover never opened for the rest of the day. The opening handler skipped the normal opening (assuming an active shading would be ended later by the Shading End logic) and only updated the base state. But that handoff can never happen with `shd: 0`: a global trigger gate blocks all shading-end triggers unless shading is actually active in the helper. The normal opening now only defers to Shading End while shading is genuinely active; with `shd: 0` the cover simply opens normally ([#565](https://github.com/hvorragend/ha-blueprints/issues/565))
- 🐛 **Fix:** When a force function (e.g. force close) was turned **off** while the **ventilation automation was disabled**, the force-disable recovery could still drive the cover to the **ventilation position** if the tilt contact sensor reported "tilted" — for example a defective sensor stuck on *tilted*. The recovery branches read the window contact sensors directly and bypassed the ventilation-enabled check that gates all normal contact handling. With ventilation automation disabled, the window contacts are now ignored consistently during force recovery as well: the *return to VENTILATION* branch no longer fires, and the *return to CLOSE / SHADING / OPEN* branches are no longer blocked by a (possibly stuck) open/tilted contact — the cover correctly returns to its shading, open, or close target. Setups with ventilation automation enabled are unaffected ([#566](https://github.com/hvorragend/ha-blueprints/issues/566))
- 🐛 **Fix:** When the sun shading started while a window was only **tilted** (not fully open) and the shading position is **below** the ventilation position (e.g. shading 30 %, ventilation 50 %), the cover dropped all the way to the **shading position** — below the ventilation floor. A tilted window makes the ventilation position a *floor* (VENT outranks SHADING in the priority cascade), so the cover should stop at the **ventilation position** while the window is tilted and only move to the shading position once the window is closed. This only happened in the order *tilt the window first, then shading starts*; the reverse order (shading already active, then tilt the window) already held the ventilation position correctly via the contact handler. The shading-start execution now holds the ventilation floor when the window is tilted. If you would rather the cover stay **fully open** while the window is tilted and shade only after you close it, enable *"Lockout protection for window tilted → when starting the sun shading"*

---

# CCA 2026.07.03

- 🐛 **Fix:** The `2026.06.28` fix for [#554](https://github.com/hvorragend/ha-blueprints/issues/554) (cancel a pending shading **end** when the shading conditions are met again during the end waiting time) never actually ran: a global trigger gate suppresses all `t_shading_start_pending_*` triggers while shading is active (`shd == 1`) — and during an end-pending, shading is *always* still active. The automation therefore stopped before ever reaching the new cancel logic, and the end timer kept running silently to its original expiry, exactly as before. The global gate now lets shading-start triggers through when an end-pending is armed (`pnd == 'end'`), so the cancel logic finally executes: the pending end is canceled (only after re-checking that the end conditions are genuinely no longer met), the cover stays shaded, and shading only ends after the end conditions hold **for the entire waiting time** without interruption — as documented. The cancel is now also reachable while the window is open/tilted. The gate's noise-suppression purpose is preserved: outside an end-pending, start triggers are still ignored while shading is active ([#554](https://github.com/hvorragend/ha-blueprints/issues/554))
---

# CCA 2026.06.28 V3

- 🐛 **Fix:** When a cover was **manually opened and closed before the scheduled opening time**, sun protection (shading) did not activate afterwards — the cover did not appear in any "sun protection" dashboard section. The shading-start template triggers (`t_shading_start_pending_*`) only fire on a FALSE→TRUE state transition. If the shading conditions were already TRUE when the user manually closed the cover (which clears the pending), and the conditions remained TRUE when the scheduled opening fired, no new FALSE→TRUE transition occurred and the pending was never re-armed. The opening handler now includes a dedicated branch that runs before the normal opening: when shading conditions are warranted at opening time and no pending is already active, the branch arms the shading-start pending and defers — the cover stays at its current position and is driven to the shading position by the execution trigger (instead of unnecessarily opening first and then immediately shading). This mirrors the path a normal `t_shading_start_pending_*` trigger would take ([#555](https://github.com/hvorragend/ha-blueprints/issues/555))
- 🔧 **Improvement:** The window-contact and resident triggers now ignore pure *attribute* changes and only react to a real `on`/`off` state transition. A "noisy" source bound to one of these inputs — for example a Threshold helper built on `sun.elevation`, whose `sensor_value` attribute updates on every elevation change — could previously re-trigger the automation every few minutes even though its actual state changed only twice a day. There was no functional harm (the automation runs in `queued` mode and every branch is idempotent), but it cluttered the trace/logbook history. This is now filtered **at the trigger itself** (`not_to`), so the automation no longer even starts a run for an attribute-only change — no leftover trace entries ([#550](https://github.com/hvorragend/ha-blueprints/issues/550))
---

# CCA 2026.06.28 V2

- 🐛 **Fix (docs):** The *"Shading END – Optional Conditions (OR)"* help text contained a misleading example claiming shading would *"End only when sun is wrong AND (dark OR cold)"*. That suggested the AND group and the OR group are combined with **AND**. In reality — and as the *"Combined logic"* note in the same help text and the automation trace both show — the two END groups are combined with **OR**: shading ends when *either* all AND-group conditions become invalid *or* any single OR-group condition becomes invalid. The example has been corrected, and the help text now states explicitly that END combines the groups with OR (unlike START, which combines them with AND) and explains that requiring several end conditions together means putting them all in the AND group. No logic change ([#560](https://github.com/hvorragend/ha-blueprints/issues/560))

- 🐛 **Fix:** In a **shading-only** setup *without* an open/close schedule (no automatic up/down, time control disabled), a tilted or opened window never moved a closed cover to the ventilation position. The internal base state initializes to *"open"* and is only ever switched to *"closed"* by the scheduled close handler — so without a schedule it stayed *"open"* forever, and since *BASE=OPEN* outranks the ventilation *"floor"* in the priority cascade, ventilation could never apply. The cascade now treats *"open"* as a real open intent only when an opening schedule actually exists; without one, a tilted window correctly drives the cover to the ventilation position. This also makes the documented *"remove the time schedule"* workaround from the `2026.05.24` notes work as described. Setups *with* a schedule are unaffected ([#553](https://github.com/hvorragend/ha-blueprints/issues/553))

---

# CCA 2026.06.28

- 🐛 **Fix:** When shading-end was **pending** (waiting for the configured end waiting time to elapse) and the shading conditions were met **again** before the timer fired — because weather changed from cloudy back to bright — the pending end was not canceled. CCA ignored all `t_shading_start_pending*` events while `pnd == 'end'`, so the end timer continued running silently. If conditions happened to still be met at the execution moment, shading ended regardless of what had happened during the waiting period. This violated the documented behavior *"Shading ends if the conditions are not fulfilled **for the entire waiting time**"*. A re-triggered `t_shading_start_pending*` event now cancels the active end-pending — but **only after re-checking that the end conditions are genuinely no longer met** (so an unrelated start trigger, e.g. forecast temperature, can no longer cancel a still-valid end-pending and leave the cover stuck shaded). The cancel also works when *"shade only once per day"* is enabled and shading already ran today. On cancel the cover stays in the shading position (`pnd` → `non`, timestamps cleared) and waits for the next uninterrupted end-conditions period ([#554](https://github.com/hvorragend/ha-blueprints/issues/554))

---

# CCA 2026.06.24

- 🐛 **Fix:** Forecast-based shading via the **daily/hourly weather forecast service** did not work when a weather entity was configured **without** a separate direct temperature sensor — i.e. the primary and recommended setup. The internal check that decides whether to call `weather.get_forecasts` treated an unset temperature sensor (which resolves to an empty list) as "still configured", so the forecast service was never called. As a result `forecast_temp_raw` and `forecast_weather_condition_raw` stayed `null`, and any forecast condition used as a **required (AND)** condition blocked shading entirely (removing it from AND made shading work again). The check now correctly recognizes an unconfigured temperature sensor, so the weather forecast service is called as intended. Calling `weather.get_forecasts` manually in Developer Tools always returned valid data; only the automation's internal gate was wrong
- 🔧 **Improvement:** When the weather forecast service is called but returns an empty forecast (weather entity available, but no forecast data — most often a temporary provider-side hiccup such as Met.no rate-limiting), the blueprint now writes a clear warning to the Home Assistant log (logger `blueprints.hvorragend.cca`) instead of silently treating the forecast conditions as "not met". Verify such cases via Developer Tools → Actions → `weather.get_forecasts`

---

# CCA 2026.06.23

- 🐛 **Fix:** With *"Reset in position"* enabled, manually moving the cover to the reset position (e.g. fully open at 100%) was silently ignored when **no** manual override was active — the helper never recorded the manual change. The manual-detection branch suppressed *every* manual move to the reset position, but the matching reset only ever fires while a manual override is already active. So a manual move to the reset position while in automatic mode was lost: neither recorded as a manual change nor cleared by a reset. As a consequence, a later event (e.g. closing a tilted window) drove the cover to the scheduled position instead of respecting the position you had just set by hand. The suppression now only applies while a manual override is actually active — matching the reset's own precondition. The intended *"reopen to the reset position to resume automatic control"* behavior is unchanged ([#546](https://github.com/hvorragend/ha-blueprints/issues/546))
- 🔧 **Improvement:** Clarified the description of the *"End Sun Shading – Immediately When Out Of Range"* option. The previous wording suggested that enabling it would end shading as soon as the sun leaves the azimuth *or* elevation range. In reality the option only controls the *timing* (it shortens the end waiting time to a few seconds) — it does **not** change *which* conditions end the shading. If "Sun Azimuth" / "Sun Elevation" are configured in the **AND** group of the END conditions, shading ends only once *all* of those conditions are out of range at the same time, so a single axis leaving its range is not enough (this also means a wide elevation range such as 0–90° practically never satisfies the elevation part). To get an "end as soon as either axis is out of range" behavior, put azimuth/elevation in the **OR** group. No behavior change — documentation only ([#545](https://github.com/hvorragend/ha-blueprints/issues/545))

---

# CCA 2026.06.20

- 🐛 **Fix:** When a cover was already in the ventilation position because the window was tilted, a following closing trigger (e.g. the sun-based closing trigger that fires repeatedly throughout the evening) re-drove the cover to the ventilation position again instead of leaving it alone. The closing handler's *"window tilted → ventilation"* branch always drove the cover, while the analogous *"already in close position"* branch only updates the base state. The branch now only drives when the cover is not already in the ventilation position — matching the contact handler, which already behaved this way. Note: if your cover reports a resting position that differs from the configured ventilation position by more than the *position tolerance* (common with tilt/venetian covers, where the tilt movement changes the reported position), increase the *position tolerance* so the cover is recognized as "in ventilation position" ([#538](https://github.com/hvorragend/ha-blueprints/issues/538))
- 🐛 **Fix:** With *"Allow sun protection when resident is still present"* disabled, the slats could still tilt into the shading angle while a resident was present. When the shading conditions were met during resident presence, the shading **intent** was correctly stored without driving the cover (`shade` on, status `resident`). But the separate *shading tilt* adjustment (which re-angles the slats as the sun rises) was missing the resident check, so a tilt-position trigger would still move the slats into the shading position — making the cover appear to enter shading mode despite the resident being present. The shading-tilt adjustment now respects the resident *"allow shading"* setting like every other shading movement

---

# CCA 2026.06.16

- 🐛 **Fix:** The *"shade the cover only once per day"* option was effectively inactive for everyone who does not manually move their covers by hand. The daily guard allowed shading again whenever no manual change had happened since the last shading — and since that is *always* the case when you never touch the cover by hand, the guard never blocked a second shading. Covers therefore re-entered the shading position again and again throughout the day (and the repeated shading-end movements made the cover look like it was *also* opening multiple times). The guard is now purely calendar-based: once the cover has shaded today, it will not shade again until the next day

---

# CCA 2026.06.14

- 🐛 **Fix:** The blueprint failed to import (YAML parsing error *"expected \<block end\>, but found ?"* at the `trace:` key) since the *"Number of stored traces"* setting was added. The `trace:` top-level key was indented by one space, which made it part of the preceding `actions:` block instead of a separate automation-level key. It is now correctly placed at the top level, so importing via the official button or the standard/raw URL works again ([#532](https://github.com/hvorragend/ha-blueprints/issues/532))
- 🐛 **Fix:** When the shading conditions were already met *before* the opening time, the cover stayed closed all morning instead of moving into the shading position. At the opening time the handler correctly deferred to the shading execution, but the execution then refused to move the cover: its position check only drove the cover *down* to the shading position, while a cover that was still fully closed sits *below* the shading position (e.g. shading position 3 %, closed 0 %). As a result nothing happened — no movement, the shading state was never recorded, and the cover stayed stuck closed (and the slats never tilted into the shading angle). The shading-start branch now also raises a closed cover up to the shading position when the schedule wants it open ([#530](https://github.com/hvorragend/ha-blueprints/issues/530))

---

# CCA 2026.06.08

- ✨ **Feature:** The *"Reset manual override"* setting now accepts **multiple** reset mechanisms at the same time. Previously the four options (*disabled*, *at fixed time*, *after timeout*, *in position*) were mutually exclusive; you can now combine e.g. *Reset in position* with *Reset after a timeout* as a safety net for when you forget to drive the cover back to the reset position. The first triggered reset wins. Existing single-value configurations continue to work unchanged. To disable all timed resets, leave the field empty ([#522](https://github.com/hvorragend/ha-blueprints/issues/522))
- ✨ **Feature:** The *"Reset in position"* mechanism now has its own *"Dwell time at reset position (minutes)"* input (default: 5 minutes), independent from *"Number of minutes until reset manual override"*. This makes combining *Reset in position* with *Reset after a timeout* sensible — each reset can be tuned independently
- 🐛 **Fix:** When a shading-start pending was armed before the opening time and the shading conditions were *still* met when the opening time fired, the cover opened normally instead of staying in shading — but only for setups using **calendar-controlled opening times** (or any opening trigger other than the early time trigger). The opening handler's "Opening skipped: Shading start pending" branch now correctly evaluates whether shading is still warranted, but on a calendar opening the weather forecast was never loaded, so the forecast-based conditions defaulted to *false*, "still warranted" evaluated to *false*, and the cover opened. The forecast is now loaded for every opening-related trigger (early/late time, brightness, sun elevation, calendar start), so the *"defer to shading execution while still warranted"* logic works regardless of which trigger fires the opening ([#514](https://github.com/hvorragend/ha-blueprints/issues/514))
- 🔧 **Improvement:** When a shading-start countdown was armed *before* the configured opening time (e.g. the shading conditions were already met at dawn), the maximum retry duration was counted from that early arming moment instead of from when the shading time window actually opens. As a result a large part of the configured "maximum duration for shading start retry loop" was consumed while merely waiting for the window to open, and the retry loop could abort with *"Shading Start aborted: Timeout or invalid"* shortly after the window opened — even though plenty of retry time was supposedly configured. The retry budget is now anchored to the start of the shading time window when arming early, so the configured duration applies *within* the window as intended ([#524](https://github.com/hvorragend/ha-blueprints/issues/524))

---

# CCA 2026.06.07

- 🐛 **Fix:** When a resident left (presence `on → off`) or arrived while a window was tilted, the cover stayed in the ventilation position instead of opening fully. With the schedule set to "open" (`bas=opn`) and no shading/privacy active, ventilation is only a *floor* — the cover should open completely because no ventilation is needed at that point. The "Resident leaving: target VENTILATION (window tilted)" and "Resident arriving: window tilted → hold ventilation position" branches only checked the tilted sensor and drove to the ventilation position regardless of the effective target. They now also require `effective_state == 'vnt'`, so when the base state is open the branch is skipped and the cover opens fully; at night (`bas=cls`) ventilation remains the correct floor. This matches the priority cascade (BASE=OPN before VENT) already used by the contact handler ([#460](https://github.com/hvorragend/ha-blueprints/issues/460), [#513](https://github.com/hvorragend/ha-blueprints/issues/513))
- 🐛 **Fix:** When a cover was already open and the *latest* opening time fired, the cover was redundantly re-driven and its recorded opening time was overwritten with the late time ([#495](https://github.com/hvorragend/ha-blueprints/issues/495)). This had been fixed before but was accidentally reverted by a later change; it is now fixed again and covered by a regression test so it cannot silently come back
- 🐛 **Fix:** Briefly tilting a window during a shading start/end countdown could cancel the pending shading so it never executed. The ventilation handler for a tilted window reset the internal pending state; it now leaves the shading countdown untouched (same fix as for briefly opening/closing a window)
- 🐛 **Fix:** Manual override (`man:1`) was triggered by tiny hardware position drift. Some covers report their position with ±1 % jitter; if such a drift happened after the drive-settle window (e.g. the cover slipped from 58 % to 59 % a few minutes after shading), the manual-position detection treated it as a manual intervention and locked in the manual override. With `ignore_shading_after_manual` active, this then blocked the shading from ending — the cover stayed in the shading position even after the sun left the facade. The detection now applies a dead-band: a reported position change only counts as manual when it exceeds the configured *position tolerance*. Drift within the tolerance is ignored (set the tolerance to `0` to restore the previous behaviour of reacting to every change)
- 🐛 **Fix:** When a shading-start pending was armed before the opening time (brightness briefly exceeded the threshold) and the conditions then fell back below the threshold *before* the opening time, the cover stayed closed all morning. At the opening time the handler logged *"Opening skipped: Shading start pending"* and deferred to the shading execution trigger — but that trigger only ever drives into the shading position or retries/aborts, it never opens the cover. The result was a blind stuck closed despite the opening time having passed. The opening handler now defers to the shading execution only while shading is *still warranted* (start conditions still met, or independent-temperature mode active); when the pending is stale it is cleared and the cover opens normally ([#514](https://github.com/hvorragend/ha-blueprints/issues/514))

---

# CCA 2026.06.02

- 🔧 **Improvement:** The reset timer of the *"reset in position"* option now uses the configured minutes directly, so the Home Assistant editor displays it correctly. Note: the *"Error in describing condition"* messages reported in [#512](https://github.com/hvorragend/ha-blueprints/issues/512) are a cosmetic Home Assistant frontend issue and do not affect how the automation runs

---

# CCA 2026.05.31

- 🔧 **Improvement:** Clarified the description of *"Independent Shading via Temperature Comparison"*. The text now states explicitly that this mode bypasses the sun position (azimuth **and** elevation) and brightness, that shading can therefore start even when the sun is not on the facade, and that the bypass is not limited to the morning but applies all day while the temperature stays above the threshold. Users who want shading to keep respecting the sun position should leave the option unchecked
- ✨ **Feature:** New option for reset manual override *"reset in position"*. This option will automatically clear the manual override state and restore automatic control once the cover reaches a specific target position (± configured tolerance) and remains there for the duration of the defined timeout. *Use Case:* Keep the blind in manual mode after lowering it by hand, and only let the automation take over again once the blind is fully reopened to 100%. Many thanks to [@wildcs](https://github.com/wildcs) for contributing this feature ([#506](https://github.com/hvorragend/ha-blueprints/pull/506))
- 🐛 **Fix:** Four handlers could drive the cover to the ventilation position even when ventilation was blocked by `resident_allow_ventilation` or the *Additional Condition For Activating Ventilation* — only the contact handler correctly checked both gates. The affected branches are: (1) the closing trigger's tilted branch, (2) "Ventilation after shading ends", (3) "Resident leaving: target VENTILATION (window tilted)", (4) "Resident arriving: window tilted → hold ventilation position", and (5) "Force disabled recovery: return to VENTILATION (window tilted)". All five now evaluate `resident_flags.allow_ventilate` and `auto_ventilate_condition`; when not met the branch is skipped and the cover follows the normal schedule instead ([#504](https://github.com/hvorragend/ha-blueprints/issues/504))

---

# CCA 2026.05.30

- 🐛 **Fix:** *"Don't end shading if cover is already closed"* no longer ends shading (opening the cover) when the cover was manually closed **further** than the configured close position. The guard checked `in_close_position`, which is a tolerance window centered on the configured close position — a cover driven below that position (e.g. fully closed at 0 % while the close position is 15 %) was treated as "not closed", so shading ended and the cover opened. The condition now also treats a position below the close position (`current_below_close`, awning-aware) as closed ([#502](https://github.com/hvorragend/ha-blueprints/issues/502))

---

# CCA 2026.05.29 V3

- 🐛 **Fix:** When a resident was present and shading conditions became true in the meantime (shading blocked by resident presence because `resident_allow_shading` was not configured), the cover opened normally after the resident left but shading never activated on that day — the sun-position template triggers only fire on FALSE→TRUE transitions and do not re-fire when conditions were already TRUE during residence. `resident_flags.allow_shade` is removed from the top-level "Check for shading start" conditions so the pending mechanism arms normally; the existing "Save shading state for the future" branch in the execution handler is extended with `OR not resident_flags.allow_shade`, so it saves `shd=1` alongside the already-handled `effective_state == 'cls'` case. The existing "Resident leaving: target SHADED" branch then drives to the shading position when the resident leaves.

---

# CCA 2026.05.29 V2

- 🐛 **Fix:** `ts.opn` no longer overwritten by the late opening trigger when the cover was already opened earlier the same day. The "Already in open position" branch now catches all cases where the cover is at open position with `effective_state=opn` — including the case where `bas=opn` and `ts.opn` is already from today. `ts.opn` is only refreshed when there is a real base-state transition or when the timestamp is from a previous day; otherwise the existing value is preserved. Additionally, the late trigger no longer redundantly drives the cover or clears the manual override ([#495](https://github.com/hvorragend/ha-blueprints/issues/495))

---

# CCA 2026.05.29

- 🐛 **Fix:** Shading never executed when pending-start (`pnd=beg`) armed before the opening time window and the opening trigger fired at window-start — the opening handler's "Shading detected" branch matched on `helper_state_pending_start`, cleared the pending state (`pnd=non`, `ts.due=0`) without driving the cover (because `effective_state != 'shd'` while `shd` was still `0`), causing the `t_shading_start_execution` trigger to be silently killed. The opening handler now defers to the execution trigger: a new "Opening skipped: Shading start pending" branch preserves `pnd`, `ts.due`, and `ts.arm`, updates only the base state (`bas=opn`, `ts.opn`), and lets the execution trigger fire 1 second later to handle the drive — including the correct retry/abort logic for manual overrides.

---

# CCA 2026.05.28 V2

- ✨ **Feature:** New input *"Independent Temperature Threshold"* (`shading_independent_temp`) for the *"Independent Shading via Temperature Comparison"* mode — previously this mode shared the same threshold as the normal forecast condition, causing both paths to be blocked simultaneously when the threshold wasn't met. The dedicated threshold can be set lower (e.g. 23 °C) while keeping a stricter value in the AND conditions, without either path interfering with the other ([#491](https://github.com/hvorragend/ha-blueprints/issues/491))
- 🔧 **Improvement:** Clarified selector label and description for *"Also trigger if Temperature Sensor 2 exceeds Forecast Temperature Value"* — the previous label implied a forecast-vs-sensor comparison but the actual logic checks whether Sensor 2 exceeds the (independent) threshold

---

# CCA 2026.05.28

- 🐛 **Fix:** Cover no longer closes when the window is closed while a resident is present but privacy-closing is not configured. The contact "window closed" handler treated any resident presence as a privacy-close trigger ("Return to open" required the resident to be absent; "Return to close" fired on mere presence). It now mirrors `effective_state`: privacy-close applies only when `resident_closing_enabled` is configured, or when opening is not permitted (`resident_allow_opening` unset). With `bas=opn` and no shading, the cover correctly returns to the open position after the window closes.

---

# CCA 2026.05.27 V2

- 🐛 **Fix:** Contact sensor "window closed" branches no longer destroy active shading pending phase (`pnd`, `ts.due`, `ts.arm`) — briefly opening and closing a door/window during shading-start or shading-end pending no longer prevents shading from executing ([#484](https://github.com/hvorragend/ha-blueprints/issues/484))
- 🐛 **Fix:** "Window closed" branches no longer fire spuriously when cover is at open position but was never in ventilation mode — removed overly broad `in_open_position` fallback from the "was ventilating before" OR condition ([#484](https://github.com/hvorragend/ha-blueprints/issues/484))
- 🐛 **Fix:** Shading end never triggered when only elevation (or only azimuth) was configured as end condition — the combined sun-position trigger `t_shading_end_pending_5` used OR logic for azimuth and elevation in a single template, so when azimuth left the range first (without meeting end conditions), the trigger stayed TRUE and never re-fired when elevation later dropped below threshold ([#483](https://github.com/hvorragend/ha-blueprints/issues/483))

---

# CCA 2026.05.27

- ✨ **Feature:** New ventilation option to disable the drive delay when ventilation starts (window opens/tilts) — useful for setups with many covers where a large fixed delay is needed for staggering, but single-cover ventilation reactions should be instant
- 🐛 **Fix:** Shading start pending armed before time window opens no longer aborts immediately — `ts.due` is now set to `max(now + waitingtime, window_start)`, ensuring execution fires after the window opens instead of aborting with only seconds elapsed of a multi-hour `max_duration` budget ([#475](https://github.com/hvorragend/ha-blueprints/issues/475))
- 🐛 **Fix:** Shading End never executed when using Calendar time control — `t_shading_end` triggers were missing from the `calendar.get_events` performance filter, causing `is_shading_allowed_window` to always evaluate to `false` ([#477](https://github.com/hvorragend/ha-blueprints/issues/477))

---

# CCA 2026.05.26

- 🐛 **Fix:** Contact handler incorrectly lowered cover to ventilation position when base state was open (`bas=opn`) and window transitioned from fully open to tilted ([#460](https://github.com/hvorragend/ha-blueprints/issues/460))
- 🔧 **Improvement:** `effective_state` now reads the window state from **live contact sensors** instead of the stale helper field — eliminates an entire class of stale-state bugs where `effective_state` returned `lock` instead of the correct cascade result during contact handler execution
- 🐛 **Fix:** Shading condition regex `"shd"\s*:\s*1` falsely matched the `ts.shd` timestamp (e.g. `"shd":1779701945`) inside the nested `ts` object, blocking all `t_shading_start_pending_*` triggers even when shading was inactive ([#467](https://github.com/hvorragend/ha-blueprints/issues/467))

---

# CCA 2026.05.25

- 🐛 **Fix:** Shading start pending blocked when status helper is uninitialized (e.g. after fresh setup)
- 🔧 **Trace Analyzer:** Shading Conditions Deep-Dive now shows independent temperature mode status — displays whether the temperature bypass is active and the effective start decision. This makes it visible when independent mode overrides the standard AND/OR conditions. ([#459](https://github.com/hvorragend/ha-blueprints/issues/459))

---

# 🚀 CCA 2026.05.24 — New State Machine, Priority Cascade, Force Pause & 30+ Bug Fixes

This is the biggest CCA update since the initial release — a **complete architecture overhaul** of the automation engine, combined with powerful new features and months of stability fixes.

**What's new at a glance:**
- 🧠 **New State Machine v6** with a clearly defined 7-layer Priority Cascade
- 📦 **Mandatory JSON Helper v6** with automatic migration from v5
- ⏸️ **Force Pause** — suspend all movements while keeping state in sync
- ⚙️ **AND/OR operators** for brightness & sun elevation conditions
- 📝 **Optional Logbook** entries for debugging without trace limits
- 🪟 **Keep Cover Open** on full-to-tilt window transition
- 🔧 **30+ bug fixes** across shading, force functions, ventilation, manual override & more
- ⚠️ **Behavior change**: BASE=OPN now beats VENT in the priority cascade

---

## ⚠️ Breaking Changes & Migration

### Priority Cascade: BASE=OPN now beats VENT

When the time schedule is in the *open* window (`bas=opn`) and a window is tilted, the cover now **opens fully** instead of stopping at the ventilation position.

| Situation | Before | After |
|-----------|--------|-------|
| Daytime (`bas=opn`), window tilted, no shading/privacy | Cover at ventilation position (e.g. 50%) | **Cover fully open (100%)** |
| Closing time (`bas=cls`), window tilted | Cover at ventilation position | Cover at ventilation position *(unchanged)* |
| Shading active, window tilted | Cover at ventilation position | Cover at ventilation position *(unchanged)* |

**Rationale:** A tilted window expresses ventilation intent — and a fully open cover provides the maximum possible airflow. VENT now acts as a *floor*: it only kicks in when the cover would otherwise close, shade, or be restricted from opening.

**To restore previous behavior:** Close the window or remove the time schedule (so `bas` never reaches `opn`).

### Automation Options Consolidated

All enable/disable decisions are now centrally located in the **Automation Options** section (`auto_options`):

| Before | After | Breaking? |
|--------|-------|-----------|
| `time_control: time_control_disabled` | Uncheck `time_control_enabled` in `auto_options` | ⚠️ Legacy (still works, but deprecated) |
| Brightness & Sun Elevation operator in Sun Elevation section | Moved to Automation Options section | ✅ No |

**Backward compatible:** Existing automations without `time_control_enabled` in `auto_options` continue to work as before.

### Helper Schema Cleanup

The shading-pending state is now type-safe: a single `pnd` enum (`non` / `beg` / `end`) plus `ts.due` (fire time) and `ts.arm` (retry anchor). Helper version remains v6 — **auto-migration handles everything**.

A defensive cleanup also fires whenever the stored `ts.*` contains keys that are no longer part of the schema — this preserves all live state and resets any pending to idle.

**For custom card templates / external tooling:** Use the new keys (`pnd`, `ts.due`, `ts.arm`). See the updated card examples in [`examples/`](https://github.com/hvorragend/ha-blueprints/tree/main/examples).

---

## 🧠 New Architecture: State Machine v6 & Priority Cascade

The automation now resolves the cover's target state through a clearly defined **priority cascade**, evaluated on every run. Higher-priority states always win:

| Priority | State | When active |
|----------|-------|-------------|
| 1 – highest | **FORCE** | Any force function is active (Force Open/Close/Shade/Ventilate) |
| 2 | **LOCKOUT** | Window is fully open — cover must not close |
| 3 | **BASE=OPN** | Time schedule = open, no privacy/shading/restriction → fully open |
| 4 | **VENT** | Window tilted **and** cover would otherwise be below ventilation height |
| 5 | **PRIVACY** | Resident present + closing trigger configured → close |
| 6 | **SHADING** | Sun shading is active |
| 7 – lowest | **BASE=CLS** | Time schedule = close |

This replaces the previous implicit state resolution and makes the cover's behavior **predictable in every situation**, including when multiple states are active simultaneously.

### Mandatory JSON Helper v6

The **Cover Status Helper** (`input_text`, minimum 254 characters) is now **required**. It stores all relevant state: base state, shading status, window sensor state, force function, resident presence, manual override flag, and timestamps for every state transition.

- **Existing helper users:** Automatic migration from v5 to v6 on first run — no manual action needed
- **New users:** Create an `input_text` helper with at least 254 characters (Settings → Devices & Services → Helpers)

---

## ✨ New Features

### ⏸️ Force Pause — Suspend All Movements

A new optional `force_pause` input (`input_boolean` or `switch`) allows suspending all automatic cover movements while keeping the background state fully up to date.

- While active: all triggers fire, helper is updated — only movement is blocked
- When turned off: cover **immediately drives** to the correct target position
- **Superior to the global condition:** the global condition freezes state tracking, so when you re-enable, the helper is stale and the cover only catches up at the next scheduled trigger (possibly hours away). Force Pause solves this.

**Use case:** A manual/automatic toggle switch. Flip it off to pause, flip it back on → instant correct position.

### ⚙️ AND/OR Operator for Brightness & Sun Elevation

The combination of *Brightness* and *Sun Elevation* conditions is now configurable via `brightness_sun_operator`:

- **OR (default):** Cover opens/closes when **either** condition crosses the threshold (matches previous behavior)
- **AND:** Cover opens/closes only when **both** conditions cross their thresholds — useful to avoid premature triggers

When only one sensor is enabled, the operator is irrelevant.

### 📝 Optional Logbook Entries

A new opt-in **Logging** section (`enable_logbook`) writes a structured logbook entry on every automation run:

- Trigger ID, effective state, current cover position
- Window / resident / force sensor states
- Full `update_values` JSON written to the helper
- Selected branches attach extra context (shading retry, pending timing)

**Default: off.** Toggle on while debugging — the 5-trace limit in Home Assistant no longer caps your ability to reconstruct what the cover did over the course of a day.

### 🪟 Keep Cover Open on Full-to-Tilt Transition

New option `ventilation_keep_open_on_full_to_tilt`: when a window changes from fully opened to tilted, the cover stays at the open position instead of lowering to the ventilation position. Useful for terrace doors where you come back inside, tilt the door, and don't want the cover moving down.

### 🏠 Resident Handling Redesign

Resident control was completely redesigned. A single smart trigger now handles both arrival and departure, including all environment checks and resident flags. When a force function is deactivated, the cover automatically returns to the correct state (open, closed, shading, or ventilation) without manual intervention.

---

## 🔧 Bug Fixes

### Force Functions

- **Force features blocking themselves** ([#339](https://github.com/hvorragend/ha-blueprints/issues/339)): Force triggers now bypass the `is_cover_movement_blocked.any` check.
- **Covers closing during ventilation despite active force** ([#337](https://github.com/hvorragend/ha-blueprints/issues/337)): Ventilation recovery now respects active force features.
- **Force recovery ignoring resident sensor** ([#332](https://github.com/hvorragend/ha-blueprints/issues/332)): Force recovery now validates resident conditions.
- **Force operations incorrectly updating helper** ([#318](https://github.com/hvorragend/ha-blueprints/issues/318)): Force operations now preserve the background helper state.
- **Force priority: "Last Wins"** ([#342](https://github.com/hvorragend/ha-blueprints/pull/342), [#377](https://github.com/hvorragend/ha-blueprints/pull/377)): When multiple forces are active, the last activated one wins. Disabling one force correctly falls back to the remaining active force.
- **Cover incorrectly closes when window closes during Force-Ventilation** ([#445](https://github.com/hvorragend/ha-blueprints/issues/445)): The contact handler now respects the active force.
- **Background state always kept up to date during force functions**: The automation continues to track the scheduled state while force is running.
- **Force-disabled recovery respecting environmental conditions** ([#310](https://github.com/hvorragend/ha-blueprints/issues/310), [#312](https://github.com/hvorragend/ha-blueprints/issues/312)): Covers now check sun elevation and brightness before reopening after force ends.

### Shading

- **Shading never starts with `weather_attributes` forecast mode** ([#399](https://github.com/hvorragend/ha-blueprints/issues/399)): Weather condition was read from attribute instead of entity state. Fixed.
- **Shading-start retry aborts on a fresh day** ([#408](https://github.com/hvorragend/ha-blueprints/issues/408), [#416](https://github.com/hvorragend/ha-blueprints/issues/416)): A dedicated retry anchor (`ts.arm`) now ensures the configured retry window is honored correctly.
- **Cover stuck in shading when conditions change rapidly** ([#395](https://github.com/hvorragend/ha-blueprints/issues/395)): Stale pending state blocked all subsequent shading-end attempts. Pending is now cleared correctly.
- **Shading-start pending stuck outside shading window** ([#430](https://github.com/hvorragend/ha-blueprints/issues/430)): Pending armed inside the shading window was never cleared when the window moved past. Fixed.
- **Shading not triggering after cover opens** ([#325](https://github.com/hvorragend/ha-blueprints/issues/325)): Shading conditions are now re-evaluated when covers open.
- **Manual override ignored when shading state is stale** ([#447](https://github.com/hvorragend/ha-blueprints/issues/447)): The "Manual: unknown position" branch now clears stale shading state and pending.
- **Pending shading-start silent exit**: Added explicit `stop:` in `default:` branch so the trace clearly reports the termination reason.
- **Shading state persistence**: Correctly saved to the helper across reboots.
- **Defensive fallback for missing weather forecast**: Missing data treated as "no forecast available" instead of Jinja2 errors.

### Ventilation & Window Sensors

- **Window-opened sensor always takes priority over tilted**: Every branch explicitly checks that *opened* is not active before processing *tilted*. Lockout always beats ventilation.
- **Lockout works independently of `resident_allow_ventilation`**: Lockout is now a standalone safety feature. Only the tilted sub-branch requires `resident_allow_ventilation`.
- **Incorrect open status when window tilted during closing time**: The tilted-closing branch now correctly sets the base state to closed.
- **Base state not updated when closing trigger fires with tilted window**: The CLOSE handler now always records the base-state change, fixing `prevent_multiple_times` for the next day.
- **Ventilation-after-shading blocked by stale lockout gate** ([#426](https://github.com/hvorragend/ha-blueprints/issues/426)): Removed incorrect guard.

### Manual Override

- **`man` flag cleared in non-movement blocks**: Manual override was prematurely cleared after triggers that didn't drive the cover. `man: 0` is now only written when the cover actually moves.
- **Manual position detection trigger** ([#326](https://github.com/hvorragend/ha-blueprints/issues/326)): Replaced non-functional template trigger with separate state triggers. Manual changes reliably detected within 60 seconds.
- **Manual override flag not cleared after auto-driven tilt** ([#425](https://github.com/hvorragend/ha-blueprints/issues/425)): `man` flag is now correctly cleared when the automation drives the cover.

### Environment Sensors

- **Cover opens at early time without waiting for sensor threshold** ([#436](https://github.com/hvorragend/ha-blueprints/issues/436)): With only one sensor enabled + OR operator, the disabled sensor short-circuited the check to `true`. Both opening and closing now branch explicitly on which sensors are enabled.
- **Sun elevation triggers respect fixed/dynamic/hybrid modes**: Triggers `t_open_5` and `t_close_5` now correctly implement all three modes.
- **Brightness, temp1, temp2 trust their pending trigger**: A transient `invalid_states` no longer overrides a sensor that just fired the pending trigger.

### Resident Handling

- **Resident leaving correctly restores shading/ventilation position**: Previously the cover sometimes closed instead.
- **Resident leaving with window open no longer falls through to shading** (lockout takes priority).
- **Resident handler reads live sensor state**, not the helper's stale `res` value — eliminating race conditions.

### Other Fixes

- **Redundant cover movements prevented** ([#344](https://github.com/hvorragend/ha-blueprints/issues/344)): Cover no longer moves when already at target position.
- **Dead helper write in Force-Shade activation** ([#427](https://github.com/hvorragend/ha-blueprints/issues/427)): Removed unused `ts.shd` write.
- **Silent failures after v5 → v6 upgrade**: Fixed manual override timeout, shading start pending, and shading end conditions.
- **Opening incorrectly blocked** ([#354](https://github.com/hvorragend/ha-blueprints/issues/354)): A single permissive condition is now sufficient to allow opening.

---

## 📦 Helper Schema Update — `ts.arm`

The v6 JSON helper schema gained one additional field: **`ts.arm`** — a dedicated retry-sequence anchor timestamp used by the shading-start and shading-end retry logic. Automatically initialized on first run; no manual action required.

---

## 🛠️ Tool Updates

### CCA Configuration Validator
- Recognizes all new parameters (`sun_elevation_mode`, `force_pause`, `auto_options`, `brightness_sun_operator`, `enable_logbook`, `ventilation_keep_open_on_full_to_tilt`, etc.)
- Sun elevation validation rewritten with full mode-aware support (Fixed / Dynamic / Hybrid)
- New check: warns when required elevation sensors are missing for Dynamic/Hybrid mode

### Trace Analyzer v2.0
Fully updated for the new Branch 0–11 structure and v6 helper format. Supports v6 internal, v6 compact, and v5 legacy display. Includes new runtime variables and an aligned shading deep-dive view.

### Trace Compare v2.0
Updated to Branch 0–11 structure, extended trigger explanations, and same v6/v5 multi-format support.

---

## 📚 Documentation Updates

New FAQ sections:
- **State Hierarchy** — detailed explanation of how `effective_state` is resolved through the priority cascade
- **Force State Architecture** — when persisted helper state vs. real-time entity state is used
- **State Transition Matrix** — maps every trigger to its branch and resulting helper changes
- **Shading Pending Mechanism** — documents the two-phase trigger flow for delayed shading start
- **Window Sensor Priority** — why *opened* always beats *tilted*
- **How does a force function work?** — moved from inline help into the FAQ

New dashboard card examples (in [`examples/`](https://github.com/hvorragend/ha-blueprints/tree/main/examples)):
- **CCA Status Tile Card** — compact tile-style visualization
- **Flex-Table-Card** — full-row visualization of all helper fields

New guide:
- **[Window-Sun-Angle Aware Shading](WINDOW_SUN_ANGLE.md)** — step-by-step guide for window-orientation-aware shading via Force Shading

---


# 🚀 CCA 2026.01.26 - Force Features Self-Blocking Fix

## 🔧 Bug Fixes

- **Fixed Force features blocking themselves** (#339): Force Open/Close/Ventilation/Shading features can now execute properly. Previously, these features failed to move the cover because `cover_move_action` and `tilt_move_action` checked `is_cover_movement_blocked.any`, which was already `true` when the force feature was active. The movement blocking condition now allows Force triggers to bypass the check using regex pattern `trigger.id is match('^t_force_')`, enabling force features to work as intended while maintaining protection for background automations.


---


# 🚀 CCA 2026.01.23 - Force Features & Ventilation Recovery Fix

## 🔧 Bug Fixes

- **Fixed covers closing during ventilation despite active force features** (#337): Ventilation recovery now properly respects force features (force-open, force-close, etc.). Previously, covers would close when windows closed even when force-open was still active. Force feature checks are now centralized in YAML anchors for consistent behavior across all branches.


---


# 🚀 CCA 2026.01.22 - Force Recovery Resident Sensor Fix

## 🔧 Bug Fixes

- **Fixed force recovery ignoring resident sensor status** (#332): Force recovery (BRANCH 12) now validates resident sensor conditions before returning to background state. Previously, when a force function was disabled, the cover could execute an invalid action if the resident sensor status had changed while the force function was active.

---


# 🚀 CCA 2026.01.14 - Force State Preservation Fix

## 🔧 Bug Fixes

- **Fixed force operations incorrectly updating helper status** (#318): Force operations (force-open, force-close, force-ventilate, force-shading) now preserve the background helper state instead of updating it. 

---


# 🚀 CCA 2026.01.12 - Window Tilted Closing Time Fix

## 🔧 Bug Fixes

- **Fixed incorrect open status when window is tilted during closing time**: The "Window tilted - Move to ventilation position" branch (inside BRANCH 1: CLOSE) now correctly sets `open=0, close=1` to reflect that this is a closing action redirected to ventilation position. Previously, it incorrectly set `open=1, close=0`, causing shutters to open instead of close when the window was closed in the morning after being tilted during evening hours.

- **Fixed shading state persistence**: The shading state is now correctly saved to the helper. Previously, this state was lost, preventing the cover from directly entering shading mode when opening the following morning.

---


# 🚀 CCA 2026.01.11 - Manual Position Trigger Fix

## 🔧 Bug Fixes

- **Fixed manual position detection trigger** (#326): Replaced non-functional template trigger with separate state triggers for each position source (current_position, position, custom sensor). Manual position changes are now reliably detected within 60 seconds.

---


# 🚀 CCA 2026.01.09 - Shading Trigger Fix

## 🔧 Bug Fixes

- **Fixed shading not triggering automatically after cover opens** (#325): Shading conditions are now correctly re-evaluated when covers open, ensuring shading activates when all conditions are met.

---


# 🚀 CCA 2026.01.06 - Forecast Temperature Trigger Coverage

## ✨ New Features

- **Added missing state triggers for Forecast Temperature condition**: The `cond_forecast_temp` condition now has dedicated state-change triggers (`t_shading_start_pending_6` and `t_shading_end_pending_6`) for immediate reaction when forecast temperature sensor values change. Previously, forecast temperature was only evaluated via time-based trigger or when other conditions triggered, which caused incomplete AND/OR logic evaluation.

- **Note for Weather Entity Users**: When using a weather entity for forecast temperature (without a dedicated sensor), the existing weather condition trigger (`t_shading_start_pending_5` / `t_shading_end_pending_4`) will fire on weather entity updates. The forecast temperature is then loaded and evaluated in the action sequence, providing indirect coverage for weather entity-based forecast temperature.

---


# 🚀 CCA 2026.01.02 - Sun Elevation Trigger Mode Support

## 🔧 Bug Fixes

- **Fixed sun elevation triggers to respect fixed/dynamic/hybrid modes**: Triggers `t_open_5` and `t_close_5` now correctly implement all three sun elevation modes (fixed, dynamic, hybrid) ensuring consistent threshold calculation across the automation.

---


# 🚀 CCA 2025.12.31 - Force Recovery Environment Check

## 🔧 Bug Fixes

- **Fixed helper status update during force-disabled states** (#312): Helper status is now correctly updated even when force functions (e.g., force-close) are active. This ensures the background state is properly tracked during forced states, allowing covers to return to the correct position when force functions are deactivated. Previously, the helper update condition was stricter than the cover movement condition, causing inconsistent state tracking.

- **Fixed force-disabled recovery respecting environmental conditions** (#310): Covers now check sun elevation and brightness before reopening after force-disabled state ends (e.g., rain protection). Time-based triggers at `time_up_late`/`time_down_late` continue to work as ultimate fallback regardless of conditions.

---


# 🚀 CCA 2025.12.30 - Sun Elevation Modes (Fixed/Dynamic/Hybrid)

## ☀️ Three Sun Elevation Modes

- **Flexible threshold calculation with three distinct modes**
  Choose how sun elevation thresholds are determined based on your needs and setup complexity.

### 🔒 Fixed Mode (Default)
- **Simple and straightforward**
  Uses only the configured fixed values for sun elevation thresholds. Perfect for users who don't need seasonal adaptation or prefer manual configuration.

- **Sensors are ignored**
  Even if elevation sensors are configured, they will be ignored in this mode. This ensures predictable behavior and prevents confusion.

- **Backward compatible**
  All existing configurations without the mode field automatically use Fixed mode, ensuring seamless upgrades.

### 📊 Dynamic Mode
- **Seasonal adaptation**
  Uses only sensor values for threshold calculation. The fixed values are completely ignored. Ideal for automatic seasonal adjustments using template sensors.

- **Sensors required**
  Both up and down sensors must be configured and provide valid numeric values. Config check validates this requirement.

- **Year-round automation**
  Perfect for users who want fully automated seasonal adaptation without manual intervention. Use with the [Dynamic Sun Elevation Guide](https://hvorragend.github.io/ha-blueprints/DYNAMIC_SUN_ELEVATION).

### 🔄 Hybrid Mode
- **Best of both worlds**
  Combines sensor value + fixed value as offset. Allows seasonal adaptation with manual fine-tuning capability.

- **Additive calculation**
  Final threshold = Sensor value + Fixed value. Example: Sensor 2.0° + Fixed 1.5° = Threshold 3.5°.

- **Flexible fine-tuning**
  Use the sensor for seasonal base values and adjust the fixed offset for per-cover tweaking (e.g., different orientations).

### 🔧 Configuration & Validation
- **New sun_elevation_mode selector**
  Easy-to-understand dropdown with clear descriptions for each mode in the Sun Elevation Settings section.

- **Updated field descriptions**
  All sun elevation fields now explain their behavior in each mode, making configuration intuitive.

### 💡 Use Cases
- **Fixed Mode**: Simple setups, manual control preference, no seasonal needs
- **Dynamic Mode**: Full automation, seasonal adaptation, template sensor enthusiasts
- **Hybrid Mode**: Seasonal base + manual offset, multi-cover setups with different orientations

---

## 🔧 Bug Fixes

- **Fixed prevent_multiple_times flags respecting manual intervention**: The
  `prevent_opening_multiple_times`, `prevent_closing_multiple_times`, and
  `prevent_shading_multiple_times` flags now correctly respect manual user
  intervention. Automation will not retry if the user manually changed the
  cover position after an automation attempt, ensuring user decisions are
  always respected.
