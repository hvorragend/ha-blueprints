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
