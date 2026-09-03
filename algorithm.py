import os
import re
import math
from collections import defaultdict
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterCrs,
    QgsProcessingParameterString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterColor,
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
    QgsFillSymbol,
    QgsLineSymbol
)
from PyQt5.QtGui import QColor

class MultiCruiseWiggleBatch(QgsProcessingAlgorithm):
    INPUT_FILES = 'INPUT_FILES'
    LON_COL = 'LON_COL'
    LAT_COL = 'LAT_COL'
    VAL_COL = 'VAL_COL'
    BASELINE_METHOD = 'BASELINE_METHOD'
    MANUAL_BASELINE = 'MANUAL_BASELINE'
    SCALE = 'SCALE'
    AZIMUTH_METHOD = 'AZIMUTH_METHOD'
    MANUAL_AZIMUTH = 'MANUAL_AZIMUTH'
    TARGET_CRS = 'TARGET_CRS'
    CRUISE_NAME = 'CRUISE_NAME'

    TRACK_COLOR = 'TRACK_COLOR'
    WIGGLE_COLOR = 'WIGGLE_COLOR'
    FILL_STYLE_MODE = 'FILL_STYLE_MODE'
    CUSTOM_POS_COLOR = 'CUSTOM_POS_COLOR'
    CUSTOM_NEG_COLOR = 'CUSTOM_NEG_COLOR'
    SINGLE_FILL_COLOR = 'SINGLE_FILL_COLOR'

    EXPORT_SHAPEFILE_COMPAT = 'EXPORT_SHAPEFILE_COMPAT'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'

    BASELINE_OPTIONS = [
        'Subtract Per-Profile Mean — pswiggle -C equivalent (Preserves slopes & broad ridges — Recommended)',
        '1D Linear Detrend — NOT a -C equivalent (Removes both slope and DC offset)',
        'Manual Baseline Value — pswiggle -C <value> equivalent (Subtract a specific number)'
    ]

    AZIMUTH_OPTIONS = [
        'Auto (Calculated perpendicular to track heading)',
        'Manual Fixed Angle (Specify exact degree below)'
    ]

    FILL_STYLE_OPTIONS = [
        '1. No Fill (Track & Wiggle Line Only — toggle the Fill layer off instead of using this for line-only display)',
        '2. Dual Fill: Red (+) / Blue (-)',
        '3. Custom Dual Fill',
        '4. Fill Positive Peaks Only',
        '5. Fill Negative Peaks Only'
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
            "<p>Batch processes profile data files from multiple cruises into a GeoPackage per cruise.</p>"
            "<b>Automation Features:</b>"
            "<ul>"
            "<li><b>Auto-Groups by Cruise:</b> Creates a separate <code>.gpkg</code> for each cruise.</li>"
            "<li><b>Clean Labels:</b> Strips standard institutional prefixes (NGDC, NIO, ONGC).</li>"
            "<li><b>Data Sanitation:</b> Automatically filters out <code>99999.0</code>, <code>-999.0</code>, and corrupted coordinates.</li>"
            "<li><b>Baseline / Detrend Method:</b> Choose how each profile is centered on zero before plotting. "
            "'Subtract Per-Profile Mean' and 'Manual Baseline Value' are direct equivalents of GMT <code>pswiggle -C</code> "
            "(subtract a single scalar constant). '1D Linear Detrend' is a different, stronger operation — it also removes "
            "slope, which can strip genuine broad-wavelength signal (regional gradients, long-wavelength anomalies).</li>"
            "<li><b>Auto-Azimuth:</b> Standardizes map polarity based on track heading (Up/Right = Positive, Down/Left = Negative), "
            "mirroring GMT <code>pswiggle -A0</code> default behavior, with a manual constant option for custom adjustments.</li>"
            "</ul>"
            "<b>Output Structure (GeoPackage):</b>"
            "<ul>"
            "<li>Each cruise produces a single <code>.gpkg</code> containing two true-geometry layers: "
            "<b>&lt;cruise&gt;</b> — a <code>LineString</code> layer with the track line and full wiggle deflection line "
            "(always written, regardless of fill setting), and "
            "<b>&lt;cruise&gt;_fill</b> — a <code>Polygon</code> layer of zero-crossing-split anomaly lobes "
            "(only written when a fill style other than 'No Fill' is selected).</li>"
            "<li>To view without color fill, toggle the <b>&lt;cruise&gt;_fill</b> layer off in the Layers panel — "
            "there is no need to regenerate output with a different fill setting just to hide color.</li>"
            "</ul>"
            "<b>Optional Shapefile Compatibility Export:</b>"
            "<ul>"
            "<li>Enable <b>Also export Shapefile-compatible output</b> to additionally write "
            "<code>&lt;cruise&gt;_lines.shp</code> and (if fill was generated) <code>&lt;cruise&gt;_fill.shp</code> "
            "for software that cannot read GeoPackage. This roughly doubles disk usage for that cruise, so it is off by default.</li>"
            "</ul>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers(self.INPUT_FILES, 'Select profile data files (.xyz, .xygk, .gmb, .xymk, .dat) — all cruises', layerType=QgsProcessing.TypeFile))
        self.addParameter(QgsProcessingParameterString(self.LON_COL, 'Longitude Column', defaultValue='1'))
        self.addParameter(QgsProcessingParameterString(self.LAT_COL, 'Latitude Column', defaultValue='2'))
        self.addParameter(QgsProcessingParameterString(self.VAL_COL, 'Anomaly / Z Column', defaultValue='3'))
        self.addParameter(QgsProcessingParameterEnum(self.BASELINE_METHOD, 'Baseline / Detrend Method (pswiggle -C equivalent)', options=self.BASELINE_OPTIONS, defaultValue=0))
        self.addParameter(QgsProcessingParameterString(self.MANUAL_BASELINE, 'Manual Baseline Value', defaultValue='0.0'))
        self.addParameter(QgsProcessingParameterString(self.SCALE, 'Scale Factor (Map meters per data unit)', defaultValue='750.0'))
        self.addParameter(QgsProcessingParameterEnum(self.AZIMUTH_METHOD, 'Azimuth / Polarity Strategy', options=self.AZIMUTH_OPTIONS, defaultValue=0))
        self.addParameter(QgsProcessingParameterString(self.MANUAL_AZIMUTH, 'Manual Azimuth Angle (0-360)', defaultValue='90.0'))
        self.addParameter(QgsProcessingParameterCrs(self.TARGET_CRS, 'Projected CRS for offset math', defaultValue='EPSG:32642'))
        self.addParameter(QgsProcessingParameterColor(self.TRACK_COLOR, 'Track Line Color', defaultValue=QColor(0, 0, 0)))
        self.addParameter(QgsProcessingParameterColor(self.WIGGLE_COLOR, 'Wiggle Profile Line Color', defaultValue=QColor(0, 0, 0)))
        self.addParameter(QgsProcessingParameterEnum(self.FILL_STYLE_MODE, 'Wiggle Fill Style & Polarity Mode', options=self.FILL_STYLE_OPTIONS, defaultValue=1))
        self.addParameter(QgsProcessingParameterColor(self.CUSTOM_POS_COLOR, 'Custom Positive Fill Color', defaultValue=QColor(230, 0, 0, 200)))
        self.addParameter(QgsProcessingParameterColor(self.CUSTOM_NEG_COLOR, 'Custom Negative Fill Color', defaultValue=QColor(0, 102, 204, 200)))
        self.addParameter(QgsProcessingParameterColor(self.SINGLE_FILL_COLOR, 'Single Fill Color', defaultValue=QColor(230, 0, 0, 200)))
        self.addParameter(QgsProcessingParameterString(self.CRUISE_NAME, 'Force single Cruise name for ALL files (optional)', defaultValue='', optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.EXPORT_SHAPEFILE_COMPAT, 'Also export Shapefile-compatible output (.shp pair per cruise, ~2x disk usage)', defaultValue=False))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, 'Output folder to save the cruise GeoPackages'))

    @staticmethod
    def _clean_profile_name(filename):
        base = os.path.splitext(filename)[0]
        base_clean = re.sub(r'[-_](ongc|flt|raw|filt|proc|mig|stk|dgh)$', '', base, flags=re.IGNORECASE)
        base_clean = re.sub(r'^(NGDC|NCEI|NOAA|NIO|ONGC|DGH|GSI|CSIR|GEODAS|SK)[-_]', '', base_clean, flags=re.IGNORECASE)
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
        heading = math.degrees(math.atan2(x2 - x1, y2 - y1))
        azimuth = (heading + 90) % 360
        if 90 < azimuth <= 270:
            azimuth = (azimuth + 180) % 360
        return azimuth

    def processAlgorithm(self, parameters, context, feedback):
        file_paths = self.parameterAsFileList(parameters, self.INPUT_FILES, context)

        if not file_paths:
            raise Exception("No profile files selected.")

        try:
            lon_idx = int(self.parameterAsString(parameters, self.LON_COL, context)) - 1
            lat_idx = int(self.parameterAsString(parameters, self.LAT_COL, context)) - 1
            val_idx = int(self.parameterAsString(parameters, self.VAL_COL, context)) - 1
            manual_baseline = float(self.parameterAsString(parameters, self.MANUAL_BASELINE, context))
            scale = float(self.parameterAsString(parameters, self.SCALE, context))
            manual_azimuth = float(self.parameterAsString(parameters, self.MANUAL_AZIMUTH, context))
        except ValueError:
            raise Exception("Please ensure Column indexes, Baseline, Scale, and Azimuth are valid numbers.")

        baseline_method = self.parameterAsEnum(parameters, self.BASELINE_METHOD, context)
        azimuth_method = self.parameterAsEnum(parameters, self.AZIMUTH_METHOD, context)
        target_crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        cruise_override = self.parameterAsString(parameters, self.CRUISE_NAME, context).strip()
        export_shp_compat = self.parameterAsBoolean(parameters, self.EXPORT_SHAPEFILE_COMPAT, context)
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context).strip()

        self.track_color = self.parameterAsColor(parameters, self.TRACK_COLOR, context)
        self.wiggle_color = self.parameterAsColor(parameters, self.WIGGLE_COLOR, context)
        self.fill_style_mode = self.parameterAsEnum(parameters, self.FILL_STYLE_MODE, context)

        custom_pos = self.parameterAsColor(parameters, self.CUSTOM_POS_COLOR, context)
        custom_neg = self.parameterAsColor(parameters, self.CUSTOM_NEG_COLOR, context)
        single_fill = self.parameterAsColor(parameters, self.SINGLE_FILL_COLOR, context)

        compute_fill = (self.fill_style_mode != 0)

        if self.fill_style_mode == 0:
            self.pos_color = QColor(0, 0, 0, 0)
            self.neg_color = QColor(0, 0, 0, 0)
        elif self.fill_style_mode == 1:
            self.pos_color = QColor(230, 0, 0, 200)
            self.neg_color = QColor(0, 102, 204, 200)
        elif self.fill_style_mode == 2:
            self.pos_color = custom_pos
            self.neg_color = custom_neg
        elif self.fill_style_mode == 3:
            self.pos_color = single_fill
            self.neg_color = QColor(0, 0, 0, 0)
        else:
            self.pos_color = QColor(0, 0, 0, 0)
            self.neg_color = single_fill

        if not output_folder or output_folder.upper() == 'TEMPORARY_OUTPUT':
            output_folder = QgsProcessingUtils.tempFolder()

        os.makedirs(output_folder, exist_ok=True)

        self.created_layers = []
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem('EPSG:4326'), target_crs, context.transformContext()
        )
        min_cols = max(lon_idx, lat_idx, val_idx) + 1

        cruise_groups = defaultdict(list)
        for full_path in file_paths:
            if not os.path.isfile(full_path):
                continue
            file_name = os.path.basename(full_path)
            if file_name.startswith('.'):
                continue
            cname = cruise_override if cruise_override else self._extract_cruise_name(file_name)
            cruise_groups[cname].append(full_path)

        for cruise_name, cruise_files in cruise_groups.items():
            if feedback.isCanceled():
                break

            tw_fields = QgsFields()
            tw_fields.append(QgsField('source', QVariant.String))
            tw_fields.append(QgsField('type', QVariant.String))

            fill_fields = QgsFields()
            fill_fields.append(QgsField('source', QVariant.String))
            fill_fields.append(QgsField('type', QVariant.String))
            fill_fields.append(QgsField('val', QVariant.Double))

            mem_tw = QgsVectorLayer(f"LineString?crs={target_crs.authid()}", cruise_name, 'memory')
            tw_provider = mem_tw.dataProvider()
            tw_provider.addAttributes(tw_fields)
            mem_tw.updateFields()

            mem_fill = QgsVectorLayer(f"Polygon?crs={target_crs.authid()}", f'{cruise_name}_fill', 'memory')
            fill_provider = mem_fill.dataProvider()
            fill_provider.addAttributes(fill_fields)
            mem_fill.updateFields()

            tw_features = []
            fill_features = []
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
                            if abs(z_val) >= 9990.0 or z_val in (99999.0, -999.0, -999.9):
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

                        d = 0.0 if len(raw_pts) == 0 else raw_pts[-1][0] + math.hypot(x - raw_pts[-1][1], y - raw_pts[-1][2])
                        raw_pts.append((d, x, y, z_val))

                if len(raw_pts) < 2:
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
                else:
                    z_corrected = [z - manual_baseline for z in z_vals]

                effective_azimuth = self._calculate_standard_azimuth(raw_pts[0][1], raw_pts[0][2], raw_pts[-1][1], raw_pts[-1][2]) if azimuth_method == 0 else manual_azimuth
                rad = math.radians(effective_azimuth)
                ux, uy = math.sin(rad), math.cos(rad)

                def _get_offset_pt(x, y, v):
                    dist = v * scale
                    return QgsPointXY(x + dist * ux, y + dist * uy)

                track_pts = [QgsPointXY(r[1], r[2]) for r in raw_pts if math.isfinite(r[1]) and math.isfinite(r[2])]
                wiggle_pts = [_get_offset_pt(r[1], r[2], z) for r, z in zip(raw_pts, z_corrected)]

                for pts, ftype in ((track_pts, 'track'), (wiggle_pts, 'wiggle')):
                    if len(pts) >= 2:
                        geom = QgsGeometry.fromPolylineXY(pts)
                        if geom and not geom.isEmpty():
                            feat = QgsFeature(tw_fields)
                            feat.setGeometry(geom)
                            feat.setAttributes([clean_name, ftype])
                            tw_features.append(feat)

                if compute_fill:
                    lobe_track = []
                    lobe_offset = []
                    lobe_val = 0.0

                    def _flush_lobe():
                        if len(lobe_track) < 2:
                            return
                        poly_pts = lobe_track + lobe_offset[::-1] + [lobe_track[0]]
                        geom = QgsGeometry.fromPolygonXY([poly_pts])
                        if geom and not geom.isEmpty():
                            f = QgsFeature(fill_fields)
                            f.setGeometry(geom)
                            f.setAttributes([clean_name, 'wiggle', lobe_val])
                            fill_features.append(f)

                    for i in range(n_pts - 1):
                        p1 = track_pts[i]
                        p2 = track_pts[i+1]
                        v1 = z_corrected[i]
                        v2 = z_corrected[i+1]
                        w1 = wiggle_pts[i]
                        w2 = wiggle_pts[i+1]

                        if not lobe_track:
                            lobe_track.append(p1)
                            lobe_offset.append(w1)
                            lobe_val = v1

                        if v1 * v2 < 0:
                            frac = abs(v1) / (abs(v1) + abs(v2))
                            p_mid = QgsPointXY(p1.x() + frac * (p2.x() - p1.x()), p1.y() + frac * (p2.y() - p1.y()))
                            w_mid = p_mid

                            lobe_track.append(p_mid)
                            lobe_offset.append(w_mid)
                            lobe_val = v1
                            _flush_lobe()

                            lobe_track = [p_mid, p2]
                            lobe_offset = [w_mid, w2]
                            lobe_val = v2
                        else:
                            lobe_track.append(p2)
                            lobe_offset.append(w2)
                            if abs(v2) > abs(lobe_val):
                                lobe_val = v2

                    _flush_lobe()

                written_sources.append(clean_name)

            if not tw_features:
                continue

            tw_provider.addFeatures(tw_features)
            mem_tw.updateExtents()

            has_fill = bool(fill_features)
            if has_fill:
                fill_provider.addFeatures(fill_features)
                mem_fill.updateExtents()

            gpkg_path = os.path.join(output_folder, f'{cruise_name}.gpkg')
            lines_shp_path = os.path.join(output_folder, f'{cruise_name}_lines.shp')
            fill_shp_path = os.path.join(output_folder, f'{cruise_name}_fill.shp')

            for path_to_clean in (lines_shp_path, fill_shp_path):
                if os.path.exists(path_to_clean):
                    QgsVectorFileWriter.deleteShapeFile(path_to_clean)

            tw_save_options = QgsVectorFileWriter.SaveVectorOptions()
            tw_save_options.driverName = 'GPKG'
            tw_save_options.fileEncoding = 'UTF-8'
            tw_save_options.layerName = 'track_wiggle'
            tw_save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

            tw_write_result = QgsVectorFileWriter.writeAsVectorFormatV3(
                mem_tw, gpkg_path, context.transformContext(), tw_save_options
            )
            if tw_write_result[0] != QgsVectorFileWriter.NoError:
                feedback.reportError(f"Failed to write GPKG track_wiggle layer for '{cruise_name}': {tw_write_result[2]}")
                continue

            if has_fill:
                fill_save_options = QgsVectorFileWriter.SaveVectorOptions()
                fill_save_options.driverName = 'GPKG'
                fill_save_options.fileEncoding = 'UTF-8'
                fill_save_options.layerName = 'fill_lobes'
                fill_save_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
                
                fill_write_result = QgsVectorFileWriter.writeAsVectorFormatV3(
                    mem_fill, gpkg_path, context.transformContext(), fill_save_options
                )
                if fill_write_result[0] != QgsVectorFileWriter.NoError:
                    feedback.reportError(f"Failed to write GPKG fill_lobes layer for '{cruise_name}': {fill_write_result[2]}")

            if export_shp_compat:
                shp_lines_options = QgsVectorFileWriter.SaveVectorOptions()
                shp_lines_options.driverName = 'ESRI Shapefile'
                shp_lines_options.fileEncoding = 'UTF-8'
                
                shp_lines_result = QgsVectorFileWriter.writeAsVectorFormatV3(
                    mem_tw, lines_shp_path, context.transformContext(), shp_lines_options
                )
                if shp_lines_result[0] != QgsVectorFileWriter.NoError:
                    feedback.reportError(f"Failed to write lines shapefile for '{cruise_name}': {shp_lines_result[2]}")

                if has_fill:
                    shp_fill_options = QgsVectorFileWriter.SaveVectorOptions()
                    shp_fill_options.driverName = 'ESRI Shapefile'
                    shp_fill_options.fileEncoding = 'UTF-8'
                    
                    shp_fill_result = QgsVectorFileWriter.writeAsVectorFormatV3(
                        mem_fill, fill_shp_path, context.transformContext(), shp_fill_options
                    )
                    if shp_fill_result[0] != QgsVectorFileWriter.NoError:
                        feedback.reportError(f"Failed to write fill shapefile for '{cruise_name}': {shp_fill_result[2]}")

            self.created_layers.append((gpkg_path, cruise_name, sorted(set(written_sources)), has_fill))

        return {self.OUTPUT_FOLDER: output_folder}

    @staticmethod
    def _escape_expr_literal(value):
        return value.replace("'", "''")

    def _apply_track_wiggle_renderer(self, layer, sources):
        root_rule = QgsRuleBasedRenderer.Rule(None)

        for src in sources:
            src_escaped = self._escape_expr_literal(src)
            parent_rule = QgsRuleBasedRenderer.Rule(
                None, 0, 0, f"\"source\" = '{src_escaped}'", src
            )

            track_symbol = QgsLineSymbol.createSimple({'color': self.track_color.name(), 'width': '0.6', 'joinstyle': 'bevel', 'capstyle': 'flat'})
            track_rule = QgsRuleBasedRenderer.Rule(track_symbol, 0, 0, '"type" = \'track\'', 'Track Line')

            wiggle_symbol = QgsLineSymbol.createSimple({'color': self.wiggle_color.name(), 'width': '0.4', 'joinstyle': 'bevel', 'capstyle': 'flat'})
            wiggle_rule = QgsRuleBasedRenderer.Rule(wiggle_symbol, 0, 0, '"type" = \'wiggle\'', 'Wiggle Line')

            parent_rule.appendChild(track_rule)
            parent_rule.appendChild(wiggle_rule)
            root_rule.appendChild(parent_rule)

        renderer = QgsRuleBasedRenderer(root_rule)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def _apply_fill_renderer(self, layer, sources):
        root_rule = QgsRuleBasedRenderer.Rule(None)

        for src in sources:
            src_escaped = self._escape_expr_literal(src)
            parent_rule = QgsRuleBasedRenderer.Rule(
                None, 0, 0, f"\"source\" = '{src_escaped}'", src
            )

            if self.fill_style_mode in (1, 2):
                pos_symbol = QgsFillSymbol.createSimple({'color': self.pos_color.name(), 'outline_style': 'no'})
                pos_rule = QgsRuleBasedRenderer.Rule(pos_symbol, 0, 0, '"val" >= 0', 'Positive Fill')
                neg_symbol = QgsFillSymbol.createSimple({'color': self.neg_color.name(), 'outline_style': 'no'})
                neg_rule = QgsRuleBasedRenderer.Rule(neg_symbol, 0, 0, '"val" < 0', 'Negative Fill')
                parent_rule.appendChild(pos_rule)
                parent_rule.appendChild(neg_rule)
            elif self.fill_style_mode == 3:
                pos_symbol = QgsFillSymbol.createSimple({'color': self.pos_color.name(), 'outline_style': 'no'})
                pos_rule = QgsRuleBasedRenderer.Rule(pos_symbol, 0, 0, '"val" >= 0', 'Positive Fill')
                parent_rule.appendChild(pos_rule)
            elif self.fill_style_mode == 4:
                neg_symbol = QgsFillSymbol.createSimple({'color': self.neg_color.name(), 'outline_style': 'no'})
                neg_rule = QgsRuleBasedRenderer.Rule(neg_symbol, 0, 0, '"val" < 0', 'Negative Fill')
                parent_rule.appendChild(neg_rule)

            root_rule.appendChild(parent_rule)

        renderer = QgsRuleBasedRenderer(root_rule)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def postProcessAlgorithm(self, context, feedback):
        for gpkg_path, cruise_name, sources, has_fill in getattr(self, 'created_layers', []):
            fill_layer = None
            if has_fill:
                fill_layer = QgsVectorLayer(f"{gpkg_path}|layername=fill_lobes", f'{cruise_name}_fill', 'ogr')
                if fill_layer.isValid():
                    fill_layer.updateExtents()
                    self._apply_fill_renderer(fill_layer, sources)
                    QgsProject.instance().addMapLayer(fill_layer)
                    fill_layer.triggerRepaint()
                else:
                    feedback.reportError(
                        f"WigglePlot: fill_lobes layer failed to load from '{gpkg_path}' for cruise '{cruise_name}'. "
                        f"Fill polygons were written but will not appear in the project."
                    )

            tw_layer = QgsVectorLayer(f"{gpkg_path}|layername=track_wiggle", cruise_name, 'ogr')
            if tw_layer.isValid():
                tw_layer.updateExtents()
                self._apply_track_wiggle_renderer(tw_layer, sources)
                QgsProject.instance().addMapLayer(tw_layer)
                tw_layer.triggerRepaint()
            else:
                feedback.reportError(
                    f"WigglePlot: track_wiggle layer failed to load from '{gpkg_path}' for cruise '{cruise_name}'. "
                    f"Track and wiggle lines will not appear in the project."
                )

        return {}
