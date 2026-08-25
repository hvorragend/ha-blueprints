{% raw %}
# 🎬 Before/After Actions

[📖 CCA Handbook](index) › Blueprint section: **Additional Actions**

All these settings are optional

**On this page:**

- [When movement actions run](#action_lifecycle)
- [Using custom actions instead of CCA's cover services](#custom_actions_only)
- [Example: Overkiz combined position and tilt call](#custom_actions_overkiz)
- [🔼 Additional Actions Before Opening The Cover](#auto_up_action_before)
- [🔼 Additional Actions After Opening The Cover](#auto_up_action)
- [🔻 Additional Actions Before Closing The Cover](#auto_down_action_before)
- [🔻 Additional Actions After Closing The Cover](#auto_down_action)
- [💨 Additional Actions Before Ventilating The Cover](#auto_ventilate_action_before)
- [💨 Additional Actions After Ventilating The Cover](#auto_ventilate_action)
- [🥵 Additional Actions Before Activating Sun Shading](#auto_shading_start_action_before)
- [🥵 Additional Actions After Activating Sun Shading](#auto_shading_start_action)
- [🥵 Additional Actions Before Disabling Sun Shading](#auto_shading_end_action_before)
- [🥵 Additional Actions After Disabling Sun Shading](#auto_shading_end_action)
- [🖐️ Additional Actions After Manual Change](#auto_manual_action)
- [🗑️ Additional Actions After Override Reset](#auto_override_reset_action)

---

<a id="action_lifecycle"></a>

## When movement actions run

The opening, closing, ventilation and sun-shading before/after actions belong to a real CCA movement pipeline. They do not run for a status-only update or when the cover position and relevant tilt are already within the configured tolerances.

For a movement that is still required, CCA follows this order:

1. Wait for the configured fixed/random drive delay.
2. Confirm that Force Pause is still off and this automation instance still owns the cover.
3. Run the matching **before-action**.
4. Confirm ownership again, then dispatch the built-in position/tilt commands.
5. Run the matching **after-action**, but only if a movement stage was actually dispatched.

The live checks are repeated around movement stages that contain waits. If Force Pause becomes active or another CCA instance takes ownership, CCA suppresses every stage it has not dispatched yet. If an earlier stage already moved the cover, the after-action still runs for that partial dispatch.

The actions after a manual change and after an override reset are state-event actions rather than movement wrappers. They run when their named event is recorded; they do not use the movement sequence above.

---

<a id="custom_actions_only"></a>

## Using custom actions instead of CCA's cover services

The **🔧 Use custom actions only** behavior option disables CCA's built-in `cover.set_cover_position` and `cover.set_cover_tilt_position` calls. In this mode, the matching **after-action is the movement implementation**: use it to call the script, service or device-specific command that actually moves the cover. Configure an appropriate after-action for every movement type CCA may use (opening, closing, ventilation, sun-shading start and sun-shading end).

CCA cannot inspect what a custom action does or verify that the device moved. Reaching the custom-only after-action pipeline after all delay, tolerance, pause and ownership checks is therefore CCA's dispatch contract. At that point CCA records the movement time and may clear Manual Override just as it would after a built-in command.

> ⚠️ **Important:** Do not enable **Use custom actions only** without complete movement after-actions. An empty, conditional or no-op after-action is still treated as a dispatched custom movement once its pipeline is reached, so the status helper and logbook may say that CCA moved the cover even though the physical cover stayed in place.

Before-actions keep their normal role in this mode: they prepare for the custom movement, but they are not the movement carrier.

Pure tilt-only plans, such as automatic sun-shading slat tracking, have no separate custom-action input. Because **Use custom actions only** disables CCA's built-in tilt service as well, those tilt-only adjustments are skipped: they do not dispatch a movement and do not run a before- or after-action. If your hardware needs continuous custom slat tracking, implement that behavior outside this option's movement after-actions.

---

<a id="custom_actions_overkiz"></a>

## Example: Overkiz combined position and tilt call

The Overkiz integration provides the service `overkiz.set_cover_position_and_tilt`, which sets the cover position **and** the slat tilt in a single command. For Somfy venetian covers (e.g. J4 IO motors) this sidesteps the sequencing constraints of separate position and tilt commands — these motors ignore tilt commands while fully open and re-apply their last tilt target after every positioning run (see [#355](https://github.com/hvorragend/ha-blueprints/issues/355), [#612](https://github.com/hvorragend/ha-blueprints/issues/612) and [#684](https://github.com/hvorragend/ha-blueprints/issues/684), where this recipe was contributed).

Setup:

1. Enable **🔧 Use custom actions only** (Automation Options → Behavior Customization) so CCA's built-in `cover.set_cover_position` / `cover.set_cover_tilt_position` calls and their tilt waits are skipped.
2. Add the following action to **every** movement after-action — opening, closing, ventilating, activating sun shading and disabling sun shading:

```yaml
action: overkiz.set_cover_position_and_tilt
data:
  tilt_position: "{{ target_tilt_position | default(101) }}"
  position: "{{ target_position | default(101) }}"
target:
  entity_id: "{{ blind }}"
```

Notes:

- This works only for covers managed through the **Overkiz** integration.
- In custom-actions-only mode the after-action **is** the movement. A movement type whose after-action does not carry this call will not move the cover — configure all five slots.
- The tilt-only limitation described above still applies: pure slat-tracking adjustments without a position change are skipped in this mode.

---

<a id="auto_up_action_before"></a>

## 🔼 Additional Actions Before Opening The Cover

> 🧩 Input: `auto_up_action_before`

Additional actions to run <ins>before</ins> opening the cover

---

<a id="auto_up_action"></a>

## 🔼 Additional Actions After Opening The Cover

> 🧩 Input: `auto_up_action`

Additional actions to run <ins>after</ins> opening the cover

---

<a id="auto_down_action_before"></a>

## 🔻 Additional Actions Before Closing The Cover

> 🧩 Input: `auto_down_action_before`

Additional actions to run <ins>before</ins> closing the cover

---

<a id="auto_down_action"></a>

## 🔻 Additional Actions After Closing The Cover

> 🧩 Input: `auto_down_action`

Additional actions to run <ins>after</ins> closing the cover

---

<a id="auto_ventilate_action_before"></a>

## 💨 Additional Actions Before Ventilating The Cover

> 🧩 Input: `auto_ventilate_action_before`

Additional actions to run <ins>before</ins> ventilating the cover

---

<a id="auto_ventilate_action"></a>

## 💨 Additional Actions After Ventilating The Cover

> 🧩 Input: `auto_ventilate_action`

Additional actions to run <ins>after</ins> ventilating the cover

---

<a id="auto_shading_start_action_before"></a>

## 🥵 Additional Actions Before Activating Sun Shading

> 🧩 Input: `auto_shading_start_action_before`

Additional actions to run <ins>before</ins> activating sun shading

---

<a id="auto_shading_start_action"></a>

## 🥵 Additional Actions After Activating Sun Shading

> 🧩 Input: `auto_shading_start_action`

Additional actions to run <ins>after</ins> activating sun shading

---

<a id="auto_shading_end_action_before"></a>

## 🥵 Additional Actions Before Disabling Sun Shading

> 🧩 Input: `auto_shading_end_action_before`

Additional actions to run <ins>before</ins> disabling sun shading

---

<a id="auto_shading_end_action"></a>

## 🥵 Additional Actions After Disabling Sun Shading

> 🧩 Input: `auto_shading_end_action`

Additional actions to run <ins>after</ins> disabling sun shading

---

<a id="auto_manual_action"></a>

## 🖐️ Additional Actions After Manual Change

> 🧩 Input: `auto_manual_action`

Additional actions after a manual change to the covers

---

<a id="auto_override_reset_action"></a>

## 🗑️ Additional Actions After Override Reset

> 🧩 Input: `auto_override_reset_action`

Additional actions to be taken after resetting the manual override

---

[⬅️ Handbook index](index) · Previous: [🔀 Additional Conditions](conditions) · Next: [🩺 Configuration Check](configcheck)

{% endraw %}
