# Cover Control Automation (CCA)

[Community-Link](https://community.home-assistant.io/t/cover-control-automation-cca-a-comprehensive-and-highly-configurable-roller-blind-blueprint/680539)

### If you would like to support me or say thank you, please click here:
🙏 [PayPal Donation](https://www.paypal.com/donate/?hosted_button_id=NQE5MFJXAA8BQ) | [Buy me a Coffee](https://buymeacoffee.com/herr.vorragend) 🙏


<br />

*Minimum required version of Home Assistant: **2024.6.0***

This is a comprehensive and highly configurable blueprint that can be used for the following basic purposes:

* Automatic opening and closing the roller shutters
* Freely configurable time windows for opening or closing
* Brightness control and/or control via the sun-elevation
* The use of scheduler helpers are possible
* Ventilation feature (Currently for two-way sensors)
* Resident feature: keep the cover closed if resident is asleep
* Complete flexibility in almost all parameters (drive delays, waiting times, position tolerance)
  - Fixed drive delay and random drive delay
  - Waiting time duration for triggers
  - Position tolerance
* Each feature can be activated or deactivated as required
* Dynamic conditions possible
* Extensive automatic sun shading with many different setting options
* Added the option to save the current status in a helper. This has the advantage that the cover can also be in other positions and the automation can still be executed. And manual interventions are not constantly overridden with every trigger.


## License Notice 
*(Based on the text by SirGoodenough)*
* Copies of the original Blueprint that were converted via the 'Take Control' feature or other means are officially not supported by me.
* I may or may not be able to support you when you have a problem after you make changes to my code, as some of the code is no longer mine.
* I & my license also require attribution as a link back to the original should you use this code in your own creation.
* [Here is a link to my license](https://github.com/hvorragend/ha-blueprints/?tab=License-1-ov-file) & the original github post expected to be followed & referenced as attribution should you use this code elsewhere.



## Condition examples
- If, for example, your blinds on the upper floor only close automatically and are not opened via the automation, you can also enable the blinds to be opened during this time by activating a vacation mode boolean.
- If you have visitors or a party, you may not want the blinds to close. This can be easily configured using a party mode boolean.
- If, for any reason, you want to pause the activation of shading or the ending of shading, this can be controlled via a shading boolean.
- If you want to suspend the entire roller blind control for a short time, perhaps because maintenance work or window cleaning is being carried out, this is possible with just one boolean.
- Are the roller blinds on side doors normally only opened by the automation system and never closed because you don't want to lock yourself out? But on vacation, the blinds should still be closed. This is how the conditions work.

## Shading features
- Sun azimuth
- Sun elevation
- Solar irradiation/Light intensity/Illuminance
- Weather Conditions
- Two different temperature sensors (compare thresholds for indoor and/or outdoor sensors)
- Not only the current temperature, but also the temperature forecast can also be taken into account.
- If multiple criteria (e.g. temperature sensors and/or azimuth and/or elevation) are defined, shading will not occur until <ins>all</ins> criteria are met.

## Important notes
- It is **not** possible to execute this automation manually!
- If you want to use sun elevation and/or azimuth it's strongly advised to use sun.sun. And please make sure your sun.sun entity is enabled!
- `time_up_early` should be earlier `than time_up_late`
- `time_up_early_non_workday` should be earlier than `time_up_late_non_workday`
- `time_down_early` should be earlier than `time_down_late`
- `time_down_early_non_workday` should be earlier than `time_down_late_non_workday`
- `shading_azimuth_start` should be lower than `shading_azimuth_end`
- `shading_elevation_min` should be lower than `shading_elevation_max`
- `shading_sun_brightness_start` should be higher than `shading_sun_brightness_end`
- `open_position` should be higher than `closed_position`
- `open_position` should be higher than `ventilate_position`
- `closed_position` should be lower than `ventilate_position`
- `shading_cover_position` should be higher than `closed_position`
- `shading_cover_position` should be lower than `open_position`
- `resident_sensor` is only allowed to be on/off/true/false
- cover must have a `current_position` attribute
