{% raw %}
# 🛡️ Force Functions & Pause

> Part of the [CCA Handbook](index). These options live in the **Force Features** section of the blueprint.

<center><p><small>
  Emergency override controls for weather protection and special scenarios
  <br />
  Force functions allow you to immediately move covers to specific positions, overriding all other automation logic.
  <br />
  Use cases include: rain protection, wind protection, frost prevention, or temporary manual control.
  <br />
  📖 See: <a href="https://hvorragend.github.io/ha-blueprints/FAQ#q-how-does-a-force-function-work">FAQ: How does a force function work?</a>
  <br />
  <br />
  All settings in this section are optional
</small></p></center>

<a id="auto_recover_after_force"></a>

## 🔙 Return to Target State After Force Disable

*Blueprint input: `auto_recover_after_force`* *(default: `auto_recover_disabled`)*

Seamless control with automatic recovery: When enabled, the cover automatically returns to its intended position when a force function is disabled.
<details> <summary><code><strong>HOW IT WORKS:</strong> Smart Background Tracking</code></summary>

**Continuous Status Tracking:**
- The helper constantly monitors what the cover *should* be doing (open, close, shading, ventilate)
- Even when a force function is active, the background state is always up-to-date
- When the force function is disabled, the cover knows exactly where to return

**Perfect for:**
- 🌧️ Rain Protection (force-close, auto-recover to shading)
- 💨 Wind Protection (force-open, auto-recover to normal state)
- ❄️ Frost Protection (force-open, auto-resume after sunrise)
- 🔥 Emergency Scenarios (temporary manual control, then auto-recovery)
- 🏠 Cleaning/Maintenance (force-open, then auto-return when done)

</details>

<a id="force_pause"></a>

## ⏸️ Force Pause (Suspend Automatic Actions)

*Blueprint input: `force_pause`*

If the status of this entity changes to on or true, all automatic cover movements are suspended immediately. The background state (target positions) is still tracked continuously in the helper — even while paused.
When this entity turns off again, the cover **immediately returns** to its correct target position — no waiting for the next scheduled trigger.
💡 **Tip:** Use an `input_boolean` as a manual/automatic toggle. Unlike putting a switch in the global condition (which blocks helper state updates too), this force pause only blocks cover movement. The helper always reflects the correct background state, so resuming is instant and reliable.

<a id="auto_up_force"></a>

## 🔼 Force Immediate Opening via Entity

*Blueprint input: `auto_up_force`*

If the status of this entity changes to on or true, the cover is opened immediately and without further checking.

<a id="auto_down_force"></a>

## 🔻 Force Immediate Closing via Entity

*Blueprint input: `auto_down_force`*

If the status of this entity changes to on or true, the cover is closed immediately and without further checking.

<a id="auto_ventilate_force"></a>

## 💨 Force Immediate Ventilation via Entity

*Blueprint input: `auto_ventilate_force`*

If the status of this entity changes to on or true, the cover is immediately set to ventilation mode and without further checking.

<a id="auto_shading_start_force"></a>

## 🥵 Force Activation Sun Shading via Entity

*Blueprint input: `auto_shading_start_force`*

If the status of this entity changes to on or true, the shading is immediately activated and without further checking.

{% endraw %}
