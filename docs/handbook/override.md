{% raw %}
# ✋ Manual Override & Reset

[📖 CCA Handbook](index) › Blueprint section: **Manual Override**

**On this page:** [🖐️ Automatic movements blocked during Manual Override](#ignore_after_manual_config) · [🖐️ Manual movement inside the schedule window counts as the scheduled event](#manual_schedule_adoption) · [🗑️ Reset manual override](#reset_override_config) · [🔙 Return to Target State After Manual Override Reset](#auto_recover_after_manual_reset) · [🗑️ Time to reset manual override](#reset_override_time) · [🗑️ Number of minutes until reset manual override](#reset_override_timeout) · [🗑️ Position for reset manual override](#reset_override_position) · [🗑️ Dwell time at reset position (minutes)](#reset_override_position_dwell)

---

<a id="ignore_after_manual_config"></a>

## 🖐️ Automatic movements blocked during Manual Override

> 🧩 Input: `ignore_after_manual_config`

Select which automatic movements must not move the cover while a Manual Override is active.

⚠️ **Leave all four unselected and Manual Override protects nothing.** The very next relevant
automatic movement simply overrides it and clears it in the process — no separate reset needed
for that movement type. This is the correct choice if you only want CCA to *know* a manual
change happened without actually changing anything. Select a type here only if you want the
manual position to stick until an explicit reset instead.

### How the selection works

- **Selected:** the manual position wins and this type of automatic movement is blocked until the Manual Override is reset.
- **Not selected:** this automatic movement may take control even while Manual Override is active. If CCA actually dispatches the movement — through its built-in cover services or the configured [custom-only after-action pipeline](actions#custom_actions_only) — the Manual Override is cleared.

The four choices are independent: automatic opening, closing, ventilation and sun shading can each have a different policy. They govern the event that owns the movement: scheduled opening/closing, the sun-shading lifecycle, or a window-contact ventilation event. For example, you can keep a manually closed cover protected from the next scheduled opening while still allowing sun shading when the facade becomes hot.

### What continues in the background

Manual Override blocks only the selected physical movements. CCA still tracks the current opening/closing schedule, sun-shading waiting period and active state, window contacts, resident state and force functions. Resetting the override therefore reconciles the target that is valid at that moment instead of waiting for a new sensor edge or restarting an old delay. As a safety net, an explicit timeout, fixed-time or position reset also re-derives the current schedule before reconciliation; a missed or refused opening/closing event therefore cannot make the reset apply an outdated helper target.

Some configured events explicitly hand control back to CCA instead of consuming these four choices: a resident arrival/departure that has a movement configured, enabling or switching a Force position, disabling Force Pause, and disabling a Force position with automatic return enabled. They replace the older manual intent only when CCA really dispatches a movement; a state-only update or already-reached target preserves Manual Override.

For contact ventilation, **Block automatic ventilation** controls both the reaction to a tilted window and the return to the current background target when the window closes. A fully opened window is the safety exception described below.

A selected sun-shading option blocks every shading-related movement while Manual Override remains active; it does not discard the shading state. If shading starts and ends entirely during the override, no obsolete shading movement is replayed afterwards. If shading is still required when the override resets, CCA can move directly to the shading target.

The full-window lockout remains the safety exception that may overrule Manual Override when its ventilation condition permits the proactive movement. If that condition is false, CCA still records the open window and prevents later closing or sun-shading movement; it merely does not raise the cover at the moment the window opens. Enabling a Force position is also an explicit higher-priority command; Force Pause can still suppress it.

---

<a id="manual_schedule_adoption"></a>

## 🖐️ Manual movement inside the schedule window counts as the scheduled event

> 🧩 Input: `manual_schedule_adoption` · Default: nothing selected

For everyone who prefers to open or close the cover **by hand** even though a schedule is
configured ([#671](https://github.com/hvorragend/ha-blueprints/issues/671)): with this option,
a manual movement that lands in the open (or closed) position **while the matching schedule
window is running** is treated as if the scheduled event itself had happened. CCA's internal
day state advances — "the cover opened today" — so later automatic events no longer act on the
assumption that the scheduled opening or closing is still outstanding.

The two directions are independent checkboxes:

- **🔼 Manual opening during the opening window** — between the early and late opening times
  (or during the calendar opening event), a manual move to the open position advances the
  internal state to "open", exactly as the scheduled opening would.
- **🔻 Manual closing during the closing window** — between the early and late closing times
  (or during the calendar closing event), a manual move to the closed position advances the
  internal state to "closed".

### What it changes — and what it does not

- **State only, never a movement.** The manual change is still recorded as a normal Manual
  Override, the cover is not moved, and everything under [🖐️ Automatic movements blocked
  during Manual Override](#ignore_after_manual_config) and the reset options applies
  unchanged.
- **Without this option** the internal state only advances when an automatic event actually
  fires. On a day where the opening's brightness/sun condition never crosses its threshold,
  a later automatic event — the end of sun shading, a Manual Override reset with
  [return-to-target](#auto_recover_after_manual_reset) enabled, a restart catch-up — could
  still treat the day state as "not opened yet" and move the cover accordingly. With the
  option enabled, your manual opening settles that question.
- **The once-per-day guards count the adoption.** With *"open only once a day"* (or the
  closing equivalent) enabled, the adopted event counts as that day's opening/closing.
- **Sun shading is untouched.** An active or pending sun shading keeps its own lifecycle; a
  manual close during the closing window does not cancel it, the shading simply ends through
  its normal end conditions and then lands on the adopted "closed" state.

### Requirements

- The matching feature must be enabled ("🔼 Morning Opening" / "🔻 Evening Closing").
- A time window must exist for that direction: the time fields or a calendar. With time
  control disabled entirely there is no window, and nothing is adopted.
- Outside the window (e.g. a manual opening in the evening) nothing is adopted either — the
  movement stays a plain Manual Override.

---

<a id="reset_override_config"></a>

## 🗑️ Reset manual override

> 🧩 Input: `reset_override_config`

If the detection of the manual position change was activated above, you may need a way to reset this status. Otherwise, the next cover movements will be permanently ignored or overridden. Or you have not activated an individual action, e.g. when closing the covers, which resets the status. <br /><br /> You can select **multiple** reset mechanisms — the first one whose condition is met clears the override. Leave empty to disable all timed resets.

A reset always hands control back to CCA and clears the override status. Whether it also moves
the cover right away is a separate decision — see [🔙 Return to Target State After Manual
Override Reset](#auto_recover_after_manual_reset) below.

---

<a id="auto_recover_after_manual_reset"></a>

## 🔙 Return to Target State After Manual Override Reset

> 🧩 Input: `auto_recover_after_manual_reset` · Default: `❌ Disable Automatic Return to Target State`

When one of the resets above fires, should the cover immediately move to the automatic target
that is valid then?

- **Disabled (default):** the reset only clears the override status. The cover stays where it
  is until the next regular automatic event (opening/closing, sun shading, ventilation)
  naturally moves it. This matches CCA's behavior from before the reset itself started driving
  the cover.
- **Enabled:** the reset re-derives the currently correct target from your schedule — the same
  gates restart/outage recovery uses — and drives there immediately, even if that differs a lot
  from the manually set position. For example, closing a cover manually and enabling this with a
  30-minute timeout can reopen it after 30 minutes while the opening schedule is still active.
  Choose a timeout that extends beyond the relevant automatic window, or leave this disabled,
  when the manual position must remain in control longer.

Even enabled, a reset will never open a cover for which no opening automation is configured on
this instance — an `opn` resting state with no opening schedule is CCA's permanent init default,
not something it ever scheduled, so that case always stays put.

---

<a id="reset_override_time"></a>

## 🗑️ Time to reset manual override

> 🧩 Input: `reset_override_time` · Default: `00:01:00`

At what time do you want the manual detection to be reset?

---

<a id="reset_override_timeout"></a>

## 🗑️ Number of minutes until reset manual override

> 🧩 Input: `reset_override_timeout` · Default: `5`

After how many minutes should the override status be cleared? Whether the cover then also moves depends on [🔙 Return to Target State After Manual Override Reset](#auto_recover_after_manual_reset) above.

---

<a id="reset_override_position"></a>

## 🗑️ Position for reset manual override

> 🧩 Input: `reset_override_position` · Default: `100`

At which position (+- tolerance) should it be reset? Typically, these are 'open' or 'closed' positions.

---

<a id="reset_override_position_dwell"></a>

## 🗑️ Dwell time at reset position (minutes)

> 🧩 Input: `reset_override_position_dwell` · Default: `5`

How long must the cover stay at the reset position (± tolerance) before the manual override is cleared? Only applies to the 'Reset in position' option.

---

[⬅️ Handbook index](index) · Previous: [🛏️ Resident Mode](resident) · Next: [🛡️ Force Functions & Pause](force)

{% endraw %}
