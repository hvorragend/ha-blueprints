{% raw %}
# 🧱 Basics: Cover & Status Helper

> Part of the [CCA Handbook](index). These two settings are the mandatory foundation of every CCA automation.

<a id="blind"></a>

## 🪟 Cover

*Blueprint input: `blind`*

Which blind or roller shutter should be automated?
Using a cover group? See [FAQ: Can I use a cover group?](https://hvorragend.github.io/ha-blueprints/FAQ#q-can-i-use-a-cover-group)

<a id="cover_status_helper"></a>

## 🔤 Cover Status Helper

*Blueprint input: `cover_status_helper`*

Helper used to store the last cover event data (in JSON format). A separate helper must be created for each CCA automation. *Attention:* You will need to manually create an [input_text](https://my.home-assistant.io/redirect/helpers/) entity with a <ins>length of 254 chars</ins> for this.

{% endraw %}
