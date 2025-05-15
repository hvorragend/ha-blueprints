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

2024.04.08-01:
  - Fixed: Make the shading work even without a helper

2024.05.01-01:
  - Updated: Trigger shading at time_up_early and schedule helper state change, too
  - Fixed: Possibility to ignore actions after manual position changes
  - Added Feature: Force activation of sun shading #49
  - Fixed: Manual shutter movements after a core restart were not always recognised.

2024.05.03-01:
  - Minor editorial changes

2024.05.15-01:
  - Fixed: Do not recognise manual movement if status is unknown
  - Updated: Change the step size for the brightness values to 1
  - Fixed: Made the force function easier with fewer conditions
  - Added: Make it possible to open and close the roller blinds multiple times
  - Added: The forecast sensor can now trigger the sun shading #48
  - Added: Delay between set_cover_position and set_cover_tilt_position.
  - Added: Lockout protection implemented at the start and end of shading. #43/#55 (Attention: Cover may close in the evening after contact is closed again!)
  - Fixed: Retriggering of the shading is possible again. Open/close branches are only started if automation is not already running.

2024.05.15-02:
  - Quick workaround, as opening and closing does not currently work.
  - Minor changes

2024.05.22-01:
  - Added: Separation of the contact sensors for ventilation and lockout protection
    BREAKING CHANGE: Reconfiguration of lockout protection necessary!
  - Updated: Combining the shading triggers. No more problems with waiting times and retriggers.
  - Fixed: Do not close after closing the contact if 'Automatic Closing' is disabled
  - Fixed: Missing shading force trigger
  - Fixed: Prevent trigger with invalid status

2024.05.28-01:
  - Complete restructuring and logic change for shading, lockout protection and ventilation:
      - When the cover is opened, the system checks whether a sun shading is already in place. If this is the case, the cover is not opened but moved directly into the shading position.
      - If the cover is to be closed and the contact is open, either lockout protection or ventilation mode is activated.
      - If the cover is closed and the corresponding contact is opened, the ventilation position is activated.
      - When the sun shading is activated, the lockout protection is taken into account if the contact is open. If the contact is closed, the cover moves back to the shading position.
      - When the sun shading is stopped, the lockout protection is checked. It is also possible to move to the ventilation position when the contact is open. If the contact is closed here, the cover is opened.

      <ins>Summary:</ins> CCA saves the temporary status (ventilation, lockout protection and shading) and the actual target status in the Cover Status Helper.
      - This means that the cover is simply opened or closed as before.
      - And it does <ins>not</ins> always return to the previous state (which may have changed in the meantime).
      - Instead, it switches to the state that should actually be current.
  - Fixed: Incorrect position detection during manual drives if shading_position is smaller than close_position
  - Added: Shading activation before opening. The cover can now move into the shading during the opening process. #4
  - Added: Prevent automatic closing due to the resident sensor #63
  - Added: Option to deactivate time control. This means that the system can now also be controlled exclusively via the brightness and the height of the sun. I
  - <strong>BREAKING CHANGES:</strong>
      - Cover Status Helper is now mandatory for ventilation, lockout protection and shading!
      - Invert the status of some options #61 ("Prevent the cover from being ... several times a day" instead of "Allow the cover to be ... several times a day")

2024.06.04-01:
  - Major GUI Update: Using blueprint sections now (Min-Core-Version: 2024.6.0)

2024.06.05-01:
  - Added: Optional checking workday tomorrow sensor when closing the cover #71
  - Updated: GUI section icons to MDI icons

2024.06.24:
  - Breaking change: 'prevent_higher_position_shading_end' changed to new parameter 'prevent_lowering_when_closing_if_shaded'
  - Added: Limited templates for enabling automation triggers
  - Added: Shading sensor 2 is also checked again during shading
  - Fixed: Occasionally sun shading was performed without checking the weather conditions
  - Fixed: The ventilation position was not set correctly when closing the roller blind
  - Fixed: At the end of sun shading, the system no longer moves to the ventilation position
  - Fixed: Sun shading is now also calculated outside the configured times and can be taken into account when opening.
  - Fixed: Option "Prevent the cover from closing immediately after deactivating the lockout protection"
  - Many thanks to Eimeel and Bostil

2024.06.26:
  - <strong>Breaking change:</strong> The option <em>"Prevent the use of the 'get_forecasts' service (prevent_forecast_service)"</em> has been removed and replaced by the configuration option under <em>"Sun Shading Forecast Type"</em>
  - Fixed: If tomorrow is not a working day, the right time is taken now - #80
  - Fixed: If the blind is moved manually below the shading and ventilation position, this is no longer recognised as closed.
  - Added: Additional Actions After Manual Change - #87
  - Added: You can now decide whether you want to use the hourly or daily weather forecast.
  - Added: It is now possible to reset the manual detection of roller blind movements at 00:01 - #86

2024-06-27:
  - Minor bugfix

2024.06.29:
  - Breaking change: The checkbox introduced in the last update "reset_manual_detection" has been moved to a separate selection. Please reconfigure.
  - Added: Time and timeout in minutes to reset the manual override #95
  - Added: Additional Actions After Override Reset #94
  - Fixed: The cover may also be closed after ventilation if the down mode is not activated
  - Many thanks to crandler for the ideas

2024.06.30:
  - Fixed: Preventing errors and warning on manual execution
  - Fixed: Incorrect time adopted if tomorrow is a working day and today is a weekend

2024.07.06:
  - Fixed: Return to shading after ventilation #43
  - Fixed: When closing the ventilation contact, do not move the roller blind if it is already in the correct position #102
  - Updated: Trigger name renamed to make debugging easier for beginners
  - Added: Additional information on when a Cover Status Helper is required
  - Added: License notification and notice about the new <em>Take Control</em>-feature

2024.07.31:
  - Fixed: Override conditions were incorrect #109
  - Fixed: Faulty timing triggers although they have been deactivated #104
  - Fixed: Removed duplicate line of code without effect #105
  - Fixed: Reset shading status at midnight that is no longer required - but still saved #106
  - Fixed: Empty weather conditions are now taken into account when shading is ended #110
  - Fixed: When the shading is ended, the resident sensor is now also checked so that nobody is woken up #116
  - Updated: All force situations are now fully cross-checked in all choose-branches
  - Added: Save the length of the helper for better debugging #107
  - Added: The ventilation position can now be moved to after the sun shading has ended (if the contact is open)

2024.08.03:
  - Fixed: Helper length analysis template variable warning #120
  - Fixed: New trigger "t_shading_reset" causes errors #119
  - Fixed: "Manual Override" don't work #122 (Thanks to Eimeel)
  - Fixed: Commenting out the check of the position information in the config check #121
  - Fixed: Blinds not opening with resident mode when auto close disabled #115

2024.09.04:
  - Major Update:
      - Complete redesign of the logic behind the contact sensors.
      - Splitting the contact sensors into "Tilted windows" and "Open windows"
      - Lockout protection removed from the automation options
      - Lockout protection can be configured individually
      - <strong>Please reconfigure contacts,  residents and manual override settings!</strong>

  - Major Update:
      - Complete redesign of the shading triggers.
        I have now separated the originally combined triggers again.
        And the waiting time is no longer taken into account in the trigger and also not as a delay in the action sequences.
        Instead, the new trigger time is now saved in the helper.
        This has the wonderful advantage that we can work with several shading triggers again, which do not reset and restart each other.
        Unfortunately, this makes things more complicated in support, as I now need traces for both triggers (pending and execution).
        But I also hope to have fewer customer service calls in the long term.
        In addition, you can now see traces again that were previously not available because they were cancelled directly in the for-wait time.

  - Updated: If you previously used the manual control reset at a certain time, you now have to reconfigure this feature once. I had to rename the variable is_reset_time to is_reset_fixed_time.
  - Added: Config check for schedule helper
  - Added: Sun shading can now be allowed even if a resident is present #131
  - Fixed: A delay is now also taken into account when the sun shading is ended #128
  - Fixed: When checking the end of shading, a True was always output if the weather conditions array was empty #133
  - Fixed: Prevent double triggering if early+late times are identical.

  - Breaking Changes:
      <ins>Removed settings:</ins>
      - "Prevent the cover from closing immediately after deactivating the lockout protection" (prevent_close_after_lockout)
      - "Enable lockout protection" (auto_lockout_protection_enabled)
      - "Contact Sensor Entity For Ventilation" (contact_sensor)
      - "Contact Sensor Entity For Lockout Protectio" (contact_sensor_lockout)
      - "Prevent automatic closing due to the resident sensor" (prevent_closing_by_resident)

      <ins>Please delete the following variables in the YAML code:</ins>
      - prevent_close_after_lockout
      - auto_lockout_protection_enabled
      - contact_sensor
      - contact_sensor_lockout
      - prevent_closing_by_resident
      - is_reset_time (replaces with is_reset_fixed_time)

2024.09.05:
  - Added check for a shading shading start/end time > 0

2024.09.19:
  - Fixed: Fixed some warnings in the log. No influence on functionality #141
  - Fixed: Brightness Down not working #144
  - Fixed: Shutter up after resident on not (always) functional #139

2024.09.25:
  - Fixed: Shutter up in the morning while Resident asleep #145
  - Fixed: Some warnings
  - Minor clean-up work

2024.10.21:
  - Added: The delay values in relation to the contact sensors can now be configured individually
  - Fixed: A problem with the scheduler in connection with the sun height/brightness has been fixed
  - Updated: YAML-Syntax for automations. Minimum version of the core raised to 2024.10.

2024.12.20:
  - Added: Additional Condition For Disabling Ventilation
  - Fixed: Small scheduler fix and description also updated
  - Update: Update of the logic and documentation for the resident sensor #158

2025.04.18:
  - Updated: Just to be more bulletproof, the tilt position control can now be specifically switched on or off. Please activate if necessary. #163
  - Updated: There is no default value for "Sun Shading Forecast Temperature" here now. To not compare the forecast temperature, leave this field empty. #179
  - Added: Allow entities of the switch domain as resident sensor or with the force entities #167
  - Added: New additional actions: Commands can now be executed before opening, closing, shading and ventilation #166
  - Fixed: Fixed problems resetting manual override #184
  - Fixed: Make sure that the reset of the manual override is only executed once #178
  - Fixed: Problems with lockout protection and partial ventilation solved #181
  - Fixed: There was no latest time for closing the cover when the scheduler was used with sun/brightness #170
  - Added: Added Sun elevation examples into the description #175
  - Added: New feature 'Allow opening the cover when resident is still present' #192
  - Breaking change: Please reconfigure "Allow sun protection when resident is still present" ('resident_shading_enabled' was renamed)

2025.05.02-01:
  - Fixed: Also take into account for shading that a door contact only needs to be tested when ventilation mode is switched on #197
  - Fixed: Removed protocol error that occurs during manual execution.
  - Added: Catching an incorrect weather configuration
  - Added: Ability to specify an existing sensor if it already provides daily maximum temperature forecast instead of weather entity #199
  - Added: Add hysteresis for temperature sensor based shading #189

2025.05.02-02:
  - Fixed: A bug has been fixed that caused the shading to be recognized but not executed. But only if shading was only allowed to be executed once a day.

2025.05.04:
  - Added: Allow immediate ending of shading if the sun is out of the defined azimuth or elevation range.
  - Added: Option to close cover instead of opening when shading ends (ideal for awnings)
  - Updated: Note that the weather sensor specification is optional #198

2025.05.07:
  - Fixed: Shading is now also recognized and temporarily stored in the helper if the resident sensor contains the value true. #131
  - Added: Tilt Reposition Feature (Thanks for the pull request, Astado) #196
  - Update: Better textual clarification of what the result of the additional condition should look like #204
  - Update: Only shade the cover when it is not in the shading position. Purely as a precautionary measure in case the target state and actual state do not match.

2025.05.11:
  - Fixed: Fixed bug that the cover can be opened again by the time-up-late-trigger despite existing shading.
  - 
2025.05.12:
  - Fixed: Multiple triggering of a detected shading has skipped the waiting time until execution #206

2025.05.13
  - Fixed: The nightly shading reset has changed the timestamp and therefore a new shading with active 'prevent_shading_multiple_times' can never be executed.

2025.05.14
  - Added: Falling below shading_elevation_max now also triggers Shading Start #193
  - Fixed: When detecting manual position changes, values greater than Ventilation were incorrectly assumed to be Open. This was too wide-ranging.
