# WigglePlot QGIS Plugin

A QGIS processing tool designed to batch process marine geophysical profile data from multiple cruises into individual shapefiles.

## Features
- **Auto-Groups by Cruise:** Automatically organizes your data files into separate `.shp` outputs.
- **Data Sanitation:** Automatically filters out sentinel errors (e.g., `99999.0`, `-999.0`) and corrupted coordinates.
- **Baseline Leveling:** Choose between per-profile mean subtraction, 1D linear detrending, or custom manual baselines.
- **Auto & Manual Azimuth:** Standardizes map polarity based on track heading, with an optional manual angle override.

## Installation
1. Download the latest release as a ZIP file.
2. In QGIS, go to **Plugins > Manage and Install Plugins > Install from ZIP**.
3. Select the downloaded ZIP file and click **Install Plugin**.

## Acknowledgments
* Developed with the assistance of **Gemini** and **Claude** (AI collaborators) for code structure, UI optimization, and workflow automation.
