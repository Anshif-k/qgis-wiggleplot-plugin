import os
from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon
from .algorithm import MultiCruiseWiggleBatch

class WigglePlotterProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(MultiCruiseWiggleBatch())

    def id(self):
        return 'wiggleplot'

    def name(self):
        return 'Geophysics'

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QgsProcessingProvider.icon(self)

    def longName(self):
        return 'Geophysics'
