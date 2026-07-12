{% raw %}
# ✋ Manual Override & Reset

[📖 CCA Handbook](index) › Blueprint section: **Manual Override**

**On this page:** [🖐️ Ignoring/override after manual position changes](#ignore_after_manual_config) · [🗑️ Reset manual override](#reset_override_config) · [🗑️ Time to reset manual override](#reset_override_time) · [🗑️ Number of minutes until reset manual override](#reset_override_timeout) · [🗑️ Position for reset manual override](#reset_override_position) · [🗑️ Dwell time at reset position (minutes)](#reset_override_position_dwell)

---

<a id="ignore_after_manual_config"></a>

## 🖐️ Ignoring/override after manual position changes

> 🧩 Input: `ignore_after_manual_config`

Ignore or override the following actions after manual position changes.

### Further description

Ultimately, this means that the cover will not be opened, closed, etc. if a manual interaction has previously been made, e.g. using a wall switch.

The reason behind this is that the human being wins with his decision and his conscious decision is weighted higher than the upcoming action of the automation.

As soon as a cover has been moved manually, the status is recorded in the Cover Status Helper. This usually means that a person has deliberately decided against a status.

  - If option is not activated: The covers are moved even if a manual correction has been made.
  - If option is activated: The action to open, close, etc. is not performed because a conscious decision was made to do otherwise due to a manual intervention.

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
