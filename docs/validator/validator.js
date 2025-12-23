/**
 * CCA Configuration Validator   
 * Version: 2025.12.17
 * Validates Home Assistant Cover Control Automation Blueprint configurations
 */

class CCAValidator {
    constructor() {
        this.config = null;
        this.issues = [];
        this.warnings = [];
        this.info = [];
        
        // Valid parameters (current version 2025.12.17)
        this.validParams = new Set([
            // Blueprint/Automation meta fields (ignored in validation)
            'alias', 'description', 'trace', 'use_blueprint', 'id', 'mode', 'max', 'max_exceeded',
            
            // Core
            'blind', 'cover_type', 'auto_options', 'individual_config',
            
            // Helper
            'cover_status_options', 'cover_status_helper', 'drive_time',
            
            // Positions
            'position_source', 'custom_position_sensor',
            'open_position', 'close_position', 'ventilate_position', 'shading_position',
            'position_tolerance',
            
            // Tilt
            'cover_tilt_wait_mode', 'cover_tilt_wait_timeout', 'tilt_delay',
            'cover_tilt_config', 'cover_tilt_reposition_config',
            'open_tilt_position', 'close_tilt_position', 'ventilate_tilt_position',
            'shading_tilt_position_0', 'shading_tilt_position_1', 'shading_tilt_position_2', 'shading_tilt_position_3',
            'shading_tilt_elevation_1', 'shading_tilt_elevation_2', 'shading_tilt_elevation_3',
            
            // Time
            'time_control',
            'time_up_early', 'time_up_early_non_workday', 'time_up_late', 'time_up_late_non_workday',
            'time_down_early', 'time_down_early_non_workday', 'time_down_late', 'time_down_late_non_workday',
            'workday_sensor', 'workday_sensor_tomorrow',
            
            // Calendar
            'calendar_entity', 'calendar_open_title', 'calendar_close_title',
            
            // Brightness
            'default_brightness_sensor', 'brightness_time_duration',
            'brightness_up', 'brightness_down', 'brightness_hysteresis',
            
            // Sun
            'default_sun_sensor', 'sun_time_duration',
            'sun_elevation_up', 'sun_elevation_down',
            'sun_elevation_up_sensor', 'sun_elevation_down_sensor',
            
            // Contacts/Ventilation
            'contact_window_opened', 'contact_window_tilted',
            'lockout_tilted_options', 'auto_ventilate_options',
            'contact_delay_trigger', 'contact_delay_status',
            
            // Shading - Basic
            'shading_azimuth_start', 'shading_azimuth_end',
            'shading_elevation_min', 'shading_elevation_max',
            'shading_brightness_sensor',
            'shading_sun_brightness_start', 'shading_sun_brightness_end', 'shading_sun_brightness_hysteresis',
            
            // Shading - Temperature
            'shading_temperatur_sensor1', 'shading_min_temperatur1', 'shading_temperature_hysteresis1',
            'shading_temperatur_sensor2', 'shading_min_temperatur2', 'shading_temperature_hysteresis2',
            
            // Shading - Forecast
            'shading_forecast_sensor', 'shading_forecast_temp_sensor', 'shading_forecast_type',
            'shading_forecast_temp', 'shading_forecast_temp_hysteresis',
            'shading_weather_conditions', 'shading_config',
            
            // Shading - Conditions
            'shading_conditions_start_and', 'shading_conditions_start_or',
            'shading_conditions_end_and', 'shading_conditions_end_or',
            
            // Shading - Timing
            'shading_waitingtime_start', 'shading_waitingtime_end',
            'shading_start_max_duration', 'shading_end_max_duration',
            'shading_end_immediate_by_sun_position',
            
            // Resident
            'resident_sensor', 'resident_config',
            
            // Manual Override
            'ignore_after_manual_config', 'reset_override_config',
            'reset_override_time', 'reset_override_timeout',
            
            // Delays
            'drive_delay_fix', 'drive_delay_random',
            
            // Force
            'auto_recover_after_force',
            'auto_up_force', 'auto_down_force', 'auto_ventilate_force', 'auto_shading_start_force',
            
            // Conditions
            'auto_global_condition',
            'auto_up_condition', 'auto_down_condition',
            'auto_ventilate_condition', 'auto_ventilate_end_condition',
            'auto_shading_start_condition', 'auto_shading_tilt_condition', 'auto_shading_end_condition',
            
            // Actions
            'auto_up_action', 'auto_up_action_before',
            'auto_down_action', 'auto_down_action_before',
            'auto_ventilate_action', 'auto_ventilate_action_before',
            'auto_shading_start_action', 'auto_shading_start_action_before',
            'auto_shading_end_action', 'auto_shading_end_action_before',
            'auto_manual_action', 'auto_override_reset_action',
            
            // Config Check
            'check_config', 'check_config_debuglevel'
        ]);
        
        // Parameters that should be ignored completely (no warnings)
        this.ignoredParams = new Set([
            'alias', 'description', 'trace', 'use_blueprint', 'id', 'mode', 'max', 'max_exceeded'
        ]);
        
        // Deprecated/Removed parameters with migration info
        this.deprecatedParams = {
            'shading_start_behavior': {
                removed: '2025.12.17',
                replacement: 'shading_start_max_duration',
                migration: 'Replace with shading_start_max_duration: "trigger_reset" → 0, "trigger_periodic" → 3600-7200 seconds'
            },
            'is_shading_end_immediate_by_sun_position': {
                removed: '2025.12.17',
                replacement: null,
                migration: 'This parameter has been removed. The functionality is now always active for sun position.'
            },
            'shading_end_behavior': {
                removed: '2025.12.17',
                replacement: null,
                migration: 'Covers now always return to open_position after shading ends.'
            },
            'time_schedule_helper': {
                removed: '2025.12.17',
                replacement: 'calendar_entity',
                migration: 'Use calendar_entity with time_control: time_control_calendar instead'
            }
        };
        
        // Required parameters (must be configured, no defaults)
        this.requiredParams = {
            'blind': { category: 'Core', description: 'Cover entity to control - REQUIRED' }
        };
        
        // Optional but recommended parameters
        this.recommendedParams = {
            'default_sun_sensor': { category: 'Sun', description: 'Sun sensor for position-based control' },
            'time_up_early': { category: 'Time', description: 'Morning opening time' },
            'time_down_late': { category: 'Time', description: 'Evening closing time' }
        };
    }

    validate(yamlText) {
        this.issues = [];
        this.warnings = [];
        this.info = [];

        try {
            const rawConfig = jsyaml.load(yamlText);
            this.config = this.extractConfig(rawConfig);
            
            if (!this.config) {
                this.addError('Could not parse configuration. Expected either a blueprint or an automation configuration.');
                return this.getResults();
            }
            
            this.validateParameterNames();
            this.validateTimeConfiguration();
            this.validatePositions();
            this.validateShadingThresholds();
            this.validateShadingConditions();
            this.validateDynamicSunElevation();
            this.validateCalendarConfiguration();
            this.validatePositionSource();
            this.validateHelperConfiguration();
            this.validateTiltFeatures();
            this.validateTimingValues();
            this.validateForceEntities();
            this.checkMissingParameters();

            return this.getResults();
        } catch (error) {
            console.error('Validation error:', error);
            return {
                valid: false,
                errors: [{ severity: 'error', message: `YAML Parse Error: ${error.message}` }],
                warnings: [],
                info: []
            };
        }
    }

    validateParameterNames() {
        const configKeys = Object.keys(this.config).filter(key => !this.ignoredParams.has(key));
        
        for (const [param, info] of Object.entries(this.deprecatedParams)) {
            if (configKeys.includes(param)) {
                let message = `⚠️ DEPRECATED: '${param}' was removed in version ${info.removed}.`;
                if (info.replacement) {
                    message += ` Use '${info.replacement}' instead.`;
                }
                message += ` Migration: ${info.migration}`;
                this.addWarning(message);
            }
        }
        
        const unknownParams = configKeys.filter(key => 
            !this.validParams.has(key) && 
            !this.deprecatedParams.hasOwnProperty(key) &&
            !this.ignoredParams.has(key)
        );
        
        if (unknownParams.length > 0) {
            unknownParams.forEach(param => {
                const suggestion = this.findClosestMatch(param);
                if (suggestion) {
                    this.addWarning(`❓ Unknown parameter '${param}'. Did you mean '${suggestion}'?`);
                } else {
                    this.addWarning(`❓ Unknown parameter '${param}'. This parameter is not recognized by CCA.`);
                }
            });
        }
    }

    checkMissingParameters() {
        for (const [param, info] of Object.entries(this.requiredParams)) {
            if (!this.config[param] || 
                (Array.isArray(this.config[param]) && this.config[param].length === 0)) {
                this.addError(`❌ ${info.category}: '${param}' is REQUIRED - ${info.description}`);
            }
        }
        
        const missingRecommended = [];
        for (const [param, info] of Object.entries(this.recommendedParams)) {
            if (!this.config[param] || 
                (Array.isArray(this.config[param]) && this.config[param].length === 0)) {
                missingRecommended.push({ param, ...info });
            }
        }
        
        if (missingRecommended.length > 0) {
            const grouped = {};
            missingRecommended.forEach(item => {
                if (!grouped[item.category]) grouped[item.category] = [];
                grouped[item.category].push(item);
            });
            
            for (const [category, items] of Object.entries(grouped)) {
                const params = items.map(i => `'${i.param}' (${i.description})`).join(', ');
                this.addInfo(`ℹ️ ${category}: Using blueprint defaults for: ${params}`);
            }
        }
        
        const autoOptions = this.config.auto_options || [];
        
        if (autoOptions.includes('auto_shading_enabled') || autoOptions.includes('auto_ventilate_enabled')) {
            if (!this.config.cover_status_helper || this.config.cover_status_helper.length === 0) {
                this.addWarning('🦮 Shading or Ventilation enabled but no cover_status_helper configured. These features require a helper to work properly.');
            }
        }
        
        if (autoOptions.includes('auto_shading_enabled')) {
            if (!this.config.shading_conditions_start_and && !this.config.shading_conditions_start_or) {
                this.addInfo('ℹ️ Shading: No custom conditions configured. Using default AND/OR conditions from blueprint.');
            }
            if (!this.config.shading_start_max_duration) {
                this.addInfo('ℹ️ Shading: shading_start_max_duration not set. Using blueprint default: 7200s (2 hours).');
            }
        }
        
        if (autoOptions.includes('auto_sun_enabled')) {
            if (!this.config.sun_elevation_up_sensor && !this.config.sun_elevation_down_sensor) {
                this.addInfo('ℹ️ Sun Control: Using fixed elevation values (not dynamic sensors).');
            }
        }
    }

    findClosestMatch(input) {
        let bestMatch = null;
        let bestDistance = Infinity;
        
        for (const validParam of this.validParams) {
            const distance = this.levenshteinDistance(input.toLowerCase(), validParam.toLowerCase());
            if (distance < bestDistance && distance <= 3) {
                bestDistance = distance;
                bestMatch = validParam;
            }
        }
        
        return bestMatch;
    }

    levenshteinDistance(str1, str2) {
        const matrix = [];
        for (let i = 0; i <= str2.length; i++) {
            matrix[i] = [i];
        }
        for (let j = 0; j <= str1.length; j++) {
            matrix[0][j] = j;
        }
        for (let i = 1; i <= str2.length; i++) {
            for (let j = 1; j <= str1.length; j++) {
                if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
                    matrix[i][j] = matrix[i - 1][j - 1];
                } else {
                    matrix[i][j] = Math.min(
                        matrix[i - 1][j - 1] + 1,
                        matrix[i][j - 1] + 1,
                        matrix[i - 1][j] + 1
                    );
                }
            }
        }
        return matrix[str2.length][str1.length];
    }

    extractConfig(rawConfig) {
        // 1. Blueprint file: blueprint.input
        if (rawConfig.blueprint && rawConfig.blueprint.input) {
            this.addInfo('📋 Blueprint file detected - extracting default values');
            return this.extractFromBlueprint(rawConfig.blueprint.input);
        }
        
        // 2. Automation with use_blueprint: use_blueprint.input
        if (rawConfig.use_blueprint && rawConfig.use_blueprint.input) {
            this.addInfo('🤖 Automation configuration detected - extracting from use_blueprint.input');
            return rawConfig.use_blueprint.input;
        }
        
        // 3. Legacy format: input at root level
        if (rawConfig.input && typeof rawConfig.input === 'object') {
            this.addInfo('📝 Legacy automation format - extracting from input');
            return rawConfig.input;
        }
        
        // 4. Flat configuration (direct parameters)
        if (rawConfig.blind || rawConfig.open_position || rawConfig.cover_type) {
            this.addInfo('📝 Flat configuration format detected');
            return rawConfig;
        }
        
        // 5. Unknown format
        this.addWarning('⚠️ Unknown configuration format. Expected blueprint, automation, or flat config.');
        return rawConfig;
    }


    extractFromBlueprint(input) {
        const config = {};
        const extractDefaults = (obj) => {
            for (const [key, value] of Object.entries(obj)) {
                if (value && typeof value === 'object') {
                    if ('default' in value) {
                        config[key] = value.default;
                    }
                    if ('input' in value) {
                        extractDefaults(value.input);
                    }
                }
            }
        };
        extractDefaults(input);
        return config;
    }

    getResults() {
        return {
            valid: this.issues.length === 0,
            errors: this.issues,
            warnings: this.warnings,
            info: this.info
        };
    }

    validateTimeConfiguration() {
        const c = this.config;
        if (!c.time_control || c.time_control === 'time_control_disabled') {
            this.addInfo('⏰ Time control is disabled - skipping time validation');
            return;
        }
        if (c.time_control === 'time_control_calendar') {
            this.addInfo('📅 Calendar control enabled - time inputs not used');
            return;
        }
        this.checkTimeOrder('time_up_early', 'time_up_late', 'time_up_early should be earlier than time_up_late');
        this.checkTimeOrder('time_up_early_non_workday', 'time_up_late_non_workday', 'time_up_early_non_workday should be earlier than time_up_late_non_workday');
        this.checkTimeOrder('time_down_early', 'time_down_late', 'time_down_early should be earlier than time_down_late');
        this.checkTimeOrder('time_down_early_non_workday', 'time_down_late_non_workday', 'time_down_early_non_workday should be earlier than time_down_late_non_workday');
    }

    validatePositions() {
        const c = this.config;
        
        if (c.open_position === undefined || c.open_position === null) {
            this.addInfo('ℹ️ Positions: open_position not configured. Using blueprint default (100 for blinds, 0 for awnings).');
            return;
        }
        
        const isAwning = c.cover_type === 'awning';
        const tolerance = c.position_tolerance || 0;

        this.checkRange('open_position', 0, 100);
        this.checkRange('close_position', 0, 100);
        this.checkRange('shading_position', 0, 100);
        this.checkRange('ventilate_position', 0, 100);

        if (isAwning) {
            this.addInfo('☂️ Awning mode detected (0%=retracted, 100%=extended)');
            this.checkPositionOrder('open_position', 'close_position', '<', 'For awnings: open_position must be lower than close_position');
            if (c.shading_position !== undefined) {
                this.checkPositionOrder('shading_position', 'close_position', '<', 'For awnings: shading_position must be lower than close_position');
                this.checkPositionOrder('open_position', 'shading_position', '<', 'For awnings: open_position must be lower than shading_position');
            }
        } else {
            this.addInfo('🪟 Blind/Roller Shutter mode detected (0%=closed, 100%=open)');
            this.checkPositionOrder('open_position', 'close_position', '>', 'For blinds: open_position must be higher than close_position');
            if (c.shading_position !== undefined) {
                this.checkPositionOrder('shading_position', 'close_position', '>', 'For blinds: shading_position must be higher than close_position');
                this.checkPositionOrder('open_position', 'shading_position', '>', 'For blinds: open_position must be higher than shading_position');
            }
        }
        this.checkPositionOverlap(tolerance);
    }

    validateShadingThresholds() {
        const c = this.config;
        if (!this.isShadingEnabled()) return;
        if (c.shading_azimuth_start !== undefined && c.shading_azimuth_end !== undefined) {
            if (c.shading_azimuth_start >= c.shading_azimuth_end) {
                this.addError(`shading_azimuth_start (${c.shading_azimuth_start}°) should be lower than shading_azimuth_end (${c.shading_azimuth_end}°)`);
            }
        }
        if (c.shading_elevation_min !== undefined && c.shading_elevation_max !== undefined) {
            if (c.shading_elevation_min >= c.shading_elevation_max) {
                this.addError(`shading_elevation_min (${c.shading_elevation_min}°) should be lower than shading_elevation_max (${c.shading_elevation_max}°)`);
            }
        }
        if (c.shading_sun_brightness_start !== undefined && c.shading_sun_brightness_end !== undefined) {
            if (c.shading_sun_brightness_start <= c.shading_sun_brightness_end) {
                this.addError(`shading_sun_brightness_start (${c.shading_sun_brightness_start}lx) should be higher than shading_sun_brightness_end (${c.shading_sun_brightness_end}lx)`);
            }
        }
    }
    
    validateShadingConditions() {
        const c = this.config;
        if (!this.isShadingEnabled()) return;
        
        const startAnd = c.shading_conditions_start_and || [];
        const startOr = c.shading_conditions_start_or || [];
        const endAnd = c.shading_conditions_end_and || [];
        const endOr = c.shading_conditions_end_or || [];
        
        // Blueprint defaults
        const hasStartAndDefault = c.shading_conditions_start_and === undefined;
        const hasEndOrDefault = c.shading_conditions_end_or === undefined;
        
        // START CONDITIONS VALIDATION
        if (startAnd.length === 0 && startOr.length === 0) {
            if (hasStartAndDefault) {
                // Using blueprint default for START AND
                this.addInfo('ℹ️ Shading START: Using blueprint default (7 AND conditions: azimuth, elevation, brightness, temp1, temp2, forecast_temp, forecast_weather)');
            } else {
                // Both explicitly configured as empty - ERROR
                this.addError('🚫 Shading enabled but no START conditions selected. Shading will never activate');
            }
        } else {
            // Show which lists are configured
            const startInfo = [];
            if (startAnd.length > 0) {
                startInfo.push(`${startAnd.length} AND condition(s)`);
            } else if (hasStartAndDefault) {
                startInfo.push('7 AND conditions (blueprint default)');
            }
            if (startOr.length > 0) {
                startInfo.push(`${startOr.length} OR condition(s)`);
            }
            if (startInfo.length > 0) {
                this.addInfo(`✅ Shading START: ${startInfo.join(' + ')}`);
            }
        }
        
        // END CONDITIONS VALIDATION
        if (endAnd.length === 0 && endOr.length === 0) {
            if (hasEndOrDefault) {
                // Using blueprint default for END OR
                this.addInfo('ℹ️ Shading END: Using blueprint default (7 OR conditions: azimuth, elevation, brightness, temp1, temp2, forecast_temp, forecast_weather)');
            } else {
                // Both explicitly configured as empty - WARNING
                this.addWarning('⏰ No END conditions selected. Shading only ends at midnight reset');
            }
        } else {
            // Show which lists are configured
            const endInfo = [];
            if (endAnd.length > 0) {
                endInfo.push(`${endAnd.length} AND condition(s)`);
            }
            if (endOr.length > 0) {
                endInfo.push(`${endOr.length} OR condition(s)`);
            } else if (hasEndOrDefault) {
                endInfo.push('7 OR conditions (blueprint default)');
            }
            if (endInfo.length > 0) {
                this.addInfo(`✅ Shading END: ${endInfo.join(' + ')}`);
            }
        }
        
        // Check for duplicates between AND and OR lists (only if both have values)
        if (startAnd.length > 0 && startOr.length > 0) {
            const startDuplicates = startAnd.filter(c => startOr.includes(c));
            if (startDuplicates.length > 0) {
                this.addError(`❌ Same START condition in both AND and OR lists: ${startDuplicates.join(', ')}`);
            }
        }
        
        if (endAnd.length > 0 && endOr.length > 0) {
            const endDuplicates = endAnd.filter(c => endOr.includes(c));
            if (endDuplicates.length > 0) {
                this.addError(`❌ Same END condition in both AND and OR lists: ${endDuplicates.join(', ')}`);
            }
        }
    }

    validateDynamicSunElevation() {
        const c = this.config;
        if (c.sun_elevation_up_sensor && c.sun_elevation_down_sensor) {
            this.addInfo('🌅 Using dynamic sun elevation sensors for both up and down thresholds');
        } else if (c.sun_elevation_up_sensor || c.sun_elevation_down_sensor) {
            this.addWarning('Using dynamic sensor for only one threshold. Consider using for both');
        }
    }

    validateCalendarConfiguration() {
        const c = this.config;
        if (c.time_control !== 'time_control_calendar') return;
        if (!c.calendar_entity || c.calendar_entity.length === 0) {
            this.addError('Calendar control enabled but no calendar entity selected');
        }
        const openTitle = c.calendar_open_title || 'Open Cover';
        const closeTitle = c.calendar_close_title || 'Close Cover';
        if (openTitle === closeTitle) {
            this.addError(`Open and Close event titles are identical ('${openTitle}')`);
        }
    }

    validatePositionSource() {
        const c = this.config;
        if (c.position_source === 'custom_sensor' && (!c.custom_position_sensor || c.custom_position_sensor.length === 0)) {
            this.addError('Custom position sensor selected but not configured');
        }
    }

    validateHelperConfiguration() {
        const c = this.config;
        const autoOptions = c.auto_options || [];
        const needsHelper = autoOptions.includes('auto_shading_enabled') || autoOptions.includes('auto_ventilate_enabled');
        
        if (needsHelper && c.cover_status_options !== 'cover_helper_enabled') {
            this.addWarning('🦮 Shading or Ventilation requires a cover status helper. Set cover_status_options to "cover_helper_enabled" and configure cover_status_helper.');
        }
        
        if (c.cover_status_options === 'cover_helper_enabled' && (!c.cover_status_helper || c.cover_status_helper.length === 0)) {
            this.addError('❌ Helper enabled (cover_status_options) but cover_status_helper entity not configured.');
        }
    }

    validateTiltFeatures() {
        const c = this.config;
        if (c.cover_type === 'awning' && c.cover_tilt_config === 'cover_tilt_enabled') {
            this.addWarning('☂️ Tilt features are not available for awnings');
        }
        if (c.tilt_delay && c.tilt_delay > 60) {
            this.addWarning(`Tilt delay (${c.tilt_delay}s) is very long. Recommended: ≤10s`);
        }
    }

    validateTimingValues() {
        const c = this.config;
        if (c.drive_time !== undefined) {
            if (c.drive_time < 5) {
                this.addWarning(`⏱️ Cover drive time (${c.drive_time}s) is too short. Min: 5s`);
            }
            if (c.drive_time > 300) {
                this.addWarning(`⏱️ Cover drive time (${c.drive_time}s) is very long. Max: 300s`);
            }
        }
        const totalDelay = (c.drive_delay_fix || 0) + (c.drive_delay_random || 0);
        if (totalDelay > 600) {
            this.addWarning(`⏱️ Combined delay (${totalDelay}s) is very high`);
        }
    }

    validateForceEntities() {
        const c = this.config;
        let count = 0;
        if (c.auto_up_force && c.auto_up_force.length > 0) count++;
        if (c.auto_down_force && c.auto_down_force.length > 0) count++;
        if (c.auto_ventilate_force && c.auto_ventilate_force.length > 0) count++;
        if (c.auto_shading_start_force && c.auto_shading_start_force.length > 0) count++;
        if (count > 1) {
            this.addWarning('⚡ Multiple force entities configured. Only one can be active at a time');
        }
    }

    isShadingEnabled() {
        const autoOptions = this.config.auto_options || [];
        return autoOptions.includes('auto_shading_enabled');
    }

    checkTimeOrder(time1Key, time2Key, message) {
        const t1 = this.config[time1Key];
        const t2 = this.config[time2Key];
        if (!t1 || !t2) return;
        if (this.parseTime(t1) >= this.parseTime(t2)) {
            this.addError(`${message} (${t1} >= ${t2})`);
        }
    }

    checkRange(key, min, max) {
        const val = this.config[key];
        if (val === undefined) return;
        if (val < min || val > max) {
            this.addError(`${key} (${val}) must be between ${min} and ${max}`);
        }
    }

    checkPositionOrder(key1, key2, operator, message) {
        const val1 = this.config[key1];
        const val2 = this.config[key2];
        if (val1 === undefined || val2 === undefined) return;
        const valid = operator === '>' ? val1 > val2 : val1 < val2;
        if (!valid) {
            this.addError(`${message} (${key1}=${val1}, ${key2}=${val2})`);
        }
    }

    checkPositionOverlap(tolerance) {
        const positions = {
            open: this.config.open_position,
            close: this.config.close_position,
            shading: this.config.shading_position,
            ventilate: this.config.ventilate_position
        };
        Object.keys(positions).forEach(key => {
            if (positions[key] === undefined) delete positions[key];
        });
        const posArray = Object.entries(positions);
        for (let i = 0; i < posArray.length; i++) {
            for (let j = i + 1; j < posArray.length; j++) {
                const [name1, val1] = posArray[i];
                const [name2, val2] = posArray[j];
                if (Math.abs(val1 - val2) <= tolerance * 2) {
                    this.addWarning(`${name1}_position (${val1}%) and ${name2}_position (${val2}%) overlap with tolerance ${tolerance}%`);
                }
            }
        }
    }

    parseTime(timeStr) {
        if (typeof timeStr !== 'string') return 0;
        const parts = timeStr.split(':');
        return (parseInt(parts[0]) || 0) * 60 + (parseInt(parts[1]) || 0);
    }

    addError(message) {
        this.issues.push({ severity: 'error', message });
    }

    addWarning(message) {
        this.warnings.push({ severity: 'warning', message });
    }

    addInfo(message) {
        this.info.push({ severity: 'info', message });
    }
}

/**
 * UI Controller
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('CCA Validator loaded');
    
    const validator = new CCAValidator();
    const fileUpload = document.getElementById('file-upload');
    const yamlInput = document.getElementById('yaml-input');
    const validateBtn = document.getElementById('validate-btn');
    const clearBtn = document.getElementById('clear-btn');
    const pasteBtn = document.getElementById('paste-btn');
    const exportBtn = document.getElementById('export-btn');
    const filterSelect = document.getElementById('filter-select');
    const validationStatus = document.getElementById('validation-status');
    const resultsSection = document.getElementById('results-section');
    const summary = document.getElementById('summary');
    const issuesList = document.getElementById('issues-list');
    
    let currentResult = null;
    let currentFilter = 'all';

    fileUpload.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                yamlInput.value = e.target.result;
                validateConfiguration();
            };
            reader.readAsText(file);
        }
    });

    validateBtn.addEventListener('click', function() {
        console.log('Validate button clicked');
        validateConfiguration();
    });

    document.querySelectorAll('.example-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const example = this.dataset.example;
            loadExample(example);
        });
    });

    clearBtn.addEventListener('click', function() {
        if (confirm('Clear the current configuration?')) {
            yamlInput.value = '';
            yamlInput.focus();
            resultsSection.classList.remove('visible');
            resultsSection.classList.add('hidden');
            currentResult = null;
            validationStatus.textContent = '';
            exportBtn.style.display = 'none';
            filterSelect.value = 'all';
            currentFilter = 'all';
        }
    });

    pasteBtn.addEventListener('click', async function() {
        try {
            const text = await navigator.clipboard.readText();
            if (text) {
                yamlInput.value = text;
                const originalText = pasteBtn.textContent;
                pasteBtn.textContent = '✓ Pasted!';
                setTimeout(() => {
                    pasteBtn.textContent = originalText;
                    validateConfiguration();
                }, 500);
            }
        } catch (err) {
            console.error('Failed to paste:', err);
            alert('Failed to paste from clipboard. Please paste manually with Ctrl+V');
        }
    });

    exportBtn.addEventListener('click', function() {
        if (currentResult) {
            exportResults(currentResult);
        }
    });

    filterSelect.addEventListener('change', function() {
        currentFilter = this.value;
        if (currentResult) {
            displayResults(currentResult);
        }
    });

    // Keyboard shortcuts
    yamlInput.addEventListener('keydown', function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            validateConfiguration();
        }
    });

    function validateConfiguration() {
        console.log('Starting validation...');
        const yamlText = yamlInput.value.trim();
        
        if (!yamlText) {
            validationStatus.textContent = '⚠️ Please provide a configuration to validate';
            validationStatus.style.color = 'var(--accent-yellow)';
            return;
        }

        // Show loading state
        validateBtn.disabled = true;
        validateBtn.innerHTML = '<span class="loading"></span>Validating...';
        validationStatus.textContent = '⏳ Validating configuration...';
        validationStatus.style.color = 'var(--accent-blue)';

        // Use setTimeout to allow UI to update before heavy computation
        setTimeout(() => {
            try {
                const startTime = performance.now();
                const result = validator.validate(yamlText);
                const duration = ((performance.now() - startTime) / 1000).toFixed(2);
                
                console.log('Validation result:', result);
                currentResult = result;
                displayResults(result);
                
                validationStatus.textContent = `✓ Validated in ${duration}s`;
                validationStatus.style.color = result.valid ? 'var(--accent-green)' : 'var(--accent-yellow)';
            } catch (error) {
                console.error('Validation error:', error);
                validationStatus.textContent = '❌ Validation error: ' + error.message;
                validationStatus.style.color = 'var(--accent-red)';
                alert('Error during validation: ' + error.message);
            } finally {
                validateBtn.disabled = false;
                validateBtn.textContent = '✓ Validate Configuration';
            }
        }, 10);
    }

    function displayResults(result) {
        resultsSection.classList.remove('hidden');
        resultsSection.classList.add('visible');
        
        // Update filter select to show counts
        filterSelect.innerHTML = `
            <option value="all">All Issues (${result.errors.length + result.warnings.length + result.info.length})</option>
            <option value="error">Errors (${result.errors.length})</option>
            <option value="warning">Warnings (${result.warnings.length})</option>
            <option value="info">Info (${result.info.length})</option>
        `;
        filterSelect.value = currentFilter;
        
        summary.className = 'summary ' + (result.valid ? 'valid' : 'invalid');
        summary.innerHTML = `
            <h3>${result.valid ? '✅ Configuration Valid' : '❌ Issues Found'}</h3>
            <p>
                ${result.errors.length} error(s), 
                ${result.warnings.length} warning(s), 
                ${result.info.length} info message(s)
            </p>
        `;

        issuesList.innerHTML = '';
        
        let allIssues = [
            ...result.errors.map(e => ({...e, severity: 'error'})),
            ...result.warnings.map(w => ({...w, severity: 'warning'})),
            ...result.info.map(i => ({...i, severity: 'info'}))
        ];
        
        // Apply filter
        if (currentFilter !== 'all') {
            allIssues = allIssues.filter(issue => issue.severity === currentFilter);
        }
        
        if (allIssues.length === 0) {
            if (currentFilter === 'all') {
                issuesList.innerHTML = '<div class="no-issues">✨ No issues found! Your configuration looks good.</div>';
            } else {
                issuesList.innerHTML = `<div class="no-issues">No ${currentFilter} issues found.</div>`;
            }
        } else {
            // Sort: errors first, then warnings, then info
            allIssues.sort((a, b) => {
                const order = { 'error': 0, 'warning': 1, 'info': 2 };
                return order[a.severity] - order[b.severity];
            });
            
            allIssues.forEach(issue => {
                const div = document.createElement('div');
                div.className = `issue ${issue.severity}`;
                div.innerHTML = `
                    <span class="severity-icon">${getSeverityIcon(issue.severity)}</span>
                    <div class="issue-content">
                        <div class="issue-message">${escapeHtml(issue.message)}</div>
                    </div>
                `;
                issuesList.appendChild(div);
            });
        }

        // Show/hide export button
        exportBtn.style.display = allIssues.length > 0 ? 'inline-block' : 'none';

        resultsSection.scrollIntoView({ behavior: 'smooth' });
    }

    function exportResults(result) {
        const timestamp = new Date().toISOString();
        const report = `CCA Configuration Validation Report
Generated: ${new Date().toLocaleString()}
${'='.repeat(50)}

Status: ${result.valid ? '✅ VALID' : '❌ INVALID'}

Summary:
- Errors: ${result.errors.length}
- Warnings: ${result.warnings.length}
- Info Messages: ${result.info.length}

${result.errors.length > 0 ? `\nERRORS:\n${'-'.repeat(50)}\n${result.errors.map((e, i) => `${i + 1}. ${e.message}`).join('\n')}\n` : ''}
${result.warnings.length > 0 ? `\nWARNINGS:\n${'-'.repeat(50)}\n${result.warnings.map((w, i) => `${i + 1}. ${w.message}`).join('\n')}\n` : ''}
${result.info.length > 0 ? `\nINFO:\n${'-'.repeat(50)}\n${result.info.map((info, i) => `${i + 1}. ${info.message}`).join('\n')}\n` : ''}

${result.valid ? '\n✨ Configuration is valid and ready to use!' : '\n⚠️ Please fix the errors before deploying.'}

---
Generated by CCA Configuration Validator
`;

        const blob = new Blob([report], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `cca-validation-${timestamp.slice(0, 10)}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    }

    function getSeverityIcon(severity) {
        const icons = { 'error': '🔴', 'warning': '⚠️', 'info': 'ℹ️' };
        return icons[severity] || '';
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function loadExample(type) {
        const examples = {
            basic: `# Basic Blind Configuration
blind: cover.example_blind
cover_type: blind
open_position: 100
close_position: 0
shading_position: 25
ventilate_position: 30
position_tolerance: 2

time_control: time_control_input
time_up_early: "07:00:00"
time_up_late: "08:00:00"
time_down_early: "20:00:00"
time_down_late: "22:00:00"

auto_options:
  - auto_up_enabled
  - auto_down_enabled`,

            advanced: `# Advanced with Shading
blind: cover.example_blind
cover_type: blind
open_position: 100
close_position: 0
shading_position: 25
ventilate_position: 30

time_control: time_control_input
time_up_early: "06:30:00"
time_up_late: "08:00:00"
time_down_early: "18:00:00"
time_down_late: "22:00:00"

auto_options:
  - auto_up_enabled
  - auto_down_enabled
  - auto_shading_enabled
  - auto_sun_enabled

# Helper required for shading
cover_status_options: cover_helper_enabled
cover_status_helper: input_text.example_cover_status

# Sun sensor for shading
default_sun_sensor: sun.sun

# Shading configuration
shading_azimuth_start: 90
shading_azimuth_end: 270
shading_elevation_min: 25
shading_elevation_max: 90
shading_sun_brightness_start: 35000
shading_sun_brightness_end: 25000

# Shading brightness sensor
shading_brightness_sensor: sensor.example_brightness

# Shading conditions
shading_conditions_start_and:
  - cond_azimuth
  - cond_elevation
shading_conditions_start_or:
  - cond_brightness`,

            awning: `# Awning Configuration
blind: cover.example_awning
cover_type: awning
open_position: 0
close_position: 100
shading_position: 75

time_control: time_control_input
time_up_early: "08:00:00"
time_up_late: "09:00:00"
time_down_early: "19:00:00"
time_down_late: "21:00:00"

auto_options:
  - auto_up_enabled
  - auto_down_enabled`
        };
        
        yamlInput.value = examples[type] || '';
        validateConfiguration();
    }
});
