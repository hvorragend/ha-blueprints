# Dynamic Sun Elevation Visualization Images

This directory contains visualization graphs for the Dynamic Sun Elevation documentation.

## Generated Images

1. **threshold_curve_annual.png** - Annual threshold curve comparing sine vs linear interpolation
2. **both_sensors_annual.png** - Opening and closing sensors working together throughout the year
3. **latitude_comparison.png** - Comparison of thresholds across different European latitudes
4. **sine_wave_explanation.png** - Mathematical explanation of the sine function transformation

## Regenerating Images

To regenerate all images:

```bash
cd docs/images
python3 generate_graphs.py
```

### Requirements

- Python 3.x
- numpy
- matplotlib

Install requirements:
```bash
pip3 install numpy matplotlib
```

## Image Specifications

- **Format**: PNG
- **DPI**: 150
- **Size**: ~160-185 KB per image
- **Background**: White
- **Font**: Sans-serif, optimized for documentation

## Usage in Documentation

Images are referenced in `blueprints/automation/DYNAMIC_SUN_ELEVATION.md` using relative paths:

```markdown
![Description](../../docs/images/image_name.png)
```

## License

These images are part of the ha-blueprints project and follow the same license.
