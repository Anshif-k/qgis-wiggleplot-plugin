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

        # "About WigglePlot" action with the icon next to it in the menu dropdown
        self.action_about = QAction(QIcon(icon_path), "About WigglePlot", self.iface.mainWindow())
        self.action_about.setToolTip("About WigglePlot Plugin")
        self.action_about.triggered.connect(self.show_about)

        # Add actions to the menu dropdown under "WigglePlot"
        self.iface.addPluginToMenu("&WigglePlot", self.action_run)
        self.iface.addPluginToMenu("&WigglePlot", self.action_about)
        
        # Add only the main tool to the toolbar
        self.iface.addToolBarIcon(self.action_run)

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
        if self.action_run:
            self.iface.removePluginMenu("&WigglePlot", self.action_run)
            self.iface.removeToolBarIcon(self.action_run)
        if self.action_about:
            self.iface.removePluginMenu("&WigglePlot", self.action_about)

    def run(self):
        processing.execAlgorithmDialog('wiggleplot:wiggleline_multicruise_batch')

    def show_about(self):
        about_text = (
            "WigglePlot is currently being developed and maintained by Muhammed Anshif K K.\n\n"
            "WigglePlot is released under the GNU GPL v2.0 license.\n\n"
            "Found a bug? Need a feature?\n"
            "Please report it here:\n"
            "https://github.com/Anshif-k/qgis-wiggleplot-plugin/issues"
        )
        QMessageBox.information(self.iface.mainWindow(), "About WigglePlot", about_text)