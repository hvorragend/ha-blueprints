# CCA Known Bug Patterns (A–AL, with cause and fix)

The regression catalog. Most patterns are pinned by tests, but the *rules*
derived from them apply to new code. Read the matching pattern before changing
branch conditions, gates, deferrals/handoffs between flows, regex checks on the
helper JSON, or trigger `enabled:` templates.

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
**Cause B:** `pnd` / `ts.due` / `ts.arm` are reset in win-only helper updates.

**Fix:** Guard in `helper_update` — only apply `ts.shd` when `new_shd != current.shd`. Do not reset `pnd`/`ts.due`/`ts.arm` in win-only updates.

### Bug Pattern I: Shading-start retry aborts on fresh day (Issue #416)

**Symptom:** First retry attempt of the day aborts immediately when the start conditions are blocked by additional conditions or manual override; the `shading_start_max_duration` window is effectively zero on a fresh helper.

**Cause:** The duration check used `helper_ts_shade` (= `ts.shd`) as anchor. Pending establishment does not transition `shd`, so the Invariant-8 guard preserves `ts.shd` at its previous value (yesterday's shading-end or `0`). `now() - ts.shd` is therefore much larger than `shading_start_max_duration` → check fails → retry aborts.

**Fix:** Dedicated `ts.arm` field that records the retry-sequence start. Set in "Shading detected" (start) and "Shading end detected" (end), preserved across continues, cleared in all terminal branches of both sequences. Duration checks for both `shading_start_max_duration` and `shading_end_max_duration` now use `helper_ts_pending_arm`. The same field serves both directions because the sequences are mutually exclusive (Invariant 11, structurally enforced by `pnd`).

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

### Bug Pattern J: Contact handler lowers cover to ventilation when base state is open (Issue #460)

**Symptom:** When `bas == 'opn'` (opening time already fired) and the window transitions from fully open to tilted, the cover incorrectly lowers from 100% (open) to 50% (ventilation).

**Cause:** The tilted-drive branch's OR condition at the `helper_state_window == 'opn' and current_above_ventilate` alternative fires unconditionally when the window goes from open → tilted, regardless of whether `base_target == 'opn'`. Per the priority cascade, VENT is a floor — it should NOT lower a cover when `base_target == 'opn'`.

**Root fix:** `effective_state` was changed to derive `win` from **live contact sensors** instead of the stale `h.win` helper field. When sensors are configured, the live sensor value takes priority; when no sensors are configured, it falls back to `h.win`. This means `effective_state` now correctly returns `'opn'` (not `'lock'`) when the window transitions from open → tilted and `bas == 'opn'`. The tilted-drive branch guards with `{{ effective_state != 'opn' }}`, and the no-drive branch catches `{{ effective_state == 'opn' }}`.

### Bug Pattern K: `regex_search('"shd"\s*:\s*1')` matches `ts.shd` timestamp (Issue #467)

**Symptom:** All `t_shading_start_pending_*` triggers are blocked by condition/3 even though `shd == 0` (shading inactive). The automation stops despite valid shading conditions.

**Cause:** The regex `"shd"\s*:\s*1` is intended to check if the top-level `shd` field is `1`, but the helper JSON contains a nested `ts.shd` timestamp (e.g. `"shd":1779701945`) whose value starts with `1`. The regex matches this nested timestamp, making the condition think shading is already active.

**Fix:** Change all 6 occurrences of the regex to `"shd"\s*:\s*1\s*[,}]` — requiring a comma or closing brace after the `1` ensures it matches only the top-level `"shd":1,` and not a multi-digit timestamp value.

### Bug Pattern L: Shading pending arms before time window → execution aborts immediately

**Symptom:** Shading conditions are met shortly before `time_up_early_today` (e.g. 06:55 with window at 07:00). Pending arms successfully, but execution aborts with `"Shading Start aborted: Timeout or invalid"` despite having thousands of seconds of `shading_start_max_duration` remaining.

**Cause:** The outer if (line ~5196) allows pending triggers to bypass `is_shading_allowed_window` (via `trigger.id` match on `t_shading_start_pending`), but requires it for execution triggers. When `ts.due` (= `now + waitingtime`) resolves to a time before the window opens, the execution trigger fires too early, fails the outer if, and the retry also requires `is_shading_allowed_window` → abort.

**Fix:** In the pending arming branch, compute `ts.due` as `max(now + waitingtime, window_start_time)`. When the window is already open, this equals `now + waitingtime` (unchanged). When arming before the window, execution is deferred to the window start. No retry logic changes needed — the execution fires within the window and the normal flow handles it.

### Bug Pattern M: Combined sun-position trigger swallows independent elevation/azimuth end (Issue #483)

**Symptom:** Shading never ends even though the sun elevation drops below the configured end threshold. The trigger fires earlier (when azimuth goes out of range) but the end conditions are not met. When elevation later drops below threshold, no trigger fires.

**Cause:** `t_shading_end_pending_5` combined azimuth and elevation checks in a single template trigger using OR logic. HA template triggers fire on FALSE→TRUE transitions only. When azimuth goes out of range first, the template becomes TRUE and the trigger fires. But `shading_end_conditions_met` is FALSE (user only configured elevation as end condition). When elevation later drops below threshold, the template is already TRUE (from azimuth) → no re-fire → shading end never triggers.

**Fix:** Split `t_shading_end_pending_5` into two independent triggers:
- `t_shading_end_pending_5`: azimuth only (outside configured range)
- `t_shading_end_pending_7`: elevation only (outside configured range)

Each condition gets its own independent FALSE→TRUE transition. Update condition regex `[1-6]` → `[1-7]` and `is_shading_end_immediate_by_sun_position` check to match both trigger IDs.

*(The regex ranges above are historical. Since the `_8` triggers — custom condition sensor — were added, the live global-gate regexes are `^t_shading_start_pending_([1-6]|8)$` and `^t_shading_end_pending_[1-8]$`; start `_7` deliberately bypasses the global shd-gate.)*

### Bug Pattern N: Contact handler destroys active shading pending phase (Issue #484)

**Symptom:** Briefly opening and closing a door/window during a shading-start (or shading-end) pending phase prevents shading from ever executing. The pending timer (`ts.due`) is reset to `0`, and the sun-position trigger doesn't re-fire because the azimuth condition hasn't changed (no FALSE→TRUE transition).

**Cause A:** All "Window closed" sub-branches (`Return to shading`, `Return to open`, `Return to close`) and the "Window opened - Full ventilation (lockout)" branch unconditionally set `pnd: 'non'`, `ts.due: 0`, `ts.arm: 0` in their `update_values`.

**Cause B:** The "was ventilating before" OR condition includes `in_open_position`, which matches whenever the cover happens to be at open position — even when CCA was never in ventilation mode (`win == 'cls'` the entire time). This causes spurious "Window closed" branch matches.

**Fix A:** Remove `pnd`/`ts.due`/`ts.arm` from `update_values` in all contact handler branches. The `helper_update` anchor preserves existing values when keys are omitted.

**Fix B:** Remove `in_open_position` from the "was ventilating before" OR condition in all three "Window closed" branches. The dedicated "No drive, sync" branches already ensure `helper_state_window` is correctly updated when the window opens/tilts.

### Bug Pattern O: Contact "window closed" handler closes on bare resident presence

**Symptom:** With `bas == 'opn'`, no shading, no force, and a resident present, closing the window lowers the cover from open to close — even though `effective_state == 'opn'` and the user never configured privacy-closing.

**Cause:** The "Window closed" return branches used raw `resident_now` as a privacy proxy. "Return to open" required `helper_state_base == 'opn' and not resident_now`, and "Return to close" fired on `helper_state_base == 'cls' or resident_now`. Any resident presence therefore forced a close, diverging from `effective_state`, whose `privacy_active` requires `'resident_closing_enabled' in resident_config` (and whose `allow_open` gate closes only when `resident_allow_opening` is unset).

**Fix:** Introduce `resident_blocks_open` in the post-delay contact-handler variables:
```jinja2
resident_now and (resident_flags.closing_trigger or 'resident_allow_opening' not in resident_config)
```
Use `not resident_blocks_open` in "Return to open" and `resident_blocks_open` in "Return to close". This mirrors `effective_state`'s privacy + allow_open gates exactly, so the contact handler agrees with the cascade.

**Rule:** Contact "window closed" return branches must resolve open-vs-close from the same gates as `effective_state` (privacy + allow_open), never from bare presence.

---

### Bug Pattern Q: Hardware position drift triggers false manual override

**Symptom:** Some minutes after the automation drives the cover (e.g. to the shading position 58 %), the cover reports a tiny position drift on its own (58 % → 59 %, stable ≥ the trigger's `for: 60s`). `t_manual_position` fires *outside* the drive-settle window, the "Manual: …" handler sets `man: 1`. With `ignore_shading_after_manual` active, the shading-end branches (gated by `not (helper_state_manual and override_flags.shading)`) are then blocked → the cover stays in the shading position even after the sun leaves the facade, until `reset_override_timeout` clears the override.

**Cause:** The manual-detection gate in "Checking for manual position changes" only required `trigger.from_state ... != trigger.to_state ...` — **any** position change after the `now > helper_json.t + drive_time + 60` settle window counted as manual. There was no dead-band, so a ±1 % hardware/integration jitter (even one that keeps the cover *within* `position_tolerance` of where CCA put it, i.e. `in_shading_position` still `True`) was treated as a manual intervention. The trigger's own `for: 60s` confirms the drift is stable, so a transient filter does not help.

**Fix:** Replace the `!=` detection with a dead-band against `position_tolerance` for all three position sources (`custom_sensor` → state value, `current_position_attr`, `position_attr`):
```yaml
- "{{ ((trigger.to_state.attributes.current_position | float(0)) - (trigger.from_state.attributes.current_position | float(0))) | abs > position_tolerance }}"
```
A change only counts as manual when its magnitude *exceeds* `position_tolerance`. With `position_tolerance = 0` the old behaviour (react to every change) is restored. The tilt-detection branch is intentionally left unchanged (no tilt tolerance exists).

**Note — not solved by raising `position_tolerance` alone:** before this fix the detection ignored the tolerance entirely (`!=` only). The tolerance governed *which* branch was chosen (`in_shading_position`), not *whether* manual was detected. The dead-band ties the two together.

### Bug Pattern R: Stale shading-start pending leaves cover stuck closed at opening time (Issue #514)

**Symptom:** Brightness briefly exceeds the shading threshold *before* the opening time → shading-start pending arms (`pnd: 'beg'`, `ts.due` deferred to `window_start + 1` per Bug Pattern L). Brightness then falls back below the threshold, still before the opening time. At the opening time the cover stays closed; the trace shows `"Opening skipped: Shading start pending"`. The cover never opens that morning.

**Cause:** The opening handler's "Opening skipped: Shading start pending" branch gated only on `helper_state_pending_start`, so it deferred to `t_shading_start_execution` unconditionally. But the execution trigger only ever drives into the shading position or retries/aborts — it **never opens the cover**. With the conditions no longer met, execution loops in "Continue waiting" (until `shading_start_max_duration` from `ts.arm`) and then aborts — the cover is never opened, because the opening intent was already consumed (skipped) at the opening trigger.

**Fix:** Add `shading_start_warranted` (new variable, defined next to `shading_start_conditions_met`) to the "Opening skipped: Shading start pending" branch conditions. It mirrors the execution gate: `shading_start_conditions_met or (independent-temperature path active)`. When the pending is stale (`shading_start_warranted == false`), the branch is skipped and execution falls through to "Normal opening", which drives the cover open and clears `pnd`/`ts.due`/`ts.arm`. When still warranted, the defer behavior is unchanged. See the design decision "Opening handler preserves shading-start pending **only while still warranted**".

---

### Bug Pattern S: `shading_start_max_duration` budget consumed by pre-window wait (Issue #524)

**Symptom:** Shading-start conditions are met well *before* the opening time (e.g. independent-temperature mode at dawn). The pending arms, `ts.due` is correctly deferred to the window start (Bug Pattern L). Inside the window the start is gated off by an additional condition (`auto_shading_start_condition`) or unstable conditions, so the loop retries. But the retry loop aborts with `"Shading Start aborted: Timeout or invalid (blocked)"` much earlier than the configured `shading_start_max_duration` would suggest — e.g. only ~1 h of in-window retry on a 2 h budget.

**Cause:** The "Shading detected" arming branch set `ts.arm: "now"` at the (pre-window) arming moment, and the max-duration checks compute `now - helper_ts_pending_arm`. When the pending arms an hour before the window opens, that hour is counted against the budget even though no real retry happens during it (the cover only waits for the window). When `ts.due` is deferred directly to the window start, the "waiting for time window" branches (which re-anchor `ts.arm` to `now` on each pre-window retry) never run, so `ts.arm` stays at the early arming time and the budget is silently shortened.

**Fix:** In the "Shading detected" arming branch, anchor `ts.arm` to the start of the shading window when arming early. Compute a `shading_start_arm` variable mirroring `shading_start_due` but without the `+ waitingtime`/`+1`: `max(now, window_start)` where `window_start` is `today_at(time_up_early_today)` (time field) or `calendar_open_start` (calendar), and plain `now` when the window is already open or time control is disabled. The "waiting for time window" retry branches keep `arm: "now"` — they already push the anchor forward to ~window-open by re-arming every `waitingtime` seconds.

**Note:** This is distinct from the underlying *configuration* cause that usually surfaces this symptom: an `auto_shading_start_condition` that stays `false` through the whole window (e.g. "outdoor temp > 14 °C" when it is 13.7 °C) will still abort after the (now correctly-sized) budget. The additional condition is a *gate*, not a trigger — if its entity is not also a shading trigger source, a value that only crosses the threshold later in the day will not re-arm the pending.

---

### Bug Pattern T: Weather forecast not loaded on non-`t_open_1` opening triggers breaks `shading_start_warranted` (Issue #514 follow-up)

**Symptom:** A shading-start pending is armed before the opening time and the shading conditions are *still* met when the opening time fires. The cover should stay in shading (the opening handler defers to the shading execution per Bug Pattern R). Instead the cover opens normally — but only for users on **calendar-controlled opening** (`t_calendar_event_start`) or any non-`t_open_1` opening trigger (`t_open_2/4/5`). The trace shows the "Opening skipped: Shading start pending" branch was *not* selected, "Normal opening" ran, and the pending was cleared.

**Cause:** The forecast-load gate (line ~4207) only ran `weather.get_forecasts` when the trigger matched `^(t_shading_start|t_open_1)`. Other opening triggers were excluded. With the forecast not loaded, `weather_forecast` is undefined, `forecast_temp_raw` and `forecast_weather_condition_raw` fall through to `None`, and `forecast_temp_valid`/`forecast_weather_valid` evaluate to `false` whenever the user has configured those conditions. `shading_start_warranted` therefore evaluates to `false`, the "Opening skipped: Shading start pending" branch (which gates on `shading_start_warranted` per the Bug Pattern R fix) is skipped, and execution falls through to "Normal opening". `independent_temp_valid` is affected too (depends on `forecast_temp_raw`), so the independent-temperature path also breaks under the same conditions.

**Fix:** Widen the regex to `^(t_shading_start|t_open|t_calendar_event_start)` so the weather forecast is loaded on every opening-related trigger. This mirrors the top-level "Check for opening" branch gate (`^(t_open|t_calendar_event)`) plus the existing shading-start triggers, ensuring `shading_start_warranted` is evaluated against fresh forecast data whenever the opening handler may need it. The closing handler discards pending unconditionally and never reads `shading_start_warranted`, so it does not need the forecast.

**Why only this user setup hit it:** The original `t_open_1` covered the most common time-based opening. Bug Pattern R (#514, CCA 2026.06.07) added the `shading_start_warranted` gate without revisiting the forecast-load gate — the moment the user's setup uses a calendar trigger or a late/brightness/sun-elevation opening trigger, the gate's premise (forecast already loaded) silently breaks.

**Second recurrence (#603, CCA 2026.07.13 V6):** the recovery gate's `recovered_pending` is a third consumer of `shading_start_warranted`, and the resumed-run backstop (`automation_resumed`) reaches it through **any** trigger id — `t_close_*`, `t_resident_update`, the contact triggers. None of them match the gate's regex, so the forecast was again not loaded, `recovered_pending` refused a warranted shading, and the helper write cleared `automation_resumed` → the miss was permanent for that day. Fix: the gate matches `automation_resumed` in addition to the trigger ids.

**Third recurrence (CCA 2026.07.13 V6):** the **calendar-load gate** two steps below the forecast gate had the identical shape and was nearly missed by the forecast fix above: its trigger-id allow-list (`^t_open`, `^t_close`, `^t_shading_start`, `^t_shading_end`, `^t_calendar_event`) matched neither `t_recovery` nor a resumed run. For calendar-controlled users the recovery therefore ran without `calendar_open_start`/`calendar_close_start`: the calendar clauses of `is_daytime_phase`/`is_evening_phase` rendered false, `recovered_base` silently fell back to the stale helper (the orphan-audit row "missed calendar opening/closing → repaired by `recovered_base`" was dead code for exactly these users), and `recovered_due`/`recovered_arm` lost the window-start deferral (Bug Pattern L family). Fix: the gate's OR gets `trigger.id == 't_recovery' or automation_resumed`, mirroring the forecast gate. Tests: `test_calendar_events_are_loaded_for_the_recovery`, `test_calendar_events_are_loaded_on_a_resumed_run_claimed_by_any_trigger`.

**Rule (the recurring shape):** whenever a new code path consumes `shading_start_warranted` — or any variable that depends on the forecast **or on the parsed calendar events** — check *which trigger ids can reach it*. A trigger-id allow-list upstream of a value-based consumer breaks silently every time the set of reaching triggers grows. `tests/test_restart_recovery.py::TestRecoveryTriggers::test_forecast_is_loaded_on_a_resumed_run_claimed_by_any_trigger` pins the resumed-run case.

---

### Bug Pattern U: Shading start skipped when cover sits below the shading position (Issue #530)

**Symptom:** Shading conditions are met *before* the opening time, so at opening time the cover is still fully closed (position `0`). The opening handler correctly defers to `t_shading_start_execution` (Bug Pattern R), but the execution then does nothing: no drive, no helper write, `shd` stays `0`, `pnd` stays `'beg'`. The cover hangs closed all morning and the slats never tilt into the shading angle. Trace shows the execution reaching the inner drive `choose` with **all** branches false (`Consider lockout` / `Start Shading` / `Save shading state for the future`), then falling off the end with no `stop`.

**Cause:** The "Start Shading" branch position guard (line ~5437) only allowed driving *downward* to the shading position: `current_above_shading` (and, for tilt covers, `current_above_shading or current_position == shading_position`). With `shading_position` above `close_position` (e.g. `3` vs `0`), a fully-closed cover is **below** the shading position → `current_above_shading` is false and `current_position != shading_position` → the guard fails. "Consider lockout" needs an open window (false here) and "Save shading state for the future" needs `effective_state == 'cls'` — but after the opening trigger set `bas: 'opn'`, `effective_state == 'opn'` (shading not yet active, `shd == 0`). All three branches miss → dead zone.

**Fix:** Add a third alternative to the "Start Shading" position-check OR: drive when the cover is **below** the shading position **and** the base state wants it open (so shading must cap an otherwise-open cover by *raising* it to the shading position):
```yaml
- and:
    - "{{ position_comparisons.current_below_shading }}"
    - "{{ effective_state == 'opn' }}"
```
The `effective_state == 'opn'` gate is essential: when `effective_state == 'cls'` (base closed, e.g. overnight) the cover must stay closed and "Save shading state for the future" stores the intent without driving — do **not** raise the cover at night. This mirrors the opening handler's "Shading detected. Move to shading position" branch, which already drives from any direction via `not in_shading_position`.

---

### Bug Pattern V: "Shade only once per day" never blocks for users who don't touch the cover by hand

**Symptom:** With `prevent_shading_multiple_times` enabled, the cover still shades multiple times a day. After the morning shading ends (sun leaves the facade, cover returns to open), the afternoon shading conditions re-trigger and the cover shades **again**. The repeated shading-end movements also make the cover appear to *open* multiple times (shade → open → shade → open).

**Cause:** The once-per-day guard was

```jinja2
prevent_flags.shading_multiple_times and ((now().day != helper_ts_shade|timestamp_custom('%-d')|int) or helper_ts_man <= helper_ts_shade)
```

The second OR-clause `helper_ts_man <= helper_ts_shade` ("no manual change happened after the last shading") is **always true** when the user never moves the cover by hand, because `ts.man` defaults to `0` and `0 <= ts.shd` holds for any non-zero `ts.shd`. The day-check is therefore short-circuited and the guard never blocks a second shading. The clause was originally added for the opening/closing guards to handle `ts.opn`/`ts.cls` being polluted by non-driving base-state syncs (Issue #311) — but for shading it only disables the feature.

**Fix:** Drop the manual clause for shading and make the guard purely calendar-based, comparing the **full date** (not just day-of-month, which collapsed across months and treated a fresh `ts.shd == 0` as "day 1"):

```jinja2
prevent_flags.shading_multiple_times and now().strftime('%Y-%m-%d') != helper_ts_shade | timestamp_custom('%Y-%m-%d')
```

The `t_shading_start_execution` bypass (third OR-clause) is kept so an already-armed pending can still execute. Manual override is still respected via the separate `not (helper_state_manual and override_flags.shading)` gate.

**`ts.shd` is the only consumer of this guard, and it is not polluted like `ts.opn`/`ts.cls`** — it changes only on a real `shd` 0↔1 transition (Invariant 8). The opening/closing guards **keep the manual clause** because their timestamps *are* polluted by non-driving syncs, so removing the clause there would reintroduce Issue #311. The user-reported "opening multiple times" symptom is a side-effect of the shading loop, not an independent opening bug.

**The date compare in the opening guard was fixed separately.** It used `now().day != helper_ts_open | timestamp_custom('%-d') | int` — a **day-of-month** compare, which collapses across months: a `ts.opn` from exactly one month ago reads as "already opened today" and suppresses the opening. It now compares the full date (`'%Y-%m-%d'`), like the shading guard. This is orthogonal to the manual clause, which stays. The **closing** guard needs no fix — it compares `helper_ts_close < today_at(time_down_early_today)`, which is already date-safe.

**The midnight reset (BRANCH 11) no longer stamps `ts.shd` at all (CCA 2026.07.14 V2).** The original reasoning — "the reset fires at 23:55 the *same* day, so its stamp can never block the next day" — held for the trigger but not for the **write**: the branch sleeps a random 0–60 s, and with `mode: queued` a long run ahead of it (a drive delay can be 10 minutes) delays the write further. A write that slips past midnight stamps the *new* day and the full-date guard then blocks the **whole following day's** shading — the old CHANGELOG #365 failure through the back door. The stamp was never load-bearing: omitting it leaves `ts.shd` at the same-day stamp of the last real `shd` transition, so the guard decides identically on the happy path. Pinned by `tests/test_midnight_reset_missed.py::TestMidnightResetDoesNotStampTsShd`.

---

### Bug Pattern W: Shading-tilt adjustment ignores resident `allow_shade`

**Symptom:** With `resident_allow_shading` **unset** ("Allow sun protection when resident is still present" disabled) and a resident present, the cover still tilts its slats into the shading position. The helper shows `shd=1` and `res=1` but the cover visibly enters shading mode despite the resident block.

**Cause:** When the shading-start conditions are met while a resident is present, the execution handler's "Save shading state for the future" branch (gated by `not resident_flags.allow_shade`) stores the intent — `shd: 1`, `pnd: 'non'`, no drive. This makes `helper_state_is_shaded` true. A subsequent `t_shading_tilt_*` trigger then enters the "Check for shading tilt" branch, which gated on `is_shading_enabled`, `helper_state_is_shaded`, tilt-possible, `auto_shading_tilt_condition`, `force_allows_shade`, window-closed and manual-override — but **not** on `resident_flags.allow_shade`. So `*tilt_move_action` drove the slats into the shading angle while the resident was present.

**Fix:** Add `- "{{ resident_flags.allow_shade }}"` to the "Check for shading tilt" branch conditions, matching every other shading-drive branch (start execution #5459, shading-end #5680, resident-leaving SHADED #6303, force-recovery SHADING #6947, and the inline equivalent in "Window closed - Return to shading" #6123).

**Rule:** Every branch that physically moves the cover (position *or* tilt) into the shading position must gate on `resident_flags.allow_shade`. The shading-tilt adjustment is a shading movement, not an exception.

---

### Bug Pattern X: Closing handler re-drives ventilation on every closing trigger (Issue #538)

**Symptom:** The cover is in the ventilation position because the window is tilted. A subsequent closing trigger — typically the sun-based `t_close_5`, which fires repeatedly through the evening closing window — re-drives the cover to the ventilation position again (`set_cover_position` + `set_cover_tilt_position`) instead of leaving it alone. The user sees the cover "override the ventilation position" and end in an undefined position on every trigger.

**Cause:** The close handler's "Window tilted. No lockout. Move to ventilation position instead of closing" branch (line ~5197) drove **unconditionally** whenever `force_allows_ventilate` was true:

```yaml
- if: "{{ force_allows_ventilate }}"
  then: ...drive position + tilt...
```

The close handler already has an idempotent "Already in close position - only update base state" branch, but had **no** equivalent guard for the ventilation case. The contact handler's ventilation-start branches (line ~6288 / ~6417) already used the correct guard. This was an asymmetry, not a deliberate design.

**Fix:** Mirror the contact handler — gate the drive (and the `man: 0` reset) on `(effective_state != 'vnt' or not in_ventilate_position)` in the `if:`, per Invariant 1 (position check in the drive guard, not the branch conditions). The `*helper_update` still always runs:

```yaml
man: "{{ 0 if force_allows_ventilate and (effective_state != 'vnt' or not in_ventilate_position) else helper_json.man | default(0) | int }}"
if: "{{ force_allows_ventilate and (effective_state != 'vnt' or not in_ventilate_position) }}"
```

This also fixes an incidental Invariant 7 violation (the old `man: 0` fired even when no drive happened).

**Config caveat (not solvable by the blueprint alone):** On tilt/venetian covers the tilt movement changes the reported `current_position`, so the cover may rest at a position several points away from the configured `ventilate_position` (Issue #538: commanded position `6` + tilt `100` → reported position `10`). With a tight `position_tolerance` (e.g. `1`), `in_ventilate_position` stays `false`, so even the new guard keeps re-driving. The user must raise `position_tolerance` (or adjust `ventilate_position`) so the cover's resting position is recognized as "in ventilation position". The blueprint guard removes the *redundant* re-drive only once the cover is recognizable as vented.

---

### Bug Pattern Y: Manual move to the reset position swallowed when no override is active (Issue #546)

**Symptom:** With *"Reset in position"* enabled (`reset_override_config` contains `reset_in_position`, e.g. `reset_override_position = 100`), the user manually moves the cover to the reset position while CCA is in **automatic** mode (`man == 0`). The helper never records a manual change (`man` stays `0`, `ts.man` unchanged). A later event — typically closing a tilted window — then drives the cover to the scheduled/`effective_state` position instead of holding the position the user just set by hand. The user reports "I opened the cover manually but it did not change the helper" and "the cover closes when I close the window".

**Cause:** The manual-detection branch ("Checking for manual position changes") condition

```yaml
- "{{ not (trigger.id == 't_manual_position' and in_reset_override_position) }}"
```

suppressed **every** manual position trigger fired while the cover is within tolerance of the reset position — regardless of `man`. But the matching reset trigger `t_reset_position` (line ~3941) only fires when `helper.man | int == 1`. This asymmetry creates a dead zone: when `man == 0`, a manual move to the reset position is **neither** recorded as a manual change (suppressed by the condition) **nor** cleared by a reset (`t_reset_position` needs `man == 1`). The move is lost, the base state is never synced, and `effective_state` continues to reflect the old schedule.

**Fix:** Gate the suppression on `helper_state_manual`, matching the `t_reset_position` precondition:

```yaml
- "{{ not (trigger.id == 't_manual_position' and in_reset_override_position and helper_state_manual) }}"
```

- `man == 1` + move to reset position → still suppressed. This is the *"reopen to the reset position to resume automatic control"* gesture (the feature's intent, #506): detection stays quiet and `t_reset_position` clears the override after the dwell time. **Unchanged.**
- `man == 0` + move to reset position → now detected as a normal manual change. The base state is synced (directly via the "Manual: opened/closed" sub-branch, or — when the open position is not recognized because the relevant `auto_*` is disabled — via the reset handler's "restore OPEN/CLOSE base state" after the dwell). Subsequent events then follow the correct `effective_state`.

**Rule:** A manual-detection suppression that exists only to mute a *reset gesture* must carry the same precondition as the reset it is muting. Suppressing detection when there is nothing to reset silently discards a real manual change.

**Config note:** Choosing `reset_override_position = 100` (= open) intentionally means "moving the cover fully open resumes automatic control" — so once the override has been cleared the cover follows the schedule again. The fix only ensures the *first* manual move (while `man == 0`) is no longer dropped; it does not turn the open position into a permanent manual hold.

---

### Bug Pattern Z: Tilted-window ventilation never triggers in a schedule-less setup (Issue #553)

**Symptom:** In a **shading-only** setup with no open/close schedule (`auto_options` has neither `auto_up_enabled` nor `auto_down_enabled`, `time_control: time_control_disabled`), a tilted or opened window **never moves a closed cover to the ventilation position**. This worked in v5. The helper shows `bas: 'opn'`, `win: 'tlt'`, and the cover sits at the closed position with no movement. The contact handler's "Window tilted - No drive, sync helper window state" branch (which gates on `effective_state == 'opn'`) catches the event and only syncs `win: 'tlt'` — the drive branch ("Window tilted - Partial ventilation", gated on `effective_state != 'opn'`) is skipped.

**Cause:** `bas` initializes to `'opn'` in every init path (fresh init, v6 parse fallback `default('opn')`, v5 migration unless the v5 state was explicitly `close`) and is **only ever** switched to `'cls'` by the scheduled close handler (`t_close_*`, which needs `auto_down_enabled` + a time/calendar source). Without a schedule, `bas` stays `'opn'` forever → `base_target == 'opn'` → the VENT floor condition (`base_target != 'opn'`) is never true → a closed cover ignores a tilted window. The `2026.05.24` changelog had documented "remove the time schedule (so `bas` never reaches `opn`)" as the way to restore v5 behavior — but removing the schedule does **not** make `bas` non-`opn`, so that workaround never worked.

**Fix:** Gate the BASE=OPN-beats-VENT rule on whether an opening automation actually exists. New `trigger_variables` flag (the `not is_time_control_disabled` clause shipped here was too narrow — see Bug Pattern AL for the current definition):

```yaml
is_opening_scheduled: "{{ is_up_enabled and not is_time_control_disabled }}"
```

In `effective_state`, replace the VENT floor condition:

```jinja2
{% set base_open_scheduled = base_target == 'opn' and is_opening_scheduled %}
{% if w == 'tlt' and allow_vent and not base_open_scheduled %}
  vnt
{% else %}
  {{ base_target }}
{% endif %}
```

This is **surgical** — it only changes the VENT-floor decision. When the window is **not** tilted, `effective_state` still returns `'opn'` for `bas == 'opn'`, so shading-end (gated on `effective_state != 'cls'`), the contact "return to open" branch, and every other base=opn consumer are unaffected. Scheduled setups (`is_opening_scheduled == true`) keep the `2026.05.24` BASE=OPN-beats-VENT behavior unchanged.

**Why not Option 1 (treat `bas` as `'cls'` for the whole cascade):** That was the maintainer's originally-documented intent, but making `effective_state` return `'cls'`/`'vnt'` wholesale breaks the shading-end handler, whose branch gate is `effective_state != 'cls'` — shading would never end. The VENT floor must be the *only* thing affected; gating just that line is the correct minimal change.

---

### Bug Pattern AA: Global trigger gate makes the #554 end-pending cancel unreachable (Issue #554)

**Symptom:** Shading-end is pending (`pnd == 'end'`). During the end waiting time the shading conditions are met again (sun comes back), so per the documented guarantee — *"Shading ends if one of the conditions is not fulfilled for the entire waiting time"* — the pending end should be canceled. The dedicated cancel branch ("Shading re-detected. Cancel pending shading end", added for #554) exists in the actions, but never runs: no trace is even recorded for the `t_shading_start_pending_*` trigger. If the end conditions happen to be met again at `t_shading_end_execution` time, shading ends regardless of the interruption.

**Cause:** The global trigger gate (conditions block, "GLOBAL CONDITIONS") suppresses `t_shading_start_pending_[1-6]` whenever the helper shows `shd == 1` — its purpose is noise suppression (don't re-run the automation for start triggers while shading is already active). But during an end-pending, `shd` is *always* still `1` (shading stays active until the end executes). The gate therefore stopped the automation before the actions ran, making the #554 cancel branch dead code in exactly the scenario it was written for.

**Fix:** The gate lets `t_shading_start_pending_[1-6]` through when the helper shows an armed end-pending (`"pnd"\s*:\s*"end"` regex — value `"end"` is unique to `pnd`, no other field can hold it):

```jinja2
{% set is_shaded = helper not in invalid_states and helper | regex_search('"shd"\s*:\s*1\s*[,}]') %}
{% set is_end_pending = helper not in invalid_states and helper | regex_search('"pnd"\s*:\s*"end"') %}
{{ not is_shaded or is_end_pending }}
```

Additionally, the "Check for shading start" branch entry OR ("Check the helper status or the target status") gets `helper_state_pending_end` as a third alternative — matching the two escape hatches the earlier #554 fixes already added to the position-check OR and the once-per-day OR — so the cancel is also reachable while the window is open/tilted (an end-pending can arm with the window open; the contact handler holds lockout/vent, but the interruption must still cancel the pending).

**Rule:** A fix in the actions is only real once every gate *upstream* of it (trigger `enabled`, trigger `for`, **global conditions**, branch conditions) provably lets the triggering event through in the exact scenario being fixed. When adding an action branch keyed to a trigger id, always re-check the global trigger gate for that id.

**Deliberate asymmetry (reporter's "FWIW"):** The gate still suppresses `t_shading_end_pending_[1-7]` while shading is inactive (`shd == 0`), even though a shading-**start** pending may be armed. This is intentional: the start side is documented as a *retry loop* ("After the waiting time expires, the automation re-evaluates ALL configured conditions. Only if they are still valid at this point, the cover actually moves") — momentary interruptions during the start wait are tolerated by design, and the execution re-check plus `shading_start_max_duration` budget already handle unmet conditions. Canceling a start-pending on an end trigger would also break the pre-window arming flows (Bug Patterns L/S/R). Do not "harmonize" the end side of the gate.

**Known residual window of that asymmetry (documented 2026.07.14, accepted):** a shading-**end**
condition whose false→true edge falls into the start-pending window is *consumed*, not deferred.
Between the arming write (`shd` still `0`) and the execution write (`shd: 1`) — potentially the
whole waiting time — every `t_shading_end_pending_*` event is dropped by the gate at trigger
time; once `shd` is `1`, that trigger's template is already true, so it never produces a new
edge. The exposure is smaller than it looks, which is why this is documented rather than fixed:

- When the crossing sensor also feeds a **start** condition (the usual case — hysteresis pairs),
  the execution re-check sees the start condition fail and retries/aborts instead of shading.
- The sun-position end triggers (`t_shading_end_pending_5`/`_7`) are enabled for every setup
  with a sun sensor and produce a **fresh edge** when the sun leaves the azimuth/elevation
  range — so an end swallowed this way ends *late* (at sun exit), not never.
- The 23:55 reset (BRANCH 11) is the backstop for everything else.

The residual loss case is an **end-only** sensor (e.g. forecast temperature configured only as
an end condition) crossing during the pending window in a setup whose other end triggers never
re-fire that day. Do **not** close it by letting end triggers through while a start pending is
armed — that is exactly the "harmonization" the paragraph above forbids (it cancels the retry
loop and breaks the pre-window arming flows L/S/R). If it ever needs fixing, the shape would be
an end-condition re-check at the *start execution* (after `shd: 1` is decided), not a gate change.

---

### Bug Pattern AB: Opening deferred to Shading End although shading is inactive (Issue #565)

**Symptom:** The cover sits at the shading position at opening time while the helper shows `shd: 0` and `pnd: 'non'` (e.g. the user moved it there manually, or positions happen to coincide). The opening trigger fires, the trace ends with `"Open time: In shading position, base state updated (movement via Shading End)"`, and the cover never opens — it stays at the shading position for the rest of the day.

**Cause:** The "Normal opening of the cover" branch guarded only on `not in_shading_position` — the physical position alone — assuming that a cover at the shading position is *shaded* and the Shading End flow will open it later. Execution fell through to the default branch, which only sets `bas: 'opn'` and defers the movement. But with `shd == 0` that handoff is impossible: the global trigger gate suppresses all `t_shading_end_pending_[1-7]` triggers unless the helper contains `"shd":1` — the gate upstream makes the deferral dead code (Bug Pattern AA territory).

**Fix:** Gate the deferral on the helper's actual shading state:

```yaml
- "{{ not in_shading_position or not helper_state_shade }}"
```

With `shd == 1` + in shading position, the default branch still defers to Shading End (whose triggers pass the global gate because `shd == 1` — the handoff works). With `shd == 0`, "Normal opening" fires and drives the cover open. This also covers the stale-pending case (`pnd == 'beg'`, `shd == 0`, cover at shading position, conditions no longer warranted): Bug Pattern R's fall-through now genuinely reaches the drive instead of dead-ending in the default branch.

**Rule:** A deferral to another flow must be gated on the *helper state* that makes that flow reachable, never on the physical position alone. Position says where the cover is; only the helper says *why* — and the "why" decides which flow owns the next movement (same family as the Bug Pattern AA rule: verify the receiving flow's upstream gates actually let it run).

---

### Bug Pattern AC: Force-disable recovery reads window contacts without the ventilation gate (Issue #566)

**Symptom:** Ventilation automation is disabled (`auto_ventilate_enabled` not in `auto_options` — e.g. because a defective tilt sensor permanently reports "tilted"). Shading is active, the cover sits at the shading position. A force function is turned off → the recovery drives the cover to the **ventilation position** although ventilation is disabled and the tilt sensor should be ignored entirely.

**Cause:** When the ventilation automation is disabled, the contact sensors are ignored throughout CCA — the contact triggers carry `enabled: "{{ is_ventilation_enabled and ... }}"`, the contact handler, the closing-lockout branch, the shading-end lockout/ventilation branches and the resident-handler ventilation branches all gate on `is_ventilation_enabled`. The force-disable recovery branches, however, read `states(contact_window_opened)` / `states(contact_window_tilted)` **directly** and bypassed that gate: the "return to VENTILATION (window tilted)" branch drove to the ventilation position, and the negative window checks in "return to CLOSE / SHADING / OPEN (base=opn)" blocked those branches on a (stuck) contact. Only the sibling "return to OPEN (window open — lockout)" branch already checked `is_ventilation_enabled`.

**Fix:** Apply the gate to every direct sensor read in the recovery `choose`:

- "return to VENTILATION (window tilted)": add `- "{{ is_ventilation_enabled }}"` (mirrors the lockout recovery branch).
- "return to CLOSE (base=cls)", "return to SHADING", "return to OPEN (base=opn)": scope the window-contact exclusions, e.g. `not (is_ventilation_enabled and contact_window_tilted != [] and states(contact_window_tilted) in ['true', 'on'])`.

With ventilation disabled, the recovery now falls through to the correct shading/open/close target instead of driving to ventilation or dead-ending in the recovery `default:` (which would clear `frc` without any movement).

**Second recurrence (CCA 2026.07.13 V6) — the restart recovery, and the scoping moved into the cascades.** The restart-recovery gate's `recovered_window` read the contacts unscoped too, and unlike `effective_state` (whose `'vnt'`/`'lock'` consumers all gate in their branches) it **drives directly** on the result: with ventilation disabled and a stuck contact, every restart *and every save of the automation* drove the cover to the ventilation position — or to open via `'lock'`, which additionally overrules a manual override (`recovery_allowed` passes on `recovered_state == 'lock'`). Ironically, `lockout_blocks_shading` three lines below was already scoped. The fix applies the AC rule at the *source*: the live-contact reads inside **both** `effective_state` and `recovered_window` are scoped to `is_ventilation_enabled` (one commit, Invariant 13), so `w` is `'cls'` while ventilation is disabled and contacts are configured. The no-contacts helper fallback (`h.win`) is untouched — a user driving `win` via the helper alone keeps working. Tests: `TestRecoveredWindow::test_ventilation_disabled_means_the_contacts_do_not_exist`, plus three vent-disabled rows in `TestCascadeParity`.

**Rule:** Every direct `states(contact_window_opened/tilted)` read in a branch condition or drive guard must be scoped to `is_ventilation_enabled` — since CCA 2026.07.13 V6 the cascade-internal `w` derivations (`effective_state`, `recovered_window`) enforce this at the source. When the ventilation automation is disabled, the window contacts do not exist as far as CCA is concerned — this includes lockout (the trigger gate already treats it that way). Note this is about the feature toggle `auto_ventilate_enabled`, not the resident flag `resident_allow_ventilation` (Invariant 6 remains untouched).

---

### Bug Pattern AD: Calendar title gate on `message` attribute misses concurrent events (Issue #568)

**Symptom:** One calendar carries two events with **different titles but the same start time** (e.g. "Open Cover" and "Open Schlafraume", both Saturday 08:30, driving different CCA instances). Only one automation runs; the other is stopped by the global conditions (trace: "Stopped because a condition failed", runtime ~0.04 s) and its cover never opens.

**Cause:** The global conditions gated `t_calendar_event_*` triggers on `state_attr(calendar_entity, 'message')` matching `calendar_open_title` or `calendar_close_title`. A calendar entity's `message`/`start_time`/`end_time` attributes only ever expose a **single** (current-or-next) event — with two simultaneous events, HA picks one and the other is invisible. The automation whose title matched the hidden event was suppressed. The same attribute-based gate also failed at an event **end** when no upcoming event exists (`message` is `none`).

**Fix:** Remove the title check from the global conditions entirely — a condition context cannot call `calendar.get_events`, and the `message` attribute is structurally unable to represent concurrent events. The precise check lives in the actions instead ("Calendar trigger relevance check", directly before the main `choose:`): after `calendar.get_events` has loaded today's events and the variables block has parsed them per title (`calendar_open_event`/`calendar_close_event` → `calendar_open_start/end`, `calendar_close_start/end`), the step `stop`s calendar-triggered runs when **none** of the automation's own parsed event boundaries caused the state transition:

```jinja2
{% set flip_to = as_timestamp(trigger.to_state.last_changed) %}
{% set flip_from = as_timestamp(trigger.from_state.last_changed) if trigger.from_state is not none else 0 %}
boundary is relevant iff flip_from < boundary <= flip_to + 60
```

The interval `(flip_from, flip_to + 60]` — previous on/off flip to current flip plus tolerance — is used instead of a plain "boundary == now" comparison for two reasons: `mode: queued` can delay execution well past the trigger (so `now()` is unusable), and a lagging calendar integration can flip the entity state after the nominal event boundary (so a tight tolerance around `flip_to` alone could false-negative). The asymmetry is deliberate: a false **pass** merely costs an idempotent no-op run (the opening/closing branches still gate on `is_opening_phase`/`is_closing_phase` etc.), while a false **stop** silently loses an open/close — so the gate is generous.

**Why not `trigger: calendar` platform triggers (which expose `trigger.calendar_event.summary`):** `calendar_entity` defaults to `[]`, and the calendar trigger schema (`cv.entity_id`) rejects a list — the blueprint would fail validation for every user without a calendar. `enabled:` does not skip schema validation. The state triggers (`to: "on"` / `to: "off"`) must stay.

**Known limitation (unchanged):** the state trigger only fires on real `off`↔`on` transitions of the calendar entity. If a matching event starts while another event is already running (overlap, not same-start), the entity stays `on` and **no trigger fires at all** — that is a trigger-level gap this action gate cannot close.

**Rule:** Never gate calendar-trigger relevance on the calendar entity's state attributes — they show one event only. Relevance must be decided against the `calendar.get_events` result (same family as Bug Pattern AA: the gate upstream must provably let the event through in the scenario being handled).

---

### Bug Pattern AE: Shading start ignores the ventilation floor when the window is already tilted

**Symptom:** With a window **tilted** (not fully open) and `shading_position` below `ventilate_position` (e.g. shading 30, vent 50), the cover drops to the **shading position (30)** when shading starts — below the ventilation floor. It should hold the **ventilation position (50)** while the window is tilted and only move to the shading position once the window is closed.

**Cause:** The shading-start execution had no VENT-floor handling. Its only drive branch, "Start Shading", drove straight to `shading_position` regardless of a tilted window. `effective_state` correctly returns `'vnt'` for tilted + shading (VENT prio 4 > SHADING prio 6), and the **contact handler** holds the floor for the reverse order (shade first, then tilt) — but the shading-start path did not. So the bug only manifested in the order **tilt first, then shading starts** (the reverse order was already correct).

**Fix:** New branch "Shading start - hold ventilation floor (window tilted)" placed **before** "Start Shading" in the execution `choose`. It fires when the window is tilted (and not opened — Invariant 5), ventilation is enabled and force/resident-allowed, shading is resident-allowed, and `position_comparisons.shading_below_ventilate` holds. It drives to `ventilate_position` / `ventilate_tilt_position`, sets `shd: 1`, `win: 'tlt'`, clears pending (`pnd: 'non'`, `ts.due: 0`, `ts.arm: 0`), and sets `man: 0` only when it actually drives (`not in_ventilate_position`, Invariant 7). When the window later closes, the contact handler's "Window closed - Return to shading" lowers the cover to the real shading position.

**Scope:** Only the common case `shading_position` below `ventilate_position` is floored (`position_comparisons.shading_below_ventilate`). When `shading_position` is at/above `ventilate_position` the floor does not bind and "Start Shading" drives to the shading position as before. The `lockout_tilted_shading_start` option still takes precedence (treats a tilted window like a fully-open one → cover stays open during shading). The latent `effective_state == 'vnt'` divergence for the rare `shading_position` *above* `ventilate_position` config is intentionally left untouched (out of scope, not the reported case).

---

### Bug Pattern AF: Unconfigured status helper kills variable rendering before the friendly config check

**Symptom:** With the mandatory `cover_status_helper` not configured, every run of the automation dies at trigger time with `Error rendering variables: TypeError: cannot use 'list' as a dict key (unhashable type: 'list')` (Python ≥ 3.13 wording of "unhashable type"). The actions' "MANDATORY HELPER VALIDATION" block — which exists precisely to log a clear "Cover Status Helper is required but not configured" error and stop — never runs, because the top-level `variables:` block is rendered *before* the actions and aborts the run.

**Cause:** `helper_json` called `states(cover_status_helper)` without a `!= []` guard. The input's `default: []` makes the argument a list, and `hass.states.get([])` fails on the dict lookup. Every other state read in the `variables:` block already carried the `x != [] and states(x)` guard — `helper_json` was the single unguarded one. The same unguarded read existed in trigger templates (`t_shading_start/end_execution`, `t_shading_tilt_*`, `t_reset_timeout`, `t_reset_position`), the global conditions (shading pending gate), and the v5→v6 migration check in the actions.

**Fix:** Guard every reachable `states(cover_status_helper)`: in `helper_json` and the global-conditions gate via `... if cover_status_helper != [] else 'unavailable'` (falls through to the existing invalid-state handling → fresh default JSON), in the migration check via a preceding `{{ cover_status_helper != [] }}` condition, and in the helper-reading triggers via `and cover_status_helper != []` in their `enabled:`. With no helper configured the run now reaches the mandatory validation, logs the friendly error, and stops.

**Rule:** Every `states(x)` / `state_attr(x, ...)` on an input whose `default` is `[]` must be guarded with `x != []` (short-circuit) — in *every* context: `variables:`, trigger `value_template`s, global conditions, and action conditions. This is the same upstream-gate family as Bug Pattern AA: a user-facing validation in the actions is dead code if variable rendering upstream can throw first.

---

### Bug Pattern AG: Opening deferred into shading while the lockout window is open (2026.06.28 V3 regression, forum report)

**Symptom:** The lockout window is **fully open** (or **tilted** with `lockout_tilted_shading_start` enabled) at the scheduled opening time and the shading conditions are met. The cover does not open — it stays at its current position (e.g. still closed after a force function or restart) for the rest of the morning. The trace ends with `"Opening: Shading pending armed"` (or `"Opening skipped: Shading start pending"`), and the later shading execution ends with `"Shading Start skipped: Lockout enabled"`.

**Cause:** The opening handler has two branches that hand the movement over to the shading execution instead of opening: "Opening skipped: Shading start pending" (defer, Bug Pattern R) and "Opening: Shading warranted, arm pending" (#555, new in `2026.06.28 V3`). Neither checked the window contacts. But the shading execution's "Consider lockout protection when shading starts" branch only **stores** the intent (`shd: 1`, `win: 'opn'`) and stops — it never drives the cover. So with the lockout active, the receiving flow can never satisfy the opening obligation: the handoff dead-ends and the cover stays below the open position although `effective_state == 'lock'` demands it. The #555 branch made this common (it fires on every sunny morning with an open window at opening time); the defer branch had the same gap since #514 for a pending armed pre-window.

**Fix:** Both branches gate on the same lockout-window check as the execution's "Consider lockout" branch (scoped to `is_ventilation_enabled` per Bug Pattern AC):

```yaml
- "{{ not (is_ventilation_enabled and ((contact_window_opened != [] and states(contact_window_opened) in ['true', 'on']) or (lockout_tilted_when_shading_starts and contact_window_tilted != [] and states(contact_window_tilted) in ['true', 'on']))) }}"
```

When the lockout applies, execution falls through to "Normal opening", which drives the cover open (a no-op via the `cover_move_action` tolerance guard when the contact handler already opened it) and clears `pnd`/`ts.due`/`ts.arm`. A plain tilted window **without** the `lockout_tilted_shading_start` option still arms/defers — the execution then holds the ventilation floor (Bug Pattern AE) or shades, as designed. Trade-off: the stored-shading-intent handoff (window closes later → "Return to shading") is not established in the lockout case; shading starts when the next shading trigger re-fires. That restores the pre-`2026.06.28 V3` behavior — lockout safety beats remembered shading.

**Rule:** A handoff into another flow must be gated on what the receiving flow can actually *do* in that scenario — the shading execution's lockout branch stops without movement, so it can never fulfill a deferred opening. Same family as Bug Pattern AB (gate deferrals on the receiving flow's reachability) and AA (verify the receiving flow's upstream gates).

---

---

### Bug Pattern AH: Time-control disable path unreachable through the UI (Issue #544)

**Symptom:** Unchecking the *"⏲️ Time Control"* checkbox in `auto_options` has no effect for installations created after the options consolidation (~2026.05). Brightness-/sun-only setups stay gated by the default Early/Late time windows; there is no way to disable time control through the UI.

**Cause:** `is_time_control_disabled` required **both** `'time_control_enabled' not in auto_options` **and** `'time_control_disabled' in time_control` — but the `time_control` selector no longer offered a `disabled` option, so the second clause could never become true for new installs. The state "`time_control_enabled` missing from `auto_options`" is ambiguous by itself: it means either "legacy pre-consolidation install (keep time control)" or "new user deliberately unchecked (wants it off)" — the checkbox alone cannot be made authoritative without silently disabling time control for every legacy install.

**Fix (maintainer decision — deliberate breaking change):** The `time_control_enabled` checkbox in `auto_options` is the single authoritative switch; the legacy `time_control` selector only picks the *source* (time fields vs calendar) and its old `time_control_disabled` value is no longer evaluated:

```yaml
is_time_control_disabled: "{{ 'time_control_enabled' not in auto_options }}"
is_time_field_enabled: "{{ 'time_control_enabled' in auto_options and 'time_control_input' in time_control }}"
is_calendar_enabled: "{{ 'time_control_enabled' in auto_options and 'time_control_calendar' in time_control and calendar_entity != [] }}"
```

Gating `is_time_field_enabled`/`is_calendar_enabled` on the checkbox is essential: the time/calendar triggers carry `enabled: "{{ is_time_field_enabled }}"` / `is_calendar_enabled`, so without the gate the Late trigger would still fire while time control is "disabled". The checkbox stays in the `default:` list (new installs get the Late safety net by default). The `time_control_disabled` option is **not** offered in the dropdown — one switch, one mechanism. Pre-consolidation configs that had chosen `time_control_disabled` remain disabled (checkbox absent), matching their original intent. The config validator (`docs/validator/validator.js`) mirrors the logic and warns about the breaking change.

**Accepted breakage:** Pre-consolidation installs with `time_control_input`/`time_control_calendar` (no `time_control_enabled` stored) silently lose time control after the update until the automation is re-saved with the checkbox enabled — for pure time-schedule users this stops opening/closing entirely. The ambiguity ("value missing = legacy install or deliberate uncheck") cannot be resolved from stored data; the maintainer chose the clean end state over keeping a permanently ambiguous hybrid clause, with prominent CHANGELOG/FAQ communication instead of silent compat.

**Rule:** When one UI input must be authoritative and the stored data cannot distinguish legacy absence from deliberate absence, do not encode the ambiguity into a hybrid AND-clause forever — pick the authoritative input, document the one-time breakage loudly, and make every dependent flag (`is_time_field_enabled`, `is_calendar_enabled`, trigger `enabled:` gates) follow the same single switch.

---

### Bug Pattern AI: Unavailable cover corrupts the helper via the 101 position sentinel

**Symptom:** After a HA restart or an outage of the cover integration, CCA keeps reacting to time/sun/contact triggers while the cover itself is `unavailable`. Symptoms vary: movements are silently skipped (the cover is mistaken for "already open"), runs abort mid-sequence with `HomeAssistantError: Entity cover.x is not available` so the helper is never written, and — the worst case — a helper write derived from the bogus position **overwrites a still-correct state**, e.g. an active shading (`shd: 1`) from before the restart.

**Cause:** The global conditions only validated the **triggering** entity (`trigger.to_state.state not in invalid_states`). The cover was never checked. With the cover unavailable, `state_attr(blind, 'current_position')` is `None` and `current_position` falls back to the `101` sentinel — which is not a neutral value: `|101 − open_position(100)| ≤ position_tolerance(5)` makes `in_open_position` **true**. So the automation reasons about a cover that "is open" and persists conclusions drawn from a phantom position.

**Fix:** A global condition over `critical_entities` — every entity whose invalid state would make the cascade compute a *wrong* target must be usable, not just the trigger source. Use the shared `invalid_states` constant, **not** `!= 'unavailable'`: an `unknown` entity (restart before restore, deleted entity) is just as broken. Paired with the `t_recovery` trigger set + the recovery gate, because a blocked automation silently loses every event of the outage window. See the design decision *"Restart / outage handling: block on state-critical entities, recover via `t_recovery`"* for the entity list, the group semantics, why condition-only sensors are excluded, and why the check is on the **state** and not on the position sentinel.

**Rule:** A guard that stops the automation from acting on bad data must be paired with a way to *catch up* once the data is good again — otherwise the guard converts a corruption bug into a silent-miss bug. Blocking is only half a fix; the recovery path is the other half. And the guard must cover *every* input the cascade reads, not just the one that surfaced the bug: a dropped window contact reads as "closed" and silently disables the lockout exactly like a dropped cover reads as "open".

---

### Bug Pattern AJ: Shading-end tilt-only branch outranks lockout/ventilation and hardcodes the open tilt (Issue #583)

**Symptom:** With *"Stay shaded: Don't open cover when sun shading ends"* (`prevent_opening_after_shading_end`) **and** *"Using the ventilation position when the sun shading is ended"* (`ventilation_after_shading_end`) both enabled, a window **tilted** at shading end leaves the cover at the shading position with slats tilted to 50 — instead of moving to `ventilate_position`/`ventilate_tilt_position`. Independently, the tilt-only slat angle ignored the configured `open_tilt_position` (hardcoded `50`; the input's default is also 50, so only users who changed it noticed).

**Cause A (ordering):** "Only tilt open after shading ends" was placed **before** "Lockout protection when shading ends" and "Ventilation after shading ends" in the shading-end execution `choose:` and carries no window-contact condition — it consumed every execution run on tilt covers with the prevent flag set, swallowing the higher-cascade LOCKOUT (prio 2) and VENT (prio 4) branches (same family as Bug Pattern AA/AB: a correct branch is dead code when an earlier branch consumes its scenario).

**Cause B (hardcoding):** `target_tilt_position: 50` instead of the `open_tilt_position` input, despite the comment "Moving the cover to open tilt position".

**Fix:** Reorder the execution `choose:` to pending → lockout → ventilation → tilt-only → move-cover (cascade order), and use `{{ open_tilt_position | int }}` in the tilt-only branch. With the window closed, or ventilation not configured/enabled, the tilt-only branch still fires as before. Deliberate consequence: with both options enabled and a tilted window, the cover now *rises* from the shading to the ventilation position — VENT is a floor and outranks SHADING; "stay shaded" means "don't open fully", not "stay below the ventilation floor". Tests: `tests/test_shading_end_priority.py`.

**Rule:** Within a `choose:`, branch order must follow the priority cascade. A branch that implements a lower-cascade behavior (shading convenience) must never be placed above lockout/ventilation branches for the same trigger — and any "the remaining cases" branch must actually be reached only by the remaining cases.

**Second recurrence (Issue #608, CCA 2026.07.13 V7) — same swallow, different gate:** after the reorder, the ventilation branch could still be skipped on tilt covers whose shading position **equals** the ventilate position (venetian setups: closed/shading/ventilate all share one cover position, only the slat angle differs — the `tilt_position_tolerance` input documents this setup explicitly). At shading end the cover rests exactly *at* the ventilate position, so `current_below_ventilate` is false and the equality alternative was gated behind `ventilation_flags.if_lower_enabled` — the branch fell through to the tilt-only branch again, which now tilted the slats to `open_tilt_position` (the very value the AJ fix introduced) instead of `ventilate_tilt_position`. The contact handler's tilted branch had a third alternative for exactly this case; the shading-end branch lacked it. Fix: add the same tilt-cover alternative (`is_cover_tilt_enabled_and_possible` AND at/below ventilate position AND `current_tilt_position <= ventilate_tilt_position`) to the shading-end ventilation branch's position OR. **Rule:** when two branches in different handlers implement the same cascade decision (here: "does VENT bind at this position?"), their position ORs must stay alternative-for-alternative identical — a missing alternative in one handler is a dormant swallow bug (same family as the 2026.07.12 V2 bracketing fix between these two branches).

---

### Bug Pattern AK: Pending execution path ends without a helper write → pending stuck until midnight

**Symptom:** A shading start (or end) never executes and never retries. The helper shows `pnd: 'beg'` (or `'end'`) with a `ts.due` in the past, and no further `t_shading_*_execution` run appears in the traces. New pending triggers are blocked (arm branches gate on `not helper_state_pending_*`). The state only clears at the 23:55 midnight reset.

**Cause:** The execution triggers are template triggers on `now() >= ts.due`. For a past `ts.due` the template stays `true` forever — there is no new FALSE→TRUE edge, so the trigger never re-fires. Any execution path that ends **without** a helper write (neither re-arm nor clear) therefore freezes the pending. Two instances found and fixed (CCA 2026.07.01):

- The shading-start drive choose (lockout / start shading / save-for-future) had **no default**. A non-tilt cover resting exactly at the shading position (neither `current_above_shading` nor `current_below_shading`), or a cover held at the ventilation floor (`effective_state == 'vnt'`, third OR-alternative requires `'opn'`), matched no branch → fall-through without helper write.
- "Move cover after shading end" wrapped its whole body in `if not prevent_flags.opening_after_shading_end` with **no else**, followed by `stop:`. With the prevent option set and tilt not possible (the tilt-only branch requires tilt), the sequence stopped without a helper write.

**Fix:** Give every drive choose inside the execution handlers a `default:` that records the state and clears the pending, and give every `if:` before a `stop:` an `else:` that clears the pending. See the "Every execution path must be terminal" rule in Invariant 8.

---

### Bug Pattern AL: The VENT floor gate reads "opening is scheduled" as "opening is *time*-scheduled"

**Symptom:** In a setup that opens the cover by **sun elevation** or **brightness** with time control switched **off** (`auto_up_enabled` + `auto_sun_enabled` / `auto_brightness_enabled`, no `time_control_enabled`), the morning opening drives the cover to the open position as expected — but tilting a window afterwards **pulls it back down** to the ventilation position. With time control enabled the identical situation keeps the cover open. The helper shows `bas: 'opn'`, `win: 'tlt'`, and the trace shows `effective_state == 'vnt'`.

**Cause:** `is_opening_scheduled` — the gate that lets BASE=OPN beat the VENT floor (Bug Pattern Z) — was `is_up_enabled and not is_time_control_disabled`. Its purpose is to tell a **real** `bas: 'opn'` (written by the opening handler) apart from the **init default** (`bas` starts at `'opn'` and only the close handler ever moves it). But `bas` reaches `'opn'` through *any* opening trigger, and time control is only two of the four sources: `t_open_4` (brightness) and `t_open_5` (sun elevation) are gated on their own feature flags alone, and the opening branch explicitly passes them through while time control is off (`is_time_control_disabled` is the first alternative of its scenario OR). So a sun-driven opening set `bas: 'opn'` legitimately, and the gate then classified it as the init default and applied the VENT floor to it.

**Fix:** Mirror the `enabled:` gates of the opening triggers instead of the time control switch:

```yaml
is_opening_scheduled: >-
  {{ is_up_enabled and (
       is_time_field_enabled or
       is_calendar_enabled or
       (is_brightness_enabled and default_brightness_sensor != []) or
       (is_sun_elevation_enabled and default_sun_sensor != [])) }}
```

The sensor-presence clauses are not cosmetic: `t_open_4` / `t_open_5` carry `enabled: "{{ is_brightness_enabled and default_brightness_sensor != [] }}"` (resp. the sun sensor), so a feature flag without its sensor enables no trigger and must not lift the floor. #553 stays fixed by construction — a shading-only setup has no `auto_up_enabled`, and `auto_up_enabled` with *every* source switched off (which has no opening trigger either, so `bas` really is stuck at its default) also still ventilates. `recovered_state` reads the same variable, so the recovery mirror follows automatically (Invariant 13).

**Rule:** A flag that asks "did an automation really write this state?" must be derived from the **triggers that write it**, not from one of the feature switches that happens to enable some of them. Whenever a new source for an existing handler is added, every "does this handler exist?" flag has to be re-derived — the same upstream/downstream mismatch as Bug Pattern AA, just in the variables instead of the gates. `tests/test_opening_schedule_gate.py` pins the flag against the real trigger `enabled:` templates so a fifth opening source cannot silently drift.

---

