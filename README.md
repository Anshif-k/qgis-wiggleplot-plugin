# WigglePlot QGIS Plugin

A QGIS processing tool designed to batch-process marine geophysical profile data from multiple cruises into clean, structurally sound GeoPackages. 

## Core Features
* **Auto-Groups by Cruise:** Automatically organizes your data files into a single `.gpkg` per cruise, containing separated true-geometry layers.
* **True Geometry Outputs:** Eliminates legacy zero-width polygon hacks. Track lines and full wiggle deflections are strictly generated as `LineString` features, while color anomaly lobes are generated as `Polygon` features.
* **Data Sanitation & Clean Labels:** Automatically strips standard institutional prefixes (NGDC, NIO, ONGC) from layer names and filters out sentinel errors (e.g., `99999.0`, `-999.0`) and corrupted coordinates.
* **Baseline / Detrend Method:** Choose between per-profile mean subtraction (equivalent to GMT's `pswiggle -C`), 1D linear detrending, or custom manual baselines. *(Note: This tool centers individual profiles against themselves for visual display; it does not perform crossover tie-line leveling).*
* **Auto & Manual Azimuth:** Standardizes map polarity based on track heading (Up/Right = Positive, Down/Left = Negative), mirroring GMT's `pswiggle -A0` behavior, with an optional manual angle override.
* **Variable Area Fills:** Color anomaly lobes are split precisely at interpolated zero-crossings for mathematically exact fill boundaries.
* **Legacy Shapefile Export:** Optional fallback to export standard `.shp` pairs for older GIS software compatibility.

## Supported Input Formats
Reads standard space/tab-delimited ASCII profile data: `.xyz`, `.xygk`, `.gmb`, `.xymk`, `.dat`.
*(Tip: In the QGIS file browser, ensure the bottom-right filter is set to **All Files (\*.\*)** to see custom extensions).*

## Installation
1. Download the latest release as a ZIP file. Do not extract it.
2. In QGIS, navigate to **Plugins > Manage and Install Plugins... > Install from ZIP**.
3. Select the downloaded ZIP file and click **Install Plugin**.
4. Once installed, navigate to the **Installed** tab, ensure **WigglePlot** is checked, and access the tool via the top menu bar or the main toolbar icon.

## Acknowledgments
* Developed with the assistance of **Gemini** and **Claude** (AI collaborators) for code structure, UI optimization, and workflow automation.
