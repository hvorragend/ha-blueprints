{% raw %}
# 🧱 Basics: Cover & Status Helper

[📖 CCA Handbook](index) › These two settings are the mandatory foundation of every CCA automation.

**On this page:** [🪟 Cover](#blind) · [🔤 Cover Status Helper](#cover_status_helper)

> ⚠️ **Requirement:** CCA requires **Home Assistant 2025.4.0 or newer**. Its transition and recovery logic relies on values assigned inside nested `if`/`choose` actions remaining available to the enclosing automation sequence. Older Home Assistant versions do not provide the variable-scope behavior CCA needs, which can silently prevent movement decisions, after-actions and movement tracking from reaching the final transition step.

---

<a id="blind"></a>

## 🪟 Cover

> 🧩 Input: `blind`

Which blind or roller shutter should be automated?
Using a cover group? See [FAQ: Can I use a cover group?](https://hvorragend.github.io/ha-blueprints/FAQ#q-can-i-use-a-cover-group)

---

<a id="cover_status_helper"></a>

## 🔤 Cover Status Helper

> 🧩 Input: `cover_status_helper`

Helper used to store the last cover event data (in JSON format). A separate helper must be created for each CCA automation. *Attention:* You will need to manually create an [input_text](https://my.home-assistant.io/redirect/helpers/) entity with a <ins>length of 254 chars</ins> for this.

---

[⬅️ Handbook index](index) · Next: [⚙️ Features & Modes](features)

{% endraw %}
