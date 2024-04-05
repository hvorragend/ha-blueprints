# Changelog

2024.01.29-01:
  - Updated hints
  - Fixed one resident condition (thx to Eimeel)
  - Added version number to json (thx to Eimeel)

2024.01.29-02:
  - Added: Implemented configuration check to perform some basic checks (idea and code by Eimeel)
  - Added: Cover Drive Time
  - A few logic changes

2024.01.29-03:
  - Added config check for sun attributes
  - Fixed: Wrong trigger condition while closing

2024.01.29-04/2024.01.29-05:
  - Updated descriptions

2024.01.30-01/2024.01.30-02:
  - Fixed and extended config check
  - Fixed closing condition. Wrong fix yesterday. Back to the origin. Will check this later.

2024.02.01-01:
  - Minor Layout changes
  - Removed commented out code
  - Fixed closing-condition
  - Fixed cover status helper initialisation and still make the first cover drive possible

2024.02.02-01:
  - *BREAKING CHANGE:* Please reconfigure/rename the variables close_position and shading_position in your blueprint config.
    Old: closed_position - New: close_position
    Old: shading_cover_position - New: shading_position
  - Added tilt positions for open, close and ventilation

2024.02.03-01:
  - Strict separation of the two brightness sensors. The previous problem was that the shading sensor used the same values to open or close the blinds as the normal sensor. Depending on the sensor (different edge, slope, median, filter, etc.), incorrect triggers occur.
    Important: If required, please register both brightness sensors.

2024.02.03-02:
  - Opening the blinds only until time_down_early. Otherwise, overlaps may occur if the brightness values are not set correctly. Avoid bouncing the blinds.

2024.02.06-01:
  - Added: Helper length validation
  - Comprehensive JSON changes / Now multidimensional JSON
  - Roller blind movements can now only be executed once a day when the helpers are used.

2024.02.07-01:
  - Fixed weather.get_forecasts: The response from the service is a dict with the target entities as keys

2024.02.09-01:
  - Streamline the code
  - Added option to enable time control via external schedule helper
  - Added more options for manual time control (drive up - late on non-workdays / drive down early and late on non-workdays)
  - **Possible breaking change**: You should reconfigure the times in your CCA automations!

2024.02.12-01:
  - Allow input_boolean as contact sensors.
  - The state of the contact sensor can be true/on or false/off
  - Fixed time control bug

2024.02.13-01:
  - Fixed potential bug when opening via time control

2024.02.15-01:
  - Fixed timestamp comparison bug
  - Faster checking for manual position changes

2024.02.18-01:
  - Fixed: Schedule open/close-bug
  - Fixed: Next try - faster checking for manual position changes
  - Separate ventilation from lockout protection
  - Added own lockout protection feature
  - Removed door/window chooser (contact_cover_place)

2024.02.18-02:
  - Fixed: Problems with helper json

2024.02.19-01:
  - Added: External trigger to force opening or closing. Useful for Antifreeze, RainProtection or WindProtection.
  - Fixed: Still timing problems occur when recognising manual drives
  - Added: Additional actions for open, close, ventilation, shading start and shading end

2024.02.28-01:
  - Fixed a nasty bug in the helper detection.
  - Fixed the warning: AttributeError: ‘list’ object has no attribute ‘lower’

2024.02.28-02:
  - Fixed: Float values were incorrectly compared as integers. This fixed problems with sun-elevation and brightness.

2024.03.01-01:
  - Roller blinds may only be closed once after Time_Down_Late. Previously, the entire day was checked.

2024.03.11-01:
  - Added various options for fine adjustment
  - Possibility to ignore actions after manual position changes
  - Only compare such positions if the mode has been activated accordingly
  - Avoid status change from 'unavailable'
  - Allow delay in ventilation mode
  - Fixed: Shading should not be activated when ventilation mode is active
  - Fixed: Closing the door contact should always lower the roller
  - Instead of cover helper and position detection working against each other, the two can now complement each other.
  - Manual detection adjusted. Positions 0% and 100% always result in close/open regardless of the configuration.
  - Forcing a status is now also automatically used as a negative condition in other queries.

2024.03.11-02:
  - Completely new structure of the various choose-branches
  - Relocation of some conditions to the sequence section
  - Redesign of the ventilation mode
  - Added: Additional Condition For Ventilation #33
  - Added: Force Ventilation #28

2024.03.12-01:
  - Fixed #29: Do not compare forecast temp with temp-sensor1 for shading

2024.03.12-02:
  - Added #20: Allow ventilation not only in closed state, but also when the position is below the ventilation position.
  - Bugfixes when comparing positions

2024.03.14-01:
  - Fixed: Ventilation mode could always be started by mistake.
  - Fixing helper length check. Thx to crandler.

2024.03.21-01:
  - **Breaking change** in the schedule helper usage! You can find the details in the section "Selection of time control options".
  - New: Reduction of triggers and thus avoidance of overlaps due to running delays (fixes #40)
  - New: Added possibility to disable the use of 'set_cover_position' and 'set_cover_tilt_position' and only use the additional actions
  - Fixed: Shading Forecast Weather Conditions
  - Fixed: Ventilation mode should not only be ended in the evening, but whenever it is not yet daytime.
  - Fixed: Added the ventilation mode activation on closing down again
  - Try to avoid overlaps in the execution of the automation if several triggers are triggered shortly after each other.
  - Fixed: Optional weather conditions for "shading in" #41

2024.04.05-01:
  - Update: Forecast Temperature below 0 possible
  - Delay lines minimally changed
  - Added: Allow shading to activate multiple times a day #44
  - Fixed: Ventilation is usually activated too often.
