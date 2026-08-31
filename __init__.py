def classFactory(iface):
    from .plugin import WigglePlotterPlugin
    return WigglePlotterPlugin(iface)