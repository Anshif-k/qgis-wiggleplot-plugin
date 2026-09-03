import os
from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
import processing
from .processing_provider import WigglePlotterProvider

class WigglePlotterPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.action_run = None
        self.action_docs = None
        self.action_about = None
        self.plugin_dir = os.path.dirname(__file__)

    def initProcessing(self):
        self.provider = WigglePlotterProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        
        # Main execution action ("Plot Wiggle") with icon
        self.action_run = QAction(QIcon(icon_path), "Plot Wiggle", self.iface.mainWindow())
        self.action_run.setToolTip("Run WigglePlot Tool")
        self.action_run.triggered.connect(self.run)

        # "Documentation" action with the icon next to it in the menu dropdown
        self.action_docs = QAction(QIcon(icon_path), "Documentation", self.iface.mainWindow())
        self.action_docs.setToolTip("How to use WigglePlot")
        self.action_docs.triggered.connect(self.show_docs)

        # "About WigglePlot" action with the icon next to it in the menu dropdown
        self.action_about = QAction(QIcon(icon_path), "About WigglePlot", self.iface.mainWindow())
        self.action_about.setToolTip("About WigglePlot Plugin")
        self.action_about.triggered.connect(self.show_about)

        # Add actions to the menu dropdown under "WigglePlot"
        self.iface.addPluginToMenu("&WigglePlot", self.action_run)
        self.iface.addPluginToMenu("&WigglePlot", self.action_docs)
        self.iface.addPluginToMenu("&WigglePlot", self.action_about)
        
        # Add only the main tool to the toolbar
        self.addToolBarIconSafe()

    def addToolBarIconSafe(self):
        if self.action_run:
            try:
                self.iface.addToolBarIcon(self.action_run)
            except Exception:
                pass

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
        if self.action_run:
            self.iface.removePluginMenu("&WigglePlot", self.action_run)
            try:
                self.iface.removeToolBarIcon(self.action_run)
            except Exception:
                pass
        if self.action_docs:
            self.iface.removePluginMenu("&WigglePlot", self.action_docs)
        if self.action_about:
            self.iface.removePluginMenu("&WigglePlot", self.action_about)

    def run(self):
        try:
            processing.execAlgorithmDialog('wiggleplot:wiggleline_multicruise_batch')
        except RuntimeError:
            pass

    def show_docs(self):
        docs_text = (
            "How to Plot a Wiggle\n"
            "--------------------------------------------------\n\n"
            "1. Select Data: Click the '...' button next to the input files field and select your profile data files.\n\n"
            "2. Map Columns: Enter the exact column numbers corresponding to Longitude, Latitude, and Anomaly/Z in your data (e.g., 1, 2, 3).\n\n"
            "3. Set Parameters:\n"
            "   - Baseline Method: Choose how to center the profile (subtracting the per-profile mean is recommended for most anomaly data).\n"
            "   - Scale Factor: Define the multiplier to control the wiggle amplitude (Map meters per data unit). 750 is for gravity profile and 150 for magnetic (recommended).\n"
            "   - Azimuth: Leave on 'Auto' to project anomalies perpendicular to the ship track, or specify a fixed angle.\n\n"
            "4. Choose Styling: Select your track/wiggle line colors and pick a Fill Style Mode (e.g., Dual Fill for positive/negative colored lobes).\n\n"
            "5. Configure Output: Select a valid Projected Target CRS (like UTM) for accurate distance scaling, pick an output folder, and click 'Run'. The tool saves modern GeoPackage (.gpkg) files by default, with an option to also export legacy Shapefiles (.shp).\n\n"
            "The resulting track lines and color fills will automatically load into your QGIS Layers panel."
        )
        QMessageBox.information(self.iface.mainWindow(), "WigglePlot Documentation", docs_text)

    def show_about(self):
        about_text = (
            "WigglePlot is developed and maintained by Muhammed Anshif K K.\n\n"
            "Affiliation: CSIR-National Institute of Oceanography (CSIR-NIO)\n\n"
            "WigglePlot is released under the GNU GPL v2.0 license.\n\n"
            "Found a bug? Need a feature?\n"
            "Please report it here:\n"
            "https://github.com/Anshif-k/qgis-wiggleplot-plugin/issues"
        )
        QMessageBox.information(self.iface.mainWindow(), "About WigglePlot", about_text)
