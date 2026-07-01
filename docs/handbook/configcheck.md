{% raw %}
# 🩺 Configuration Check

> Part of the [CCA Handbook](index). These options live in the **Configuration Check** section of the blueprint.

<center><p><small> <strong>🔗 Use the <a href="https://hvorragend.github.io/ha-blueprints/validator/" target="_blank">Online Configuration Validator</a></strong> <br /> Validate your YAML configuration for errors, typos, and deprecated parameters before deploying. <br /> ✅ Instant feedback • 🔍 Typo detection • ⚠️ Migration guidance • 🔒 Privacy-friendly (client-side) </small></p></center>

<a id="check_config"></a>

## ✔️ Check Configuration

*Blueprint input: `check_config`* *(default: `False`)*

With this boolean, you can enable or disable the basic plausibility check for the configuration. The check only takes place if the automation is executed manually. <br /><br /> Use the <a href="https://hvorragend.github.io/ha-blueprints/validator/" target="_blank">online validator</a> for another validation.

<a id="check_config_debuglevel"></a>

## ✔️ Check Configuration - Debug level

*Blueprint input: `check_config_debuglevel`* *(default: `info`)*

Choose the debug level for Syslog messages in case of configuration issues <br /> Please make sure that it suits your Home Assistant logger default level.

{% endraw %}
