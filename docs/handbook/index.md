# 📖 CCA Handbook — Cover Control Automation

The complete configuration reference for the **Cover Control Automation (CCA)** blueprint.
Every blueprint input is documented here in full detail — the blueprint UI shows a short
summary and links to the matching chapter of this handbook.

**New to CCA?** Start with the [Quick Start Guide](../#-quick-start-5-steps) and the
[FAQ](../FAQ), then come back here when you want to fine-tune individual options.

---

## Chapters

### Getting started
1. [🧱 Basics: Cover & Status Helper](basics) — the two mandatory settings
2. [⚙️ Features & Modes](features) — enable/disable automation features, time-control mode, operators
3. [📐 Positions](positions) — position source, cover type, open/close/ventilate/shading positions, tolerance

### Schedules & environment
4. [⏰ Time & Calendar Control](time) — opening/closing times, workday sensors, calendar mode
5. [💡 Brightness](brightness) — brightness-based opening and closing
6. [☀️ Sun Elevation](sun) — fixed, dynamic and hybrid elevation thresholds

### Windows & shading
7. [🚪 Window Contacts & Ventilation](contacts) — lockout protection, tilted-window ventilation
8. [🌤️ Sun Shading](shading) — shading conditions, sun position, forecast, timing and retry behavior
9. [🪟 Tilt Positions (Venetian Blinds)](tilt) — slat control, elevation-dependent tilt stages

### People & overrides
10. [🛏️ Resident Mode](resident) — presence-based behavior
11. [✋ Manual Override & Reset](override) — manual-change detection and reset strategies
12. [🛡️ Force Functions & Pause](force) — forced open/close/ventilate/shading, force pause, recovery

### Fine-tuning
13. [⏳ Drive Delays](delays) — fixed and random delays before movements
14. [🔀 Additional Conditions](conditions) — per-action custom conditions
15. [🎬 Before/After Actions](actions) — custom actions around each movement
16. [🩺 Configuration Check](configcheck) — runtime configuration validation
17. [📝 Logging](logging) — logbook diagnostics

---

## More resources

- ❓ [FAQ](../FAQ) — common questions, troubleshooting, how-tos
- 📢 [Changelog](../CHANGELOG)
- ☀️ [Dynamic Sun Elevation Guide](../DYNAMIC_SUN_ELEVATION)
- ⏰ [Time Control Visualization](../TIME_CONTROL_VISUALIZATION)
- 📐 [Window Sun Angle Guide](../WINDOW_SUN_ANGLE)
- 🔧 [Configuration Validator](../validator/)
- 🔍 [Trace Analyzer](../trace-analyzer/) · 📈 [Trace Compare](../trace-compare/)
- 💬 [Community Thread](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539)
- 🐞 [Report an issue](https://github.com/hvorragend/ha-blueprints/issues)
