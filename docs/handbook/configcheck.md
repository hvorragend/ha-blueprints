{% raw %}
# 🩺 Configuration Check

[📖 CCA Handbook](index) › Blueprint section: **Configuration Check**

<strong>🔗 Use the <a href="https://hvorragend.github.io/ha-blueprints/validator/" target="_blank">Online Configuration Validator</a></strong> <br /> Validate your YAML configuration for errors, typos, and deprecated parameters before deploying. <br /> ✅ Instant feedback • 🔍 Typo detection • ⚠️ Migration guidance • 🔒 Privacy-friendly (client-side)

**On this page:** [✔️ Check Configuration](#check_config) · [✔️ Check Configuration - Debug level](#check_config_debuglevel)

---

<a id="check_config"></a>

## ✔️ Check Configuration

> 🧩 Input: `check_config` · Default: `False`

With this boolean, you can enable or disable the basic plausibility check for the configuration. The check only takes place if the automation is executed manually. <br /><br /> Use the <a href="https://hvorragend.github.io/ha-blueprints/validator/" target="_blank">online validator</a> for another validation.

---

<a id="check_config_debuglevel"></a>

## ✔️ Check Configuration - Debug level

> 🧩 Input: `check_config_debuglevel` · Default: `info`

Choose the debug level for Syslog messages in case of configuration issues <br /> Please make sure that it suits your Home Assistant logger default level.

---

[⬅️ Handbook index](index) · Previous: [🎬 Before/After Actions](actions) · Next: [📝 Logging](logging)

{% endraw %}
