{% raw %}
# 🔀 Additional Conditions

[📖 CCA Handbook](index) › Blueprint section: **Additional Conditions**

All these settings are optional

**On this page:** [❓ Additional Condition for the entire automation](#auto_global_condition) · [🔼 Additional Condition For Opening The Cover](#auto_up_condition) · [🔻 Additional Condition For Closing The Cover](#auto_down_condition) · [💨 Additional Condition For Activating Ventilation](#auto_ventilate_condition) · [💨 Additional Condition For Disabling Ventilation](#auto_ventilate_end_condition) · [🥵 Additional Condition When Activating Sun Shading](#auto_shading_start_condition) · [🥵 Additional Condition For Sun Shading Tilt](#auto_shading_tilt_condition) · [🥵 Additional Condition When Deactivating Sun Shading](#auto_shading_end_condition)

---

<a id="auto_global_condition"></a>

## ❓ Additional Condition for the entire automation

> 🧩 Input: `auto_global_condition`

This condition allows you to control the execution of the <ins>entire</ins> automation dynamically and outside of the blueprint configuration. With this option you could enable a party mode. <br /><br /> If the result of this condition is <ins>true</ins>, the automation will continue.<br /> The result of the conditions must be <ins>false</ins>, for the automation to stop in this sequence. <br /><br /> Forcing Open/Close/Shading/Ventilation is therefore only possible if this condition remains empty or becomes valid.

---

<a id="auto_up_condition"></a>

## 🔼 Additional Condition For Opening The Cover

> 🧩 Input: `auto_up_condition`

This condition can be used to dynamically control the <ins>opening</ins> of the cover. You can use this, for example, if the covers normally don't open, but you really want to do it on vacation. <br /><br /> If the result of this condition is <ins>true</ins>, the automation will continue.<br /> The result of the conditions must be <ins>false</ins>, for the automation to stop in this sequence.

---

<a id="auto_down_condition"></a>

## 🔻 Additional Condition For Closing The Cover

> 🧩 Input: `auto_down_condition`

This condition can be used to dynamically control the <ins>closing</ins> of the cover. You can use this, for example, at Christmas time or if you want the covers to behave differently while on vacation. <br /><br /> If the result of this condition is <ins>true</ins>, the automation will continue.<br /> The result of the conditions must be <ins>false</ins>, for the automation to stop in this sequence.

---

<a id="auto_ventilate_condition"></a>

## 💨 Additional Condition For Activating Ventilation

> 🧩 Input: `auto_ventilate_condition`

This condition can be used to dynamically control the <ins>start of the ventilation</ins> of the cover. <br /><br /> If the result of this condition is <ins>true</ins>, the automation will continue.<br /> The result of the conditions must be <ins>false</ins>, for the automation to stop in this sequence.

---

<a id="auto_ventilate_end_condition"></a>

## 💨 Additional Condition For Disabling Ventilation

> 🧩 Input: `auto_ventilate_end_condition`

This condition can be used to dynamically control the <ins>end of the ventilation</ins> of the cover. <br /><br /> If the result of this condition is <ins>true</ins>, the automation will continue.<br /> The result of the conditions must be <ins>false</ins>, for the automation to stop in this sequence.

---

<a id="auto_shading_start_condition"></a>

## 🥵 Additional Condition When Activating Sun Shading

> 🧩 Input: `auto_shading_start_condition`

This condition can be used to dynamically control the <ins>shading-IN-automation</ins> of the cover. This can be useful if you want to temporarily disable automation (e.g. because of control by other automations). <br /><br /> If the result of this condition is <ins>true</ins>, the automation will continue.<br /> The result of the conditions must be <ins>false</ins>, for the automation to stop in this sequence. <br /> Another example: Here you could also set that the shading is only triggered in the summer season.

---

<a id="auto_shading_tilt_condition"></a>

## 🥵 Additional Condition For Sun Shading Tilt

> 🧩 Input: `auto_shading_tilt_condition`

This condition can be used to dynamically control the <ins>shading_tilt-IN-automation</ins> of the cover. This can be useful if you want to temporarily disable automation (e.g. because of control by other automations). <br /> Another example: Here you could also set that the tilting is only triggered in the summer season. <br /><br /> If the result of this condition is <ins>true</ins>, the automation will continue.<br /> The result of the conditions must be <ins>false</ins>, for the automation to stop in this sequence.

---

<a id="auto_shading_end_condition"></a>

## 🥵 Additional Condition When Deactivating Sun Shading

> 🧩 Input: `auto_shading_end_condition`

This condition can be used to dynamically control the <ins>shading-OUT-automation</ins> of the cover. This can be useful if you want to temporarily disable automation (e.g. because of control by other automations). <br /> If the result of this condition is <ins>true</ins>, the automation will continue.<br /> The result of the conditions must be <ins>false</ins>, for the automation to stop in this sequence.

---

[⬅️ Handbook index](index) · Previous: [⏳ Drive Delays](delays) · Next: [🎬 Before/After Actions](actions)

{% endraw %}
