{% raw %}
# Window-Sun-Angle Aware Shading

> **Recipe — no blueprint changes required.** Uses the existing **Force Shading** input to drive shading from a user-built helper sensor that knows your window's orientation.

## 🌍 The Problem

The blueprint's built-in shading conditions check the sun against an **azimuth × elevation rectangle**. The cover shades whenever the sun is somewhere inside that rectangle — even when the sun is *not actually shining into the window*.

This is most painful for:
- **Tilted / roof / Velux windows** ([#245](https://github.com/hvorragend/ha-blueprints/issues/245)) — the window plane is not vertical, so a flat azimuth/elevation box doesn't describe direct sunlight.
- **Multi-orientation rooms** with east/south/west windows ([#187](https://github.com/hvorragend/ha-blueprints/issues/187) discussion) — each window needs its own "is the sun pointing at me?" check.
- **Obstacles** (neighbouring buildings, trees) that shade specific azimuth slices.

## ✨ The Solution

Build a **template helper sensor** that computes how directly the sun is hitting the window (cosine similarity between the sun vector and the window's normal vector), threshold it into a **binary sensor**, and feed that binary sensor into the existing **🥵 Force Activation Sun Shading via Entity** input. Pair it with **🔙 Return to Target State After Force Disable** to get a clean comeback when the sun moves on.

**Why Force Shading?** Because the sensor *is* the decision. When it's `on`, you want shading — period. The blueprint's normal shading conditions are designed to combine *several* signals (azimuth, elevation, brightness, temperature, forecast) and only need the rectangle approximation because they don't know your window's orientation. Once your helper sensor encodes orientation, that one signal is enough.

> ⚠️ **Read the [Caveats](#-caveats) section before deploying.** Force Shading sits at the top of the priority cascade — it overrides lockout, ventilation and privacy. The recipe shows how to AND-in a window-contact sensor to keep lockout safety.

---

## 🚀 Quick Setup (10 Minutes)

### Step 1: Add the Similarity Template Sensor

Add this to `configuration.yaml` (or a `packages/` file). Replace the `win_azi`, `win_ele`, and `sun_ele_threshold` values with your window's data — see [📐 Mathematical Background](#-mathematical-background) for how to find them.

```yaml
template:
  - sensor:
      - name: "Kitchen Window Sun Similarity"
        unique_id: kitchen_window_sun_similarity
        unit_of_measurement: "%"
        icon: mdi:window-closed-variant
        state: >
          {% set deg2rad = pi/180 %}

          {% set sun_azi = state_attr('sun.sun', 'azimuth') | float(0) %}
          {% set sun_ele = state_attr('sun.sun', 'elevation') | float(0) %}

          {% set sun_x = cos(sun_azi*deg2rad)*cos(sun_ele*deg2rad) %}
          {% set sun_y = sin(sun_azi*deg2rad)*cos(sun_ele*deg2rad) %}
          {% set sun_z = sin(sun_ele*deg2rad) %}

          {% set win_azi = 232.68 %}
          {% set win_ele = 0 %}
          {% set sun_ele_threshold = 5 %}

          {% set win_x = cos(win_azi*deg2rad)*cos(win_ele*deg2rad) %}
          {% set win_y = sin(win_azi*deg2rad)*cos(win_ele*deg2rad) %}
          {% set win_z = sin(win_ele*deg2rad) %}

          {% set dot = sun_x*win_x + sun_y*win_y + sun_z*win_z %}
          {% set norm_win = sqrt(win_x**2 + win_y**2 + win_z**2) %}
          {% set norm_sun = sqrt(sun_x**2 + sun_y**2 + sun_z**2) %}
          {% set cos_sim = dot/(norm_win*norm_sun) %}

          {{ ((cos_sim * 100) | round(0)) if (sun_ele > sun_ele_threshold and cos_sim > 0) else 0 }}
```

> Credit: original formula by [@itsamejoshab](https://github.com/itsamejoshab) in [#187](https://github.com/hvorragend/ha-blueprints/issues/187).

**Output range:** `0` (sun behind the window or below `sun_ele_threshold`) … `100` (sun perfectly perpendicular to window).

### Step 2: Add the Binary Threshold Sensor

```yaml
template:
  - binary_sensor:
      - name: "Kitchen Window Sun Direct"
        unique_id: kitchen_window_sun_direct
        device_class: light
        state: >
          {{ states('sensor.kitchen_window_sun_similarity') | float(0) > 30 }}
```

`30` is a good starting threshold (≈ 73° between sun and window normal). Lower = shades earlier / longer. Higher = shades only at strong direct hits.

> 💡 **Hysteresis tip:** to prevent flapping near the threshold, use two thresholds. See [Hysteresis](#hysteresis-recommended) below.

### Step 3: Restart Home Assistant

**Settings** → **System** → **Restart**

### Step 4: Verify

**Developer Tools** → **States**:
- `sensor.kitchen_window_sun_similarity` → numeric `0`–`100`
- `binary_sensor.kitchen_window_sun_direct` → `on` when sun hits, `off` otherwise

### Step 5: Configure CCA Blueprint

In your CCA automation:

1. Open the **Force Features** section.
2. **🥵 Force Activation Sun Shading via Entity** → select `binary_sensor.kitchen_window_sun_direct`.
3. **🔙 Return to Target State After Force Disable** → set to **✅ Enable Automatic Return to Target State**.
4. Save the automation.

**Done. 🎉** The cover now shades exactly when the sun is shining directly into your window and returns to its normal target state when the sun moves on.

---

## ⚠️ Caveats

### Force Shading bypasses Lockout, Ventilation and Privacy

Force Shading sits **above** all other priorities (see [FAQ: How does a force function work?](FAQ.md#q-how-does-a-force-function-work)). With the naive recipe above, the cover will shade even with the window wide open.

**Recommended fix — AND in your window contact sensor:**

```yaml
template:
  - binary_sensor:
      - name: "Kitchen Window Sun Direct"
        unique_id: kitchen_window_sun_direct
        device_class: light
        state: >
          {{ states('sensor.kitchen_window_sun_similarity') | float(0) > 30
             and is_state('binary_sensor.kitchen_window_contact', 'off') }}
```

Now the binary sensor stays `off` whenever the window is open → Force Shading isn't triggered → the blueprint's normal lockout/ventilation logic runs as intended.

You can chain in additional gates the same way — presence, mode helper, brightness sensor, anything you want.

### Hysteresis (recommended)

Without hysteresis the binary sensor can oscillate around the threshold. Use two thresholds and the previous state:

```yaml
template:
  - binary_sensor:
      - name: "Kitchen Window Sun Direct"
        unique_id: kitchen_window_sun_direct
        device_class: light
        state: >
          {% set sim = states('sensor.kitchen_window_sun_similarity') | float(0) %}
          {% set is_on = is_state('binary_sensor.kitchen_window_sun_direct', 'on') %}
          {{ sim > 25 if is_on else sim > 35 }}
```

Turns `on` at 35, stays on until it drops below 25. Adjust to taste.

### Re-trigger

The Force Shading input is a normal HA state trigger, so any state change of the binary sensor (`off` → `on`, `on` → `off`) drives the cover immediately. This addresses the re-trigger problem mentioned by [@ahemwe](https://github.com/hvorragend/ha-blueprints/issues/187#issuecomment-4366157782) when using the similarity value as a plain shading condition.

---

## 📐 Mathematical Background

The sensor computes the **dot product** of two unit vectors:

- **Sun vector** — from `sun.sun.azimuth` and `sun.sun.elevation`
- **Window normal vector** — from your inputs `win_azi` and `win_ele`

Both expressed in spherical coordinates → converted to Cartesian → normalized → dot product.

The dot product of two unit vectors equals `cos(angle)` between them:

| `cos_sim` | Angle between sun and window normal | Meaning |
|-----------|-------------------------------------|---------|
| `1.0` | 0° | Sun directly perpendicular — strongest hit |
| `0.5` | 60° | Glancing |
| `0` | 90° | Sun is parallel to window plane |
| `< 0` | > 90° | Sun is on the *other* side of the window — clamped to `0` |

Multiplied by 100 for a `0`–`100` "directness" percentage.

### Finding `win_azi` (window azimuth)

The compass bearing of the **outward-facing** normal of your window. `0` = north, `90` = east, `180` = south, `270` = west.

**Easy method — Google Earth / Maps:**
1. Find your house in satellite view.
2. Use the ruler to draw a line from the centre of the window straight outward (perpendicular to the wall).
3. Read the bearing from the ruler tool.

Example: a window facing roughly south-southwest → `win_azi ≈ 200`–`230`.

### Finding `win_ele` (window tilt)

The vertical tilt of the window's outward normal:

| Window type | `win_ele` |
|-------------|-----------|
| Vertical wall window | `0` |
| Roof window at 45° pitch, normal pointing outward and **upward** | `45` |
| Skylight (horizontal glass facing straight up) | `90` |
| Inward-tilted (rare) | negative |

For a Velux roof window: take the roof pitch from the blueprints / by eye and use that.

### `sun_ele_threshold`

Below this elevation the sun is treated as set. Default `5`° matches "civil twilight is over". Increase if your horizon is blocked by buildings or hills.

### Alternative: angle in degrees (for roof windows)

[@ahemwe](https://github.com/hvorragend/ha-blueprints/issues/187#issuecomment-4366157782) uses `acos` to get the actual angle between the sun and the roof surface, which is easier to threshold intuitively for roof windows. Replace the last line of the similarity sensor with:

```yaml
{% set ang_rad = acos(cos_sim) %}
{% set ang_deg = ang_rad * 180 / pi %}
{% set roof_angle = 90 - ang_deg %}
{{ roof_angle | round(0) if sun_ele > sun_ele_threshold else -90 }}
```

`roof_angle` reads as: positive = sun shines *into* the window, `0` = grazing the window plane, negative = sun behind the window. Threshold the binary sensor on, e.g., `> 10`.

---

## 🏠 Multi-Window Setup

One sensor pair per window — one CCA automation per cover, each pointed at its own binary sensor.

**Naming convention:**

```
sensor.<room>_<orientation>_window_sun_similarity
binary_sensor.<room>_<orientation>_window_sun_direct
```

Examples:
- `sensor.living_east_window_sun_similarity` (`win_azi: 90`)
- `sensor.living_south_window_sun_similarity` (`win_azi: 180`)
- `sensor.bedroom_west_window_sun_similarity` (`win_azi: 270`)
- `sensor.bath_roof_window_sun_similarity` (`win_azi: 180`, `win_ele: 35`)

Each binary sensor goes into its own automation's Force Shading input.

---

## 🐛 Troubleshooting

### Similarity sensor shows `0` even when sun is shining in

- Check `state_attr('sun.sun', 'azimuth')` and `'elevation')` in **Developer Tools → Template** — both must return numbers.
- Verify `sun_ele > sun_ele_threshold`: at low sun, the formula clamps to `0` by design.
- Verify `win_azi` direction (compass: 0=N, 90=E, 180=S, 270=W). A common mistake is using the *inward* normal — flip by adding 180.

### Cover shades even when the window is open

You skipped the [Caveats](#-caveats) AND-gate. Add `is_state('binary_sensor.<your_window_contact>', 'off')` to the binary-sensor template.

### Cover stays in shading after the sun has moved on

You don't have **🔙 Return to Target State After Force Disable** enabled. Set it to **✅ Enable Automatic Return to Target State**.

### Cover oscillates around the threshold

Use the [hysteresis](#hysteresis-recommended) two-threshold variant.

### Sensor isn't re-evaluating

`sun.sun` updates every few minutes by default — that's enough for shading. If you want faster updates, wrap the template sensor in a `trigger:` block with `time_pattern: minutes: '/1'`.

### Multiple force functions warning in the log

CCA only allows one force function per automation. If you also use Force Open / Close / Ventilate, make sure they can't be `on` at the same time as your sun-direct binary sensor — see [FAQ: Can multiple force functions be active simultaneously?](FAQ.md#q-can-multiple-force-functions-be-active-simultaneously).

---

## 💡 Pro Tips

1. **Tune the threshold per window.** West-facing windows in late afternoon often want a higher threshold (the sun is high "directness" but already weakening) — bump from 30 to 40.
2. **Combine with brightness.** For an extra-precise gate, AND in `states('sensor.outdoor_brightness') | float > 30000`. Stops the helper from forcing shading on a hazy morning.
3. **Visualize on a dashboard.** Add the similarity sensor to a `history-graph` card together with `sun.sun` for a few days — it makes finding the right threshold trivial.
4. **Different binary sensor per season.** Some users want stricter shading in summer and looser in winter. Build a single similarity sensor and two binary sensors (different thresholds), and route via an `input_select` template.

---

## 📚 Related

- [FAQ: What are force functions?](FAQ.md#q-what-are-force-functions)
- [FAQ: How does a force function work?](FAQ.md#q-how-does-a-force-function-work)
- [FAQ: What is "Return to Target State After Force Disable"?](FAQ.md#q-what-is-return-to-target-state-after-force-disable)
- [Issue #187 — Account for Sun-Window angle for sun triggers](https://github.com/hvorragend/ha-blueprints/issues/187)
- [Issue #245 — Roof window shading (closed as duplicate)](https://github.com/hvorragend/ha-blueprints/issues/245)
{% endraw %}
