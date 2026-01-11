#!/usr/bin/env python3
"""
Generate visual graphs for Dynamic Sun Elevation documentation
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams
import os

# Set style
rcParams['font.family'] = 'sans-serif'
rcParams['font.size'] = 10
rcParams['axes.labelsize'] = 11
rcParams['axes.titlesize'] = 12
rcParams['legend.fontsize'] = 9
rcParams['figure.dpi'] = 150

# Output directory
output_dir = os.path.dirname(os.path.abspath(__file__))

def calculate_threshold(day, summer, winter):
    """Calculate threshold value for a given day using sinusoidal interpolation"""
    seasonal_factor = np.sin(2 * np.pi * (day - 80.75) / 365)
    base = winter + (summer - winter) * (seasonal_factor + 1) / 2
    return base

def calculate_threshold_linear(day, summer, winter):
    """Calculate threshold value using linear interpolation"""
    if day < 172:  # Before summer solstice
        # Jan 1 (day 1) to Jun 21 (day 172)
        progress = (day - 1) / (172 - 1)
        return winter + (summer - winter) * progress
    else:  # After summer solstice
        # Jun 21 (day 172) to Dec 31 (day 365)
        progress = (day - 172) / (365 - 172)
        return summer + (winter - summer) * progress

def graph1_annual_threshold_curve():
    """Generate annual threshold curve comparing sine vs linear"""
    days = np.arange(1, 366)

    # Opening sensor values (50°N)
    summer_open = -2.0
    winter_open = 5.0

    # Calculate values
    sine_values = [calculate_threshold(d, summer_open, winter_open) for d in days]
    linear_values = [calculate_threshold_linear(d, summer_open, winter_open) for d in days]

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot curves
    ax.plot(days, sine_values, 'b-', linewidth=2.5, label='Sine interpolation (recommended)', zorder=3)
    ax.plot(days, linear_values, 'r--', linewidth=1.5, label='Linear interpolation', alpha=0.7, zorder=2)

    # Mark key dates
    key_dates = [
        (1, 'Jan 1\n(Winter)', 'top'),
        (80, 'Mar 21\n(Spring Equinox)', 'bottom'),
        (172, 'Jun 21\n(Summer Solstice)', 'top'),
        (266, 'Sep 23\n(Fall Equinox)', 'bottom'),
        (355, 'Dec 21\n(Winter Solstice)', 'top'),
    ]

    for day, label, valign in key_dates:
        val = calculate_threshold(day, summer_open, winter_open)
        ax.axvline(day, color='gray', linestyle=':', alpha=0.5, linewidth=1)

        if valign == 'top':
            ax.annotate(label, xy=(day, val), xytext=(day, val + 1.2),
                       ha='center', va='bottom', fontsize=8,
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                                edgecolor='gray', alpha=0.8))
        else:
            ax.annotate(label, xy=(day, val), xytext=(day, val - 1.2),
                       ha='center', va='top', fontsize=8,
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                                edgecolor='gray', alpha=0.8))

    # Add annotation for equinox behavior
    ax.annotate('Equinoxes: Sine curve\nchanges faster',
                xy=(80, calculate_threshold(80, summer_open, winter_open)),
                xytext=(120, 0),
                fontsize=9, ha='left',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.3),
                arrowprops=dict(arrowstyle='->', color='black', lw=1.5))

    # Styling
    ax.set_xlabel('Day of Year', fontsize=12, fontweight='bold')
    ax.set_ylabel('Sun Elevation Threshold (degrees)', fontsize=12, fontweight='bold')
    ax.set_title('Dynamic Sun Elevation Threshold Throughout Year (50°N)\nOpening Sensor Example',
                fontsize=14, fontweight='bold', pad=20)
    ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
    ax.legend(loc='upper right', framealpha=0.9)
    ax.set_xlim(0, 366)
    ax.set_ylim(-3, 6)

    # Add month labels on secondary x-axis
    month_days = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks(month_days)
    ax2.set_xticklabels(month_names)
    ax2.tick_params(axis='x', length=0)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'threshold_curve_annual.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    print("✓ Generated: threshold_curve_annual.png")
    plt.close()

def graph2_both_sensors():
    """Generate graph showing both opening and closing sensors"""
    days = np.arange(1, 366)

    # Opening sensor (50°N)
    summer_open = -2.0
    winter_open = 5.0
    open_values = [calculate_threshold(d, summer_open, winter_open) for d in days]

    # Closing sensor (50°N)
    summer_close = -1.0
    winter_close = 2.0
    close_values = [calculate_threshold(d, summer_close, winter_close) for d in days]

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot curves
    ax.plot(days, open_values, 'b-', linewidth=2.5, label='Opening sensor', zorder=3)
    ax.plot(days, close_values, 'r-', linewidth=2.5, label='Closing sensor', zorder=3)

    # Shade the "window" between opening and closing
    ax.fill_between(days, open_values, close_values, alpha=0.2, color='green',
                     label='Cover open window')

    # Mark key dates
    key_dates = [
        (1, 'Jan 1 (Winter)', winter_open + 0.5),
        (172, 'Jun 21 (Summer)', summer_open - 0.5),
        (355, 'Dec 21 (Winter)', winter_open + 0.5),
    ]

    for day, label, y_pos in key_dates:
        ax.axvline(day, color='gray', linestyle=':', alpha=0.5, linewidth=1)
        ax.text(day, y_pos, label, ha='center', va='center', fontsize=9,
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                         edgecolor='gray', alpha=0.9))

    # Add behavior annotations
    ax.annotate('WINTER:\n• High thresholds\n• Opens late\n• Closes early\n• Short day',
                xy=(355, 3.5), xytext=(320, 4.5),
                fontsize=9, ha='center',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.7),
                arrowprops=dict(arrowstyle='->', color='blue', lw=1.5))

    ax.annotate('SUMMER:\n• Low thresholds\n• Opens early\n• Closes late\n• Long day',
                xy=(172, -1.5), xytext=(172, -3.5),
                fontsize=9, ha='center',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightyellow', alpha=0.7),
                arrowprops=dict(arrowstyle='->', color='orange', lw=1.5))

    # Styling
    ax.set_xlabel('Day of Year', fontsize=12, fontweight='bold')
    ax.set_ylabel('Sun Elevation Threshold (degrees)', fontsize=12, fontweight='bold')
    ax.set_title('Dynamic Sun Elevation Sensors Throughout Year (50°N)\nOpening and Closing Behavior',
                fontsize=14, fontweight='bold', pad=20)
    ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
    ax.legend(loc='upper right', framealpha=0.9)
    ax.set_xlim(0, 366)
    ax.set_ylim(-4, 6)

    # Add month labels
    month_days = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks(month_days)
    ax2.set_xticklabels(month_names)
    ax2.tick_params(axis='x', length=0)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'both_sensors_annual.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    print("✓ Generated: both_sensors_annual.png")
    plt.close()

def graph3_latitude_comparison():
    """Generate graph comparing different latitudes"""
    days = np.arange(1, 366)

    # Base values for 50°N
    summer_open = -2.0
    winter_open = 5.0

    # Different latitudes
    latitudes = [
        (38.0, 'Athens (38°N)', '#FF6B6B'),
        (48.2, 'Vienna (48°N)', '#4ECDC4'),
        (52.5, 'Berlin (52.5°N)', '#45B7D1'),
        (59.3, 'Stockholm (59°N)', '#96CEB4'),
    ]

    fig, ax = plt.subplots(figsize=(12, 6))

    for lat, label, color in latitudes:
        # Calculate adjustment
        adjustment = (lat - 50) * 0.2
        values = [calculate_threshold(d, summer_open, winter_open) + adjustment for d in days]
        ax.plot(days, values, linewidth=2, label=label, color=color)

    # Mark key dates
    for day in [1, 172, 355]:
        ax.axvline(day, color='gray', linestyle=':', alpha=0.3, linewidth=1)

    # Styling
    ax.set_xlabel('Day of Year', fontsize=12, fontweight='bold')
    ax.set_ylabel('Sun Elevation Threshold (degrees)', fontsize=12, fontweight='bold')
    ax.set_title('Dynamic Sun Elevation Thresholds by Latitude\nOpening Sensor Comparison',
                fontsize=14, fontweight='bold', pad=20)
    ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
    ax.legend(loc='upper right', framealpha=0.9)
    ax.set_xlim(0, 366)

    # Add month labels
    month_days = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    ax2.set_xticks(month_days)
    ax2.set_xticklabels(month_names)
    ax2.tick_params(axis='x', length=0)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'latitude_comparison.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    print("✓ Generated: latitude_comparison.png")
    plt.close()

def graph4_sine_wave_explanation():
    """Generate sine wave with seasonal factor explanation"""
    days = np.arange(1, 366)
    seasonal_factors = [np.sin(2 * np.pi * (d - 80.75) / 365) for d in days]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    # Top: Sine wave
    ax1.plot(days, seasonal_factors, 'b-', linewidth=2.5)
    ax1.axhline(0, color='black', linestyle='-', linewidth=0.8, alpha=0.3)
    ax1.axhline(1, color='red', linestyle='--', linewidth=1, alpha=0.5, label='Maximum (Summer)')
    ax1.axhline(-1, color='blue', linestyle='--', linewidth=1, alpha=0.5, label='Minimum (Winter)')

    # Mark key points
    key_points = [
        (80, 0, 'Spring Equinox\n(Mar 21)', 'bottom'),
        (172, 1, 'Summer Solstice\n(Jun 21)', 'top'),
        (266, 0, 'Fall Equinox\n(Sep 23)', 'top'),
        (355, -1, 'Winter Solstice\n(Dec 21)', 'bottom'),
    ]

    for day, value, label, pos in key_points:
        ax1.plot(day, value, 'ro', markersize=8, zorder=5)
        if pos == 'top':
            ax1.annotate(label, xy=(day, value), xytext=(day, value + 0.3),
                        ha='center', va='bottom', fontsize=9,
                        bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                                 edgecolor='red', alpha=0.9))
        else:
            ax1.annotate(label, xy=(day, value), xytext=(day, value - 0.3),
                        ha='center', va='top', fontsize=9,
                        bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                                 edgecolor='blue', alpha=0.9))

    ax1.set_ylabel('Seasonal Factor\nsin(2π × (day - 80.75) / 365)', fontsize=11, fontweight='bold')
    ax1.set_title('Sine Function for Seasonal Interpolation', fontsize=14, fontweight='bold', pad=15)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper right')
    ax1.set_ylim(-1.3, 1.3)
    ax1.set_xlim(0, 366)

    # Bottom: Resulting threshold values
    summer = -2.0
    winter = 5.0
    thresholds = [calculate_threshold(d, summer, winter) for d in days]

    ax2.plot(days, thresholds, 'g-', linewidth=2.5, label='Threshold value')
    ax2.axhline(summer, color='orange', linestyle='--', linewidth=1, alpha=0.5,
                label=f'Summer value = {summer}°')
    ax2.axhline(winter, color='purple', linestyle='--', linewidth=1, alpha=0.5,
                label=f'Winter value = {winter}°')

    # Mark same key dates
    for day, _, label, _ in key_points:
        val = calculate_threshold(day, summer, winter)
        ax2.plot(day, val, 'go', markersize=8, zorder=5)

    ax2.set_xlabel('Day of Year', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Threshold (degrees)', fontsize=11, fontweight='bold')
    ax2.set_title('Resulting Sun Elevation Threshold (Opening Sensor)',
                 fontsize=14, fontweight='bold', pad=15)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')
    ax2.set_xlim(0, 366)
    ax2.set_ylim(-3, 6)

    # Add month labels for both
    month_days = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    for ax in [ax1, ax2]:
        ax_top = ax.twiny()
        ax_top.set_xlim(ax.get_xlim())
        ax_top.set_xticks(month_days)
        ax_top.set_xticklabels(month_names)
        ax_top.tick_params(axis='x', length=0)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'sine_wave_explanation.png'),
                dpi=150, bbox_inches='tight', facecolor='white')
    print("✓ Generated: sine_wave_explanation.png")
    plt.close()

if __name__ == '__main__':
    print("\n🎨 Generating Dynamic Sun Elevation documentation graphs...\n")

    try:
        graph1_annual_threshold_curve()
        graph2_both_sensors()
        graph3_latitude_comparison()
        graph4_sine_wave_explanation()

        print("\n✅ All graphs generated successfully!")
        print(f"📁 Location: {output_dir}/")
        print("\nGenerated files:")
        print("  • threshold_curve_annual.png - Annual curve comparison (sine vs linear)")
        print("  • both_sensors_annual.png - Opening and closing sensors together")
        print("  • latitude_comparison.png - Comparison across different latitudes")
        print("  • sine_wave_explanation.png - Mathematical explanation\n")

    except Exception as e:
        print(f"\n❌ Error generating graphs: {e}")
        import traceback
        traceback.print_exc()
