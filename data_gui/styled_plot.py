import time
import pyqtgraph as pg
import numpy as np
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import QVBoxLayout, QWidget
from PySide6.QtCore import Qt, QPointF

from bottom_status_bar import BottomStatusBar

import si_prefix

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
                    txt = txt.rstrip("0").rstrip(".")  # Drop trailing zeros/decimal point
                strings.append(txt)
            return strings
        except Exception:
            return [str(v) for v in values]


class StyledPlotWidget(QWidget):
    """A PlotWidget with a shared style (background, grid, axes, default pen)
    wrapped in a QWidget with QVBoxLayout. Now with fixed crosshair behavior.
    """

    UPDATE_INTERVAL_SEC = 0.05  # 50 ms throttle for crosshair updates

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
        self.vLine.setVisible(False)
        self.hLine.setVisible(False)

        # Grab the ViewBox and add crosshairs there:
        self.plot_item = self.plot_widget.getPlotItem()
        self.vb = self.plot_item.vb
        self.vb.addItem(self.vLine, ignoreBounds=True)
        self.vb.addItem(self.hLine, ignoreBounds=True)

        # Attach sigMouseMoved to the ViewBox scene
        self.vb.scene().sigMouseMoved.connect(self.mouseMoved)

        # For storing actual data traces
        self.plot_data_items = []

        # Connect view range change to dynamic axis label/tick update
        self.plot_item.sigRangeChanged.connect(self._update_axis_labels_and_ticks)
        self._update_axis_labels_and_ticks()  # Do an initial labeling

        # Screen saver
        self.screen_saver_trace()

    def screen_saver_trace(self):
        t = np.linspace(0, 10e-6, 1000)
        y = 0.1 * np.exp(-t / 3e-6) * np.sin(2 * np.pi * 1e6 * t)
        if not hasattr(self, '_screen_saver_item') or not self._screen_saver_item:
            self._screen_saver_item = self.plot_widget.plot(t, y, pen=self._default_pen, name="Screen Saver Trace")
        else:
            self._screen_saver_item.setData(t, y)
        self._screen_saver_item.setVisible(True)

    def setup_traces(self, num_channels: int):
        if hasattr(self, '_screen_saver_item') and self._screen_saver_item:
            self._screen_saver_item.setVisible(False)

        for item in self.plot_data_items:
            self.plot_widget.removeItem(item)
        self.plot_data_items = []

        colors = ['#0077bb', '#ff0000', '#00ff00', '#ff00ff', '#00ffff', '#ffff00']
        for i in range(num_channels):
            pen_color = colors[i % len(colors)]
            pen = pg.mkPen(color=pen_color, width=2)
            plot_item = self.plot_widget.plot(pen=pen, name=f"Channel {i+1}")
            self.plot_data_items.append(plot_item)

    def update_trace_data(self, channel_index: int, x_data, y_data):
        if 0 <= channel_index < len(self.plot_data_items):
            self.plot_data_items[channel_index].setData(x_data, y_data)
            self.refresh_crosshair()  # Refresh crosshair after updating data

    def clear_all_traces(self):
        for item in self.plot_data_items:
            self.plot_widget.removeItem(item)
        self.plot_data_items = []
        if hasattr(self, '_screen_saver_item') and self._screen_saver_item:
            self._screen_saver_item.setVisible(True)
        else:
            self.screen_saver_trace()

    def _configure(self, background, grid_alpha):
        self.plot_widget.setBackground(background)
        self.plot_widget.showGrid(x=True, y=True, alpha=grid_alpha)

        font = QFont("Times", 10)
        for axis_name in ("bottom", "left"):
            axis = self.plot_widget.getAxis(axis_name)
            axis.setTickFont(font)
            axis.setLabel(font=font)

    def plot(self, *args, pen=None, **kwargs):
        if pen is None:
            pen = self._default_pen
        plot_item = self.plot_item.plot(*args, pen=pen, **kwargs)
        self.refresh_crosshair()
        return plot_item

    def refresh_crosshair(self):
        if not self.plot_widget.isVisible() or not self.plot_widget.scene():
            return
        global_mouse_pos = QCursor.pos()
        widget_mouse_pos = self.plot_widget.mapFromGlobal(global_mouse_pos)
        scene_mouse_pos = self.plot_widget.mapToScene(widget_mouse_pos)
        self.mouseMoved(scene_mouse_pos)

    def mouseMoved(self, scene_pos: QPointF):
        """Called on every mouse‐move over the ViewBox’s scene."""
        now = time.time()
        if now - self._last_crosshair_update < self.UPDATE_INTERVAL_SEC:
            return

        self._last_crosshair_update = now

        # Check if the mouse is inside the ViewBox bounding rect
        if not self.vb.sceneBoundingRect().contains(scene_pos):
            # Mouse is outside the plot‐area
            self.vLine.setVisible(False)
            self.hLine.setVisible(False)
            if self.main_window_status_bar:
                self.main_window_status_bar.clear_coordinates()
            return

        # Map from scene -> data coordinates via the ViewBox
        view_mouse_pos = self.vb.mapSceneToView(scene_pos)
        x_mouse = view_mouse_pos.x()
        y_display = view_mouse_pos.y()

        # Move and show crosshairs
        self.vLine.setPos(x_mouse)
        self.vLine.setVisible(True)

        # If there is a data trace, do a simple interpolation on the first visible trace
        items = self.plot_item.listDataItems()
        y_interp = None
        if items:
            item = items[0]
            x_data, y_data = item.getData()
            if x_data is not None and len(x_data) > 0:
                idx = np.searchsorted(x_data, x_mouse)
                if idx <= 0:
                    y_interp = y_data[0]
                elif idx >= len(x_data):
                    y_interp = y_data[-1]
                else:
                    x0, x1 = x_data[idx - 1], x_data[idx]
                    y0, y1 = y_data[idx - 1], y_data[idx]
                    y_interp = y0 + (y1 - y0) * (x_mouse - x0) / (x1 - x0)

        # Update status bar coordinates (if available)
        if self.main_window_status_bar:
            if y_interp is not None:
                self.main_window_status_bar.update_coordinates(x_mouse, y_interp)
                self.hLine.setPos(y_interp)
            else:
                self.main_window_status_bar.update_coordinates(x_mouse, y_display)
                self.hLine.setPos(y_display)
        self.hLine.setVisible(True)

    def _update_axis_labels_and_ticks(self):
        plot_item = self.plot_item
        view_range = plot_item.viewRange()
        x_range = view_range[0]
        y_range = view_range[1]

        x_span = abs(x_range[1] - x_range[0])
        y_span = abs(y_range[1] - y_range[0])

        x_str = si_prefix.si_format(x_span, precision=3)
        y_str = si_prefix.si_format(y_span, precision=3)

        def extract_prefix(s):
            parts = s.strip().split(' ')
            if len(parts) == 2:
                return parts[1]
            return ''

        x_prefix = extract_prefix(x_str)
        y_prefix = extract_prefix(y_str)

        def get_factor(prefix):
            if prefix:
                try:
                    return si_prefix.si_parse("1" + prefix)
                except Exception:
                    return 1
            return 1

        x_factor = get_factor(x_prefix)
        y_factor = get_factor(y_prefix)

        x_label = f"{self._x_label_base} [{x_prefix}{self._x_unit_base}]"
        y_label = f"{self._y_label_base} [{y_prefix}{self._y_unit_base}]"
        plot_item.setLabel("bottom", x_label)
        plot_item.setLabel("left", y_label)

        self.x_axis.set_si_scale(x_factor)
        self.y_axis.set_si_scale(y_factor)
