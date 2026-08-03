{% raw %}
# ✋ Manual Override & Reset

[📖 CCA Handbook](index) › Blueprint section: **Manual Override**

**On this page:** [🖐️ Automatic movements blocked during Manual Override](#ignore_after_manual_config) · [🗑️ Reset manual override](#reset_override_config) · [🗑️ Time to reset manual override](#reset_override_time) · [🗑️ Number of minutes until reset manual override](#reset_override_timeout) · [🗑️ Position for reset manual override](#reset_override_position) · [🗑️ Dwell time at reset position (minutes)](#reset_override_position_dwell)

---

<a id="ignore_after_manual_config"></a>

## 🖐️ Automatic movements blocked during Manual Override

> 🧩 Input: `ignore_after_manual_config`

Select which automatic movements must not move the cover while a Manual Override is active.

### How the selection works

- **Selected:** the manual position wins and this type of automatic movement is blocked until the Manual Override is reset.
- **Not selected:** this automatic movement may take control even while Manual Override is active. If CCA actually dispatches the movement — through its built-in cover services or the configured [custom-only after-action pipeline](actions#custom_actions_only) — the Manual Override is cleared.

The four choices are independent: automatic opening, closing, ventilation and sun shading can each have a different policy. They govern the event that owns the movement: scheduled opening/closing, the sun-shading lifecycle, or a window-contact ventilation event. For example, you can keep a manually closed cover protected from the next scheduled opening while still allowing sun shading when the facade becomes hot.

### What continues in the background

Manual Override blocks only the selected physical movements. CCA still tracks the current opening/closing schedule, sun-shading waiting period and active state, window contacts, resident state and force functions. Resetting the override therefore reconciles the target that is valid at that moment instead of waiting for a new sensor edge or restarting an old delay.

Some configured events explicitly hand control back to CCA instead of consuming these four choices: a resident arrival/departure that has a movement configured, enabling or switching a Force position, disabling Force Pause, and disabling a Force position with automatic return enabled. They replace the older manual intent only when CCA really dispatches a movement; a state-only update or already-reached target preserves Manual Override.

For contact ventilation, **Block automatic ventilation** controls both the reaction to a tilted window and the return to the current background target when the window closes. A fully opened window is the safety exception described below.

A selected sun-shading option blocks every shading-related movement while Manual Override remains active; it does not discard the shading state. If shading starts and ends entirely during the override, no obsolete shading movement is replayed afterwards. If shading is still required when the override resets, CCA can move directly to the shading target.

The full-window lockout remains the safety exception that may overrule Manual Override when its ventilation condition permits the proactive movement. If that condition is false, CCA still records the open window and prevents later closing or sun-shading movement; it merely does not raise the cover at the moment the window opens. Enabling a Force position is also an explicit higher-priority command; Force Pause can still suppress it.

---

<a id="reset_override_config"></a>

## 🗑️ Reset manual override

> 🧩 Input: `reset_override_config`

If the detection of the manual position change was activated above, you may need a way to reset this status. Otherwise, the next cover movements will be permanently ignored or overridden. Or you have not activated an individual action, e.g. when closing the covers, which resets the status. <br /><br /> You can select **multiple** reset mechanisms — the first one whose condition is met clears the override. Leave empty to disable all timed resets.

---

<a id="reset_override_time"></a>

## 🗑️ Time to reset manual override

> 🧩 Input: `reset_override_time` · Default: `00:01:00`

At what time do you want the manual detection to be reset?

---

<a id="reset_override_timeout"></a>

## 🗑️ Number of minutes until reset manual override

> 🧩 Input: `reset_override_timeout` · Default: `5`

After how many minutes should it be reset?

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
