import os
import re
import math
from collections import defaultdict
from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterCrs,
    QgsProcessingParameterString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFolderDestination,
    QgsProcessingUtils,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsVectorLayer,
    QgsVectorFileWriter,
    QgsRuleBasedRenderer,
    QgsLineSymbol
)

class MultiCruiseWiggleBatch(QgsProcessingAlgorithm):
    """
    Multi-Cruise Automated Batch Wiggle Line Plotter.
    """

    INPUT_FILES = 'INPUT_FILES'
    LON_COL = 'LON_COL'
    LAT_COL = 'LAT_COL'
    VAL_COL = 'VAL_COL'
    BASELINE_METHOD = 'BASELINE_METHOD'
    MANUAL_BASELINE = 'MANUAL_BASELINE'
    SCALE = 'SCALE'
    AZIMUTH_METHOD = 'AZIMUTH_METHOD'
    MANUAL_AZIMUTH = 'MANUAL_AZIMUTH'
    INVERT = 'INVERT'
    TARGET_CRS = 'TARGET_CRS'
    CRUISE_NAME = 'CRUISE_NAME'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'

    BASELINE_OPTIONS = [
        'Subtract Per-Profile Mean (Preserves slopes & broad ridges — Recommended)',
        '1D Linear Detrend (Removes both slope and DC offset)',
        'Manual Baseline Value (Subtract a specific number)'
    ]
    
    AZIMUTH_OPTIONS = [
        'Auto (Calculated perpendicular to track heading)',
        'Manual Fixed Angle (Specify exact degree below)'
    ]

    def createInstance(self):
        return MultiCruiseWiggleBatch()

    def name(self):
        return 'wiggleline_multicruise_batch'

    def displayName(self):
        return 'WigglePlot'

    def group(self):
        return ''

    def groupId(self):
        return 'wiggleplot_group'

    def shortHelpString(self):
        return (
            "<h3>WigglePlot Automation</h3>"
            "<p>Batch processes profile data files from multiple cruises into individual shapefiles.</p>"
            "<b>Automation Features:</b>"
            "<ul>"
            "<li><b>Auto-Groups by Cruise:</b> Creates a separate <code>.shp</code> for each cruise.</li>"
            "<li><b>Clean Labels:</b> Strips standard institutional prefixes (NGDC, NIO, ONGC).</li>"
            "<li><b>Data Sanitation:</b> Automatically filters out <code>99999.0</code>, <code>-999.0</code>, and corrupted coordinates.</li>"
            "<li><b>Baseline Leveling:</b> Choose between per-profile mean subtraction, 1D linear detrending, or applying a manual constant.</li>"
            "<li><b>Auto-Azimuth:</b> Standardizes map polarity based on track heading (Up/Right = Positive, Down/Left = Negative), with a manual constant option for custom adjustments.</li>"
            "</ul>"
        )

    def initAlgorithm(self, config=None):
        # Step 1: Data Input
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_FILES,
                'Select profile data files (.xygk, .gmb, .xymk, .dat) — all cruises',
                layerType=QgsProcessing.TypeFile
            )
        )
        
        # Step 2: Data Parsing
        self.addParameter(
            QgsProcessingParameterNumber(
                self.LON_COL,
                'Longitude Column',
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=1,
                minValue=1
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.LAT_COL,
                'Latitude Column',
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=2,
                minValue=1
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.VAL_COL,
                'Anomaly / Z Column',
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=3,
                minValue=1
            )
        )
        
        # Step 3: Math & Display
        self.addParameter(
            QgsProcessingParameterEnum(
                self.BASELINE_METHOD,
                'Baseline / Leveling Method',
                options=self.BASELINE_OPTIONS,
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MANUAL_BASELINE,
                'Manual Baseline Value (Only used if "Manual Baseline Value" is selected above)',
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.SCALE,
                'Scale Factor (Map meters per data unit)',
                type=QgsProcessingParameterNumber.Double,
                defaultValue=750.0,
                minValue=0.001
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.AZIMUTH_METHOD,
                'Azimuth / Polarity Strategy',
                options=self.AZIMUTH_OPTIONS,
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MANUAL_AZIMUTH,
                'Manual Azimuth Angle (0-360, ignored if Auto is selected)',
                type=QgsProcessingParameterNumber.Double,
                defaultValue=90.0
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.INVERT,
                'Invert wiggle direction',
                defaultValue=False
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS,
                'Projected CRS for offset math',
                defaultValue='EPSG:32642',
            )
        )
        
        # Step 4: Output
        self.addParameter(
            QgsProcessingParameterString(
                self.CRUISE_NAME,
                'Force single Cruise name for ALL files (leave BLANK to auto-separate each cruise)',
                defaultValue='',
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                'Output folder to save the cruise shapefiles'
            )
        )

    @staticmethod
    def _clean_profile_name(filename):
        base = os.path.splitext(filename)[0]
        base_clean = re.sub(r'[-_](ongc|flt|raw|filt|proc|mig|stk|dgh)$', '', base, flags=re.IGNORECASE)
        base_clean = re.sub(r'^(NGDC|NCEI|NOAA|NIO|ONGC|DGH|GSI|CSIR|GEODAS)[-_]', '', base_clean, flags=re.IGNORECASE)
        return base_clean

    @staticmethod
    def _extract_cruise_name(filename):
        base_clean = MultiCruiseWiggleBatch._clean_profile_name(filename)

        m_two_part = re.match(r'^([a-zA-Z]{1,3})[-_](\d+[a-zA-Z]?\d*)[-_].*$', base_clean)
        if m_two_part:
            sep = '-' if '-' in base_clean else '_'
            return f"{m_two_part.group(1)}{sep}{m_two_part.group(2)}"

        parts = re.split(r'[-_]', base_clean)
        if len(parts) > 1:
            return parts[0]

        m_no_sep = re.match(r'^([a-zA-Z_-]+)\d+$', base_clean)
        if m_no_sep:
            return m_no_sep.group(1).rstrip('-_')

        return base_clean

    @staticmethod
    def _calculate_standard_azimuth(x1, y1, x2, y2):
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length == 0:
            return 90.0

        nx = dy / length
        ny = -dx / length

        if abs(dy) >= abs(dx):
            if nx < 0 or (nx == 0 and ny < 0):
                nx, ny = -nx, -ny
        else:
            if ny < 0 or (ny == 0 and nx < 0):
                nx, ny = -nx, -ny

        azimuth = (math.degrees(math.atan2(nx, ny)) + 360) % 360
        return azimuth

    def processAlgorithm(self, parameters, context, feedback):
        file_paths = self.parameterAsFileList(parameters, self.INPUT_FILES, context)
        lon_idx = self.parameterAsInt(parameters, self.LON_COL, context) - 1
        lat_idx = self.parameterAsInt(parameters, self.LAT_COL, context) - 1
        val_idx = self.parameterAsInt(parameters, self.VAL_COL, context) - 1
        baseline_method = self.parameterAsEnum(parameters, self.BASELINE_METHOD, context)
        manual_baseline = self.parameterAsDouble(parameters, self.MANUAL_BASELINE, context)

        scale = self.parameterAsDouble(parameters, self.SCALE, context)
        azimuth_method = self.parameterAsEnum(parameters, self.AZIMUTH_METHOD, context)
        manual_azimuth = self.parameterAsDouble(parameters, self.MANUAL_AZIMUTH, context)
        invert = self.parameterAsBoolean(parameters, self.INVERT, context)
        target_crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        cruise_override = self.parameterAsString(parameters, self.CRUISE_NAME, context).strip()
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context).strip()

        if not file_paths:
            raise Exception("No profile files selected.")

        if not output_folder or output_folder.upper() == 'TEMPORARY_OUTPUT':
            output_folder = QgsProcessingUtils.tempFolder()

        os.makedirs(output_folder, exist_ok=True)

        self.created_layers = []
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem('EPSG:4326'), target_crs, context.transformContext()
        )
        min_cols = max(lon_idx, lat_idx, val_idx) + 1
        sign = -1.0 if invert else 1.0

        cruise_groups = defaultdict(list)
        for full_path in file_paths:
            if not os.path.isfile(full_path):
                continue
            file_name = os.path.basename(full_path)
            if file_name.startswith('.'):
                continue

            if cruise_override:
                cname = cruise_override
            else:
                cname = self._extract_cruise_name(file_name)

            cruise_groups[cname].append(full_path)

        feedback.pushInfo(f"Identified {len(cruise_groups)} cruise(s): {', '.join(sorted(cruise_groups.keys()))}")

        for cruise_name, cruise_files in cruise_groups.items():
            if feedback.isCanceled():
                break

            fields = QgsFields()
            fields.append(QgsField('source', QVariant.String))
            fields.append(QgsField('type', QVariant.String))

            mem_layer = QgsVectorLayer(f"LineString?crs={target_crs.authid()}", cruise_name, 'memory')
            provider = mem_layer.dataProvider()
            provider.addAttributes(fields)
            mem_layer.updateFields()

            qgs_features = []
            written_sources = []

            for full_path in sorted(cruise_files):
                if feedback.isCanceled():
                    break

                file_name = os.path.basename(full_path)
                clean_name = self._clean_profile_name(file_name)
                raw_pts = []

                with open(full_path, 'r', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#') or line.startswith('>'):
                            continue
                        parts = line.split()
                        if len(parts) < min_cols:
                            continue

                        try:
                            lon = float(parts[lon_idx])
                            lat = float(parts[lat_idx])
                            z_val = float(parts[val_idx])

                            if not (math.isfinite(lon) and math.isfinite(lat) and math.isfinite(z_val)):
                                continue

                            if abs(lon) > 180.0 or abs(lat) > 90.0:
                                continue

                            if abs(z_val) >= 9990.0 or z_val in (99999.0, -99999.0, 9999.0, -9999.0, -999.0, -999.9):
                                continue

                        except (ValueError, IndexError):
                            continue

                        try:
                            p = transform.transform(QgsPointXY(lon, lat))
                            x, y = p.x(), p.y()
                            if not (math.isfinite(x) and math.isfinite(y)):
                                continue
                        except Exception:
                            continue

                        if len(raw_pts) == 0:
                            d = 0.0
                        else:
                            prev_d, prev_x, prev_y, _ = raw_pts[-1]
                            d = prev_d + math.hypot(x - prev_x, y - prev_y)

                        raw_pts.append((d, x, y, z_val))

                if len(raw_pts) < 2:
                    feedback.pushInfo(f"Skipping '{file_name}' — fewer than 2 valid points.")
                    continue

                raw_pts.sort(key=lambda r: r[0])
                n_pts = len(raw_pts)
                d_vals = [r[0] for r in raw_pts]
                z_vals = [r[3] for r in raw_pts]

                mean_z = sum(z_vals) / n_pts

                if baseline_method == 0:
                    z_corrected = [z - mean_z for z in z_vals]
                elif baseline_method == 1:
                    mean_d = sum(d_vals) / n_pts
                    denom = sum((d - mean_d) ** 2 for d in d_vals)
                    if denom > 0:
                        slope = sum((d - mean_d) * (z - mean_z) for d, z in zip(d_vals, z_vals)) / denom
                        intercept = mean_z - slope * mean_d
                        z_corrected = [z - (slope * d + intercept) for d, z in zip(d_vals, z_vals)]
                    else:
                        z_corrected = [z - mean_z for z in z_vals]
                elif baseline_method == 2:
                    z_corrected = [z - manual_baseline for z in z_vals]

                # AZIMUTH LOGIC
                if azimuth_method == 0:
                    _, x1, y1, _ = raw_pts[0]
                    _, x2, y2, _ = raw_pts[-1]
                    effective_azimuth = self._calculate_standard_azimuth(x1, y1, x2, y2)
                else:
                    effective_azimuth = manual_azimuth

                track_pts = []
                wiggle_pts = []
                for (d, x, y, _), z in zip(raw_pts, z_corrected):
                    dist = z * scale * sign
                    ox = x + dist * math.sin(math.radians(effective_azimuth))
                    oy = y + dist * math.cos(math.radians(effective_azimuth))

                    if math.isfinite(x) and math.isfinite(y):
                        track_pts.append(QgsPointXY(x, y))
                    if math.isfinite(ox) and math.isfinite(oy):
                        wiggle_pts.append(QgsPointXY(ox, oy))

                for pts, ftype in ((track_pts, 'track'), (wiggle_pts, 'wiggle')):
                    if len(pts) < 2:
                        continue
                    geom = QgsGeometry.fromPolylineXY(pts)
                    if geom and not geom.isEmpty():
                        feat = QgsFeature(fields)
                        feat.setGeometry(geom)
                        feat.setAttributes([clean_name, ftype])
                        qgs_features.append(feat)

                written_sources.append(clean_name)

            if not qgs_features:
                feedback.pushWarning(f"No valid features created for cruise '{cruise_name}'.")
                continue

            provider.addFeatures(qgs_features)
            mem_layer.updateExtents()

            output_path = os.path.join(output_folder, f'{cruise_name}.shp')
            save_options = QgsVectorFileWriter.SaveVectorOptions()
            save_options.driverName = 'ESRI Shapefile'
            save_options.fileEncoding = 'UTF-8'
            save_options.layerCrs = target_crs
            save_options.destCRS = target_crs

            write_result = QgsVectorFileWriter.writeAsVectorFormatV3(
                mem_layer, output_path, context.transformContext(), save_options
            )
            error_code = write_result[0] if isinstance(write_result, tuple) else write_result
            if error_code != QgsVectorFileWriter.NoError:
                feedback.pushWarning(f"Failed to write '{output_path}': {write_result}")
                continue

            self.created_layers.append((output_path, cruise_name, sorted(set(written_sources))))
            feedback.pushInfo(f"Wrote {len(written_sources)} profile(s) for cruise '{cruise_name}' -> '{output_path}'.")

        return {self.OUTPUT_FOLDER: output_folder}

    @staticmethod
    def _escape_expr_literal(value):
        return value.replace("'", "''")

    def _apply_rule_based_renderer(self, layer, sources):
        root_rule = QgsRuleBasedRenderer.Rule(None)

        for src in sources:
            src_escaped = self._escape_expr_literal(src)
            parent_rule = QgsRuleBasedRenderer.Rule(
                None, 0, 0, f"\"source\" = '{src_escaped}'", src
            )

            track_symbol = QgsLineSymbol.createSimple({'color': '0,0,255,255', 'width': '0.3'})
            track_rule = QgsRuleBasedRenderer.Rule(
                track_symbol, 0, 0, '"type" = \'track\'', 'Track'
            )

            wiggle_symbol = QgsLineSymbol.createSimple({'color': '255,0,0,255', 'width': '0.5'})
            wiggle_rule = QgsRuleBasedRenderer.Rule(
                wiggle_symbol, 0, 0, '"type" = \'wiggle\'', 'Wiggle'
            )

            parent_rule.appendChild(track_rule)
            parent_rule.appendChild(wiggle_rule)
            root_rule.appendChild(parent_rule)

        renderer = QgsRuleBasedRenderer(root_rule)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def postProcessAlgorithm(self, context, feedback):
        for output_path, cruise_name, sources in getattr(self, 'created_layers', []):
            layer = QgsVectorLayer(output_path, cruise_name, 'ogr')
            if layer.isValid():
                self._apply_rule_based_renderer(layer, sources)
                QgsProject.instance().addMapLayer(layer)
                layer.triggerRepaint()

        return {}