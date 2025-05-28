import sys
import signal
import asyncio
import time

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFormLayout,
    QLineEdit, QSpinBox, QScrollArea, QDockWidget, 
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
import PySide6.QtAsyncio as QtAsyncio
import pyqtgraph as pg

from data_source import DataReceiver
from data_processor import DataProcessor
from settings import SettingsMenu


class StyledPlotWidget(pg.PlotWidget):
    """A PlotWidget with a shared style (background, grid, axes, default pen)."""
    def __init__(self, *args, background="#ffffff", grid_alpha=0.3, default_color="#0077bb", **kwargs):
        super().__init__(*args, **kwargs)
        self._default_pen = pg.mkPen(color=default_color, width=2)
        self._configure(background, grid_alpha)

    def _configure(self, background, grid_alpha):
        # Background
        self.setBackground(background)

        # Grid
        self.showGrid(x=True, y=True, alpha=grid_alpha)

        # Axis styling
        font = QFont("Arial", 10)
        for axis_name in ("bottom", "left"):
            axis = self.getPlotItem().getAxis(axis_name)
            axis.setPen(pg.mkPen(color="#333333", width=1))
            axis.setTextPen(pg.mkPen(color="#333333"))
            axis.setStyle(tickFont=font)
            self.getAxis("bottom").label.setFont(font)
            self.getAxis("left").label.setFont(font)

    def plot(self, *args, pen=None, **kwargs):
        # Delegate to the PlotItem, using default pen if none provided
        if pen is None:
            pen = self._default_pen
        return self.getPlotItem().plot(*args, pen=pen, **kwargs)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data GUI")
        self.resize(1200, 800)

        # ─── menu bar ──────────────────────────────────────────────────────
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        exit_action = QAction("&Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        settings_menu = menubar.addMenu("&Settings")
        self.settings_manager = SettingsMenu(settings_menu)

        # --- Data Source menu setup ---------------------------------------
        self.data_sources = [DataReceiver]  # add more receiver classes here
        self.default_source = DataReceiver

        self.datasource_manager = menubar.addMenu("&Data Source")

        for source_cls in self.data_sources:
            name    = getattr(source_cls, "menu_name", source_cls.__name__)
            tip     = getattr(source_cls, "menu_tooltip", "")
            action  = QAction(name, self)
            action.setToolTip(tip)
            action.setCheckable(True)
            if source_cls is self.default_source:
                action.setChecked(True)
            # when triggered, call switch_data_source with that class
            action.triggered.connect(
                lambda checked, src=source_cls: self.switch_data_source(src)
            )
            self.datasource_manager.addAction(action)

        # --- View menu toggles for docks ----------------------------------
        self.view_manager = menubar.addMenu("&View")

        # ─── docks & plots ─────────────────────────────────────────────────
        # Traces
        self.trace_plot = StyledPlotWidget()
        self.trace_dock = QDockWidget("Traces", self)
        self.trace_dock.setWidget(self.trace_plot)
        self.trace_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.trace_dock)
        self.view_manager.addAction(self.trace_dock.toggleViewAction())

        # Results
        self.results_plot = StyledPlotWidget(default_color="#dd7700")
        self.results_dock = QDockWidget("Results", self)
        self.results_dock.setWidget(self.results_plot)
        self.results_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.results_dock)
        self.splitDockWidget(self.trace_dock, self.results_dock, Qt.Vertical)
        self.view_manager.addAction(self.results_dock.toggleViewAction())

        # Settings
        settings_content = QWidget()
        settings_layout  = QFormLayout(settings_content)
        settings_layout.addRow("Parameter 1:", QLineEdit())
        settings_layout.addRow("Parameter 2:", QSpinBox())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(settings_content)
        self.control_dock = QDockWidget("Settings", self)
        self.control_dock.setWidget(scroll)
        self.control_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, self.control_dock)
        self.control_dock.setMinimumWidth(250)
        self.control_dock.setMaximumWidth(250)
        self.setDockNestingEnabled(True)
        self.view_manager.addAction(self.control_dock.toggleViewAction())

        left_w  = int(self.width() * 0.8)
        right_w = self.width() - left_w
        self.resizeDocks(
            [self.trace_dock, self.control_dock],
            [left_w, right_w],
            Qt.Horizontal
        )
        
        # instantiate the default receiver
        self.receiver = self.default_source()
        self.processor    = DataProcessor(roi=(0, 50))
        self.results_data = []

        # plot‐line handles
        self.trace_line   = self.trace_plot.plot()
        self.results_line = self.results_plot.plot()

        # status bar
        self.statusBar().showMessage("Ready")

        # placeholders for our asyncio task & timing
        self._data_task     = None
        self._last_receive  = None


    def switch_data_source(self, source_cls):
        """Cancel the old loop, clear plots, re-init receiver, restart."""
        # 1) cancel
        if self._data_task:
            self._data_task.cancel()

        # 2) clear history
        self.results_data.clear()
        self.trace_line.setData([], [])
        self.results_line.setData([], [])

        # 3) new receiver
        self.receiver = source_cls()

        # 4) reset timer and restart
        self._last_receive = time.perf_counter()
        self._data_task    = asyncio.create_task(self.update_data())

        self.statusBar().showMessage(
            f"Switched data source to {getattr(source_cls,'menu_name',source_cls.__name__)}"
        )


    def start_data_loop(self):
        """Kick off the first update_data() task."""
        self._last_receive = time.perf_counter()
        self._data_task    = asyncio.create_task(self.update_data())


    async def update_data(self):
        now = time.perf_counter()
        self._last_receive = now
        try:
            async for t, signal in self.receiver.get_trace():
                # measure arrival interval
                now = time.perf_counter()
                interval_ms = (now - self._last_receive) * 1e3
                self._last_receive = now

                # draw timing
                t0 = time.perf_counter()
                self.trace_line.setData(t, signal)

                # process & plot results
                val = self.processor.process((t, signal))
                self.results_data.append(val)
                self.results_line.setData(range(len(self.results_data)),
                                         self.results_data)

                draw_ms = (time.perf_counter() - t0) * 1e3

                # show in status bar
                self.statusBar().showMessage(
                    f"Interval: {interval_ms:6.2f} ms   |   Draw: {draw_ms:6.2f} ms"
                )
        except asyncio.CancelledError:
            # task was cancelled by switch_data_source()
            pass


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *args: QApplication.quit())
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    QtAsyncio.run(window.update_data(), handle_sigint=True)
