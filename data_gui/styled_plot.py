import time
import pyqtgraph as pg
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import QVBoxLayout, QWidget, QStatusBar # QLabel removed
from PySide6.QtCore import Qt, QPointF
import numpy as np

from bottom_status_bar import BottomStatusBar

import si_prefix  # <-- Add this import

class DynamicSIAxis(pg.AxisItem):
    def __init__(self, orientation, **kwargs):
        super().__init__(orientation, **kwargs)
        self._scale = 1
        self._format = "{:.3f}"

    def set_si_scale(self, scale):
        self._scale = scale

    def tickStrings(self, values, scale, spacing):
        # Format tick labels using the current SI scale
        try:
            strings = []
            for v in values:
                scaled = v / self._scale
                txt = self._format.format(scaled)
                if "." in txt:
                    txt = txt.rstrip("0").rstrip(".") # Drop trailing zeros and decimal point if necessary
                strings.append(txt)
            return strings
        except Exception:
            return [str(v) for v in values]

class StyledPlotWidget(QWidget):
    """A PlotWidget with a shared style (background, grid, axes, default pen) wrapped in a QWidget with QVBoxLayout."""

    UPDATE_INTERVAL_SEC = 0.05  # 50 ms

    def __init__(self, status_bar: BottomStatusBar, *args, background="#ffffff", grid_alpha=0.3, default_color="#0077bb", **kwargs):
        super().__init__(*args, **kwargs)
        self.main_window_status_bar = status_bar
        self.main_window_status_bar.update_status("Initialized by StyledPlotWidget")
        self._last_crosshair_update = 0.0

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Use custom SI axes
        self.x_axis = DynamicSIAxis('bottom')
        self.y_axis = DynamicSIAxis('left')
        self.plot_widget = pg.PlotWidget(axisItems={'bottom': self.x_axis, 'left': self.y_axis})
        self.plot_widget.getPlotItem().setDownsampling(auto=True)
        self._default_pen = pg.mkPen(color=default_color, width=2)

        self._x_label_base = "Time"
        self._x_unit_base = "s"
        self._y_label_base = "Voltage"
        self._y_unit_base = "V"
        self.x_axis.enableAutoSIPrefix(False)
        self.y_axis.enableAutoSIPrefix(False)

        self._configure(background, grid_alpha)

        self.layout.addWidget(self.plot_widget)

        self.crosshairpen = pg.mkPen(color="#636363", width=2)
        self.vLine = pg.InfiniteLine(angle=90, movable=False, pen=self.crosshairpen)
        self.hLine = pg.InfiniteLine(angle=0, movable=False, pen=self.crosshairpen)
        self.plot_widget.addItem(self.vLine, ignoreBounds=True)
        self.plot_widget.addItem(self.hLine, ignoreBounds=True)
        self.vLine.setVisible(False)
        self.hLine.setVisible(False)

        self.plot_widget.scene().sigMouseMoved.connect(self.mouseMoved)

        # Connect view range change to dynamic axis label/tick update
        self.plot_widget.getPlotItem().sigRangeChanged.connect(self._update_axis_labels_and_ticks)
        self._update_axis_labels_and_ticks()  # Initial call

        # Screen saver
        self.screen_saver_trace()  # Call to generate a trace for the screen saver

    def screen_saver_trace(self):
        t = np.linspace(0, 10e-6, 1000)
        y = 0.1 * np.exp(-t / 3e-6) * np.sin(2 * np.pi * 1e6 * t)
        self.plot_widget.plot(t, y, pen=self._default_pen, name="Screen Saver Trace")

    def _configure(self, background, grid_alpha):
        self.plot_widget.setBackground(background)
        self.plot_widget.showGrid(x=True, y=True, alpha=grid_alpha)

        font = QFont("Times", 10)
        for axis_name in ("bottom", "left"):
            axis = self.plot_widget.getPlotItem().getAxis(axis_name)
            axis.setPen(pg.mkPen(color="#333333", width=1))
            axis.setTextPen(pg.mkPen(color="#333333"))
            axis.setStyle(tickFont=font) # Styles the tick labels

    def plot(self, *args, pen=None, **kwargs):
        if pen is None:
            pen = self._default_pen
        plot_item = self.plot_widget.getPlotItem().plot(*args, pen=pen, **kwargs)
        self.refresh_crosshair()
        return plot_item

    def refresh_crosshair(self):
        if not self.plot_widget.isVisible() or not self.plot_widget.scene():
            self.vLine.setVisible(False)
            self.hLine.setVisible(False)
            if self.main_window_status_bar:
                self.main_window_status_bar.right_label.setText("X: --, Y: --")
            return

        global_mouse_pos = QCursor.pos()
        widget_mouse_pos = self.plot_widget.mapFromGlobal(global_mouse_pos)
        scene_mouse_pos = self.plot_widget.mapToScene(widget_mouse_pos)

        self.mouseMoved(scene_mouse_pos)

    def mouseMoved(self, scene_pos: QPointF):
        """Called on every mouse move; only actually update crosshairs if enough time has passed."""
        now = time.time()
        if now - self._last_crosshair_update < self.UPDATE_INTERVAL_SEC:
            # Too soon: skip this update
            return
        
        self._last_crosshair_update = now
        
        local_mouse_pos = self.plot_widget.mapFromScene(scene_pos)
        if not self.plot_widget.rect().contains(local_mouse_pos):
            self.vLine.setVisible(False)
            self.hLine.setVisible(False)
            if self.main_window_status_bar:
                self.main_window_status_bar.right_label.setText("X: --, Y: --")
            return
        
        # If we get here, at least 30 ms have passed since the last update.
        view_mouse_pos = self.plot_widget.getPlotItem().vb.mapSceneToView(scene_pos)
        x_mouse = view_mouse_pos.x()
        y_display = view_mouse_pos.y()
        
        # Show/move crosshairs
        self.vLine.setPos(x_mouse)
        self.hLine.setPos(y_display)
        self.vLine.setVisible(True)
        self.hLine.setVisible(True)
        
        # If there is a plotted DataItem, interpolate to find the exact y for hLine
        items = self.plot_widget.getPlotItem().listDataItems()
        if items:
            data_item = items[0]
            x_data = data_item.xData
            y_data = data_item.yData
            
            if x_data is not None and y_data is not None and len(x_data) > 0:
                if len(x_data) == 1:
                    y_plot = y_data[0]
                    self.hLine.setPos(y_plot)
                    y_display = y_plot
                else:
                    x_first, x_last = x_data[0], x_data[-1]
                    if x_first < x_last and x_first <= x_mouse <= x_last:
                        y_interp = np.interp(x_mouse, x_data, y_data)
                        self.hLine.setPos(y_interp)
                        y_display = y_interp
        
        # Update status bar coordinates
        if self.main_window_status_bar:
            self.main_window_status_bar.update_coordinates(x_mouse, y_display)

    def _update_axis_labels_and_ticks(self):
        plot_item = self.plot_widget.getPlotItem()
        view_range = plot_item.viewRange()
        x_range = view_range[0]
        y_range = view_range[1]

        # Calculate SI prefix for x and y axes
        x_span = abs(x_range[1] - x_range[0])
        y_span = abs(y_range[1] - y_range[0])

        # Use si_prefix to get formatted string (e.g., '10.0 µ')
        x_str = si_prefix.si_format(x_span, precision=3)
        y_str = si_prefix.si_format(y_span, precision=3)

        # Extract prefix from formatted string
        def extract_prefix(s):
            parts = s.strip().split(' ')
            if len(parts) == 2:
                return parts[1]
            return ''

        x_prefix = extract_prefix(x_str)
        y_prefix = extract_prefix(y_str)

        # Get scale factor from prefix (use "1" + prefix, or 1 if prefix is empty)
        def get_factor(prefix):
            if prefix:
                try:
                    return si_prefix.si_parse("1" + prefix)
                except Exception:
                    return 1
            return 1

        x_factor = get_factor(x_prefix)
        y_factor = get_factor(y_prefix)

        # Set axis labels with SI prefix and unit
        x_label = f"{self._x_label_base} [{x_prefix}{self._x_unit_base}]"
        y_label = f"{self._y_label_base} [{y_prefix}{self._y_unit_base}]"
        plot_item.setLabel("bottom", x_label)
        plot_item.setLabel("left", y_label)

        # Set SI scale for tick formatting
        self.x_axis.set_si_scale(x_factor)
        self.y_axis.set_si_scale(y_factor)