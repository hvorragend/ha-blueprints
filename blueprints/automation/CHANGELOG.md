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
