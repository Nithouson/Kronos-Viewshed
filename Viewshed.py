# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Kronos
                                 A QGIS plugin
 This plugin performs viewshed analysis on raster datasets.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2020-12-19
        git sha              : $Format:%H$
        copyright            : (C) 2020 by Kronos Team
        email                : hanwgeek@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt5.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtWidgets import QAction
from qgis.core import (
    QgsRasterLayer,
    QgsProject,
    QgsPointXY,
    QgsPoint,
    QgsRaster,
    QgsRasterShader,
    QgsColorRampShader,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleBandColorDataRenderer,
    QgsSingleBandGrayRenderer,
)

from qgis.gui import QgsMapTool, QgsMapToolEmitPoint

from PIL import Image
import os.path
import numpy as np
import gdal
from math import *

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .Viewshed_dialog import KronosDialog




class Kronos:
    """QGIS Plugin Implementation."""


    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = self.iface.mapCanvas()

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Kronos_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Kronos')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Kronos', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/Viewshed/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Viewshed'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True

        if self.first_start == True:
            self.first_start = False
            self.dlg = KronosDialog()
            self.dlg.btnSelect.clicked.connect(self.select_viewpoint)

            self.emitPoint = QgsMapToolEmitPoint(self.canvas)
            self.emitPoint.canvasClicked.connect(self._get_point)
            self.viewpoint = None


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Kronos'),
                action)
            self.iface.removeToolBarIcon(action)


    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started

        self.dlg.cbxLayer.clear()
        layers = list(QgsProject.instance().mapLayers().values())
        for layer in layers:
            if layer.type() == layer.RasterLayer:
                self.dlg.cbxLayer.addItem(layer.name())
        self.dlg.ledObsH.setText('0')
        self.dlg.cbxAlgo.clear()
        self.dlg.cbxAlgo.addItem("R3")
        self.dlg.cbxAlgo.addItem("XDraw")
        self.dlg.ledFilepath.setText(os.path.join(QgsProject.instance().homePath(), "viewshed.tif"))

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            lid = self.dlg.cbxLayer.currentIndex()
            inputlayer = layers[lid]
            W = inputlayer.width()
            H = inputlayer.height()
            obsX = float(self.dlg.ledXpos.text())
            obsY = float(self.dlg.ledYpos.text())
            obsH = float(self.dlg.ledObsH.text())
            bbox = inputlayer.extent()
            Xmin,Ymin,Xmax,Ymax = bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(),bbox.yMaximum()
            Xres = (Xmax - Xmin)/W
            Yres = (Ymax - Ymin)/H
            if obsX <= Xmin or obsX >= Xmax or obsY <= Ymin or obsY >= Ymax:
                QMessageBox.critical(self.iface.mainWindow(), self.tr("Error"),
                                    self.tr("The observer point is outside the raster extent."))
                return

            mid = self.dlg.cbxAlgo.currentIndex()

            outputlayername = self.dlg.ledOutlayer.text()
            outputpath = self.dlg.ledFilepath.text()
            meta = inputlayer.metadata()

            dem = np.zeros((W,H))
            for c in range(W):
                for r in range(H):
                    dem[c,r], result= inputlayer.dataProvider().sample(QgsPointXY
                                (Xmin + (c+0.5) * Xres, Ymax - (r+0.5) * Yres), 1)

            methods = [Viewshed_R3, Viewshed_XDraw]
            # Grid Coordinates: Topleft(-0.5,-0.5)  BottomRight (W-0.5,H-0.5)
            visible = methods[mid](dem, (obsX-Xmin)/Xres - 0.5, (Ymax-obsY)/Yres - 0.5, obsH)

            im = Image.new('L',(W,H))
            for c in range(W):
                for r in range(H):
                    if visible[c,r] == 0:
                        im.putpixel((c,r),0)
                    else:
                        im.putpixel((c,r),255)
            im.save(outputpath)

            rlayer = QgsRasterLayer(outputpath, outputlayername)

            if not rlayer.isValid():
                print("Layer failed to load!")
            else:
                QgsProject.instance().addMapLayer(rlayer)



    def dist(x1,y1,x2,y2):
        return sqrt((x1-x2)*(x1-x2)+(y1-y2)*(y1-y2))

    def select_viewpoint(self):
        self.canvas.setMapTool(self.emitPoint)

    def _transform_to_image(self, layer, x, y):
        point = layer.dataProvider().transformCoordinates(QgsPoint(x, y), 1)
        return int(point.x()), int(point.y())

    def _transform_to_coords(self, layer, x, y):
        point = layer.dataProvider().transformCoordinates(QgsPoint(x, y), 0)
        return point.x(), point.y()
        
    def _get_layer_array(self, layer):
        ds = gdal.Open(layer.dataProvider().dataSourceUri())
        return ds.GetRasterBand(1).ReadAsArray()

    def _get_point(self, point):
      self.viewpoint = point
      self.dlg.ledXpos.setText("{:.10f}".format(point.x()))
      self.dlg.ledYpos.setText("{:.10f}".format(point.y()))
      self.canvas.unsetMapTool(self.emitPoint)

def Viewshed_XDraw(dem, obsX, obsY, addH):
    terr = get_layer_array(dem)

    x, y = obsX, obsY
    view = np.zeros_like(terr)
    vis = np.zeros_like(view, dtype=bool)
    view[y - 1:y + 2, x - 1:x + 2] = terr[y - 1:y + 2, x - 1:x + 2]
    vis[y - 1:y + 2, x - 1:x + 2] = True
    height = terr[y, x]


    t_height, t_width = terr.shape
    rows = np.array(range(t_width)) - x
    cols = abs(np.array(range(t_height)) - y)[:, None]
    cols[y] = 1

    base = np.tile(rows, (t_height, 1))
    lefts = ((cols - 1) * base) // cols + x
    rights = lefts + 1

    left_ratio = base % cols
    zeros_index = left_ratio == 0
    for i in range(cols.shape[0]):
        left_ratio[i, zeros_index[i]] = cols[i]

    left_ratio = left_ratio / cols
    right_ratio = 1 - left_ratio

    for i in range(1, y):
        r = y - i - 1
        prev_r = r + 1

        left, right = max(0, x - i - 1), min(t_width, x + i + 1)
        los = ((view[prev_r, lefts[prev_r]] * left_ratio[prev_r] + view[prev_r, rights[prev_r]] * right_ratio[prev_r] - height) * cols[r] / (cols[r] - 1) + height)[left:right]
        cur_terr = terr[r, left:right]
        vis[r, left:right] = cur_terr >= los
        view[r, left:right] = np.maximum(cur_terr, los)

    for i in range(1, t_height - y - 1):
        r = y + i + 1
        prev_r = r - 1

        left, right = max(0, x - i), min(t_width, x + i + 2)
        los = ((view[prev_r, lefts[prev_r]] * left_ratio[prev_r] + view[prev_r, rights[prev_r]] * right_ratio[prev_r] - height) * cols[r] / (cols[r] - 1) + height)[left:right]
        cur_terr = terr[r, left:right]
        vis[r, left:right] = cur_terr >= los
        view[r, left:right] = np.maximum(cur_terr, los)

    vis1 = vis

    terr = terr.T
    x, y = obsX, obsY
    view = np.zeros_like(terr)
    vis = np.zeros_like(view, dtype=bool)
    view[y - 1:y + 2, x - 1:x + 2] = terr[y - 1:y + 2, x - 1:x + 2]
    vis[y - 1:y + 2, x - 1:x + 2] = True
    height = terr[y, x]


    t_height, t_width = terr.shape
    rows = np.array(range(t_width)) - x
    cols = abs(np.array(range(t_height)) - y)[:, None]
    cols[y] = 1

    base = np.tile(rows, (t_height, 1))
    lefts = ((cols - 1) * base) // cols + x
    rights = lefts + 1

    left_ratio = base % cols
    zeros_index = left_ratio == 0
    for i in range(cols.shape[0]):
        left_ratio[i, zeros_index[i]] = cols[i]

    left_ratio = left_ratio / cols
    right_ratio = 1 - left_ratio

    for i in range(1, y):
        r = y - i - 1
        prev_r = r + 1

        left, right = max(0, x - i), min(t_width, x + i + 2)
        los = ((view[prev_r, lefts[prev_r]] * left_ratio[prev_r] + view[prev_r, rights[prev_r]] * right_ratio[prev_r] - height) * cols[r] / (cols[r] - 1) + height)[left:right]
        cur_terr = terr[r, left:right]
        vis[r, left:right] = cur_terr >= los
        view[r, left:right] = np.maximum(cur_terr, los)

    for i in range(1, t_height - y - 1):
        r = y + i + 1
        prev_r = r - 1

        left, right = max(0, x - i - 1), min(t_width, x + i + 1)
        los = ((view[prev_r, lefts[prev_r]] * left_ratio[prev_r] + view[prev_r, rights[prev_r]] * right_ratio[prev_r] - height) * cols[r] / (cols[r] - 1) + height)[left:right]
        cur_terr = terr[r, left:right]
        vis[r, left:right] = cur_terr >= los
        view[r, left:right] = np.maximum(cur_terr, los)

    vis = np.bitwise_or(vis1, vis.T)

    return vis

def Viewshed_R3(dem, obsX, obsY, addH):
    W = dem.shape[0]
    H = dem.shape[1]
    visible = np.ones(dem.shape)

    obsX_grid = int(round(obsX))
    obsY_grid = int(round(obsY))
    obsH = dem[obsX_grid, obsY_grid] + addH

    for r in range(H):
        tarY = r
        for c in range(W):
            tarX = c
            tarH = dem[c,r]
            tarA = (tarH - obsH) / dist(obsX,obsY,tarX,tarY)
            if abs(tarY-obsY) > abs(tarX-obsX):
                stepX = (tarX - obsX) / (tarY - obsY)
                if tarY > obsY:
                    midX = obsX
                    for midY in range(obsY_grid+1, tarY):
                        midH = (floor(midX)+1-midX) * dem[int(floor(midX)), midY] \
                               + (midX-floor(midX)) * dem[int(ceil(midX)), midY]
                        midA = (midH-obsH)/dist(obsX, obsY, midX, midY)
                        if midA > tarA:
                            visible[c,r] = 0
                            break
                        midX += stepX
                else:
                    midX = tarX
                    for midY in range(tarY+1 , obsY_grid):
                        midH = (floor(midX)+1-midX) * dem[int(floor(midX)), midY] \
                               + (midX-floor(midX)) * dem[int(ceil(midX)), midY]
                        midA = (midH - obsH) / dist(obsX, obsY, midX, midY)
                        if midA > tarA:
                            visible[c,r] = 0
                            break
                        midX += stepX

            else:
                stepY = (tarY - obsY) / (tarX - obsX)
                if tarX > obsX:
                    midY = obsY
                    for midX in range(obsX_grid+1, tarX):
                        midH = (floor(midY)+1-midY) * dem[midX, int(floor(midY))] \
                               + (midY-floor(midY)) * dem[midX, int(ceil(midY))]
                        midA = (midH - obsH) / dist(obsX, obsY, midX, midY)
                        if midA > tarA:
                            visible[c,r] = 0
                            break
                        midY += stepY
                else:
                    midY = tarY
                    for midX in range(tarX+1, obsX_grid):
                        midH = (floor(midY) + 1 - midY) * dem[midX, int(floor(midY))] \
                               + (midY - floor(midY)) * dem[midX, int(ceil(midY))]
                        midA = (midH - obsH) / dist(obsX, obsY, midX, midY)
                        if midA > tarA:
                            visible[c,r] = 0
                            break
                        midY += stepY
    return visible
