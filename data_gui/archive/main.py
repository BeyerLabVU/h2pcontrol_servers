'''
This is the previous iteration of the GUI code, which is now DEPRECATED.
It is here ONLY for reference and should not be used in new projects.
'''


import sys
import signal
import asyncio
import time

from PySide6.QtWidgets import QApplication, QMainWindow, QSizePolicy, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QColor
import PySide6.QtAsyncio as QtAsyncio
import pyqtgraph as pg
from pyqtgraph.dockarea import DockArea, Dock

from data_source import DataReceiver
from data_processor import DataProcessor
from control_panel import ControlPanel
from settings import SettingsMenu
from plot_settings_panel import PlotAppearanceSettingsPanel
from styled_pw import StyledPlotWidget

# Attempt to import qt_material
try:
    import qt_material
except ImportError:
    qt_material = None # Placeholder if not installed


class SortedDock(Dock):
    """A Dock that sorts its widgets based on a priority attribute."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._widgets = []  # Internal list to keep track of added widgets

    def addWidget(self, widget: QWidget):
        """Adds a widget to the dock and sorts widgets by priority."""
        if hasattr(widget, 'priority'):
            self._widgets.append(widget)
            self._widgets.sort(key=lambda w: getattr(w, 'priority', 0))

            # Clear and re-add widgets in sorted order
            for w in self._widgets:
                super().addWidget(w)
        else:
            raise AttributeError("Widget must have a 'priority' attribute to be added to SortedDock.")

    def removeWidget(self, widget: QWidget):
        """Removes a widget from the dock and re-sorts the remaining widgets."""
        if widget in self._widgets:
            self._widgets.remove(widget)

            # Clear and re-add widgets in sorted order
            for w in self._widgets:
                super().addWidget(w)
        else:
            raise ValueError("Widget not found in SortedDock.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Data GUI")
        self.resize(1200, 800)

        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        exit_action = QAction("&Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        settings_menu = menubar.addMenu("&Settings")
        self.settings_manager = SettingsMenu(settings_menu)

        self.data_sources = [lambda panel: DataReceiver(panel)]  # add more receiver classes here
        self.default_source = lambda panel: DataReceiver(panel)

        self.datasource_manager = menubar.addMenu("&Data Source")
        self.view_manager = menubar.addMenu("&View")

        for source_cls in self.data_sources:
            name    = getattr(source_cls(None), "menu_name", source_cls.__name__)
            tip     = getattr(source_cls(None), "menu_tooltip", "")
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

        self.dock_area = DockArea()
        self.setCentralWidget(self.dock_area)

        # Traces
        self.trace_plot = StyledPlotWidget()
        self.trace_plot_items = {} # Dictionary to store plot items by channel_idx
        self.trace_dock = Dock("Traces", size=(int(self.width() * 0.75), int(self.height() * 0.6))) # Approximate initial size
        self.trace_dock.addWidget(self.trace_plot)
        self.dock_area.addDock(self.trace_dock, 'left')

        # Results
        self.results_plot = StyledPlotWidget(default_color="#dd7700")
        self.results_dock = Dock("Results", size=(int(self.width() * 0.75), int(self.height() * 0.4))) # Approximate initial size
        
        self.results_dock.addWidget(self.results_plot)
        self.dock_area.addDock(self.results_dock, 'bottom', self.trace_dock) # Place below trace_dock

        # Control Panel
        self.control_panel = ControlPanel()  # Instantiate the new ControlPanel
        self.control_dock = Dock("Settings")  # Approximate initial size
        self.control_dock.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.control_dock.addWidget(self.control_panel)  # Add the ControlPanel instance

        # Dynamically set the minimum width based on the ControlPanel's size hint
        width = 330  # Default minimum width
        self.control_dock.setMinimumWidth(width)
        self.control_dock.setMaximumWidth(width)

        self.dock_area.addDock(self.control_dock, 'right')

        # Add specific settings panels to the ControlPanel
        self._setup_plot_appearance_settings()

        # Save the initial dock state after all docks are added and arranged
        self.initial_dock_state = self.dock_area.saveState()

        # # Add dock toggle actions to the View menu
        # self.view_manager.addAction(self.trace_dock.toggleViewAction())
        # self.view_manager.addAction(self.results_dock.toggleViewAction())
        # self.view_manager.addAction(self.control_dock.toggleViewAction())

        # Qt-Material Dark style toggle action
        self.qt_material_dark_action = QAction("Enable Qt-Material (Dark)", self)
        self.qt_material_dark_action.setCheckable(True)
        self.qt_material_dark_action.triggered.connect(self.toggle_qt_material_dark_style)
        self.view_manager.addAction(self.qt_material_dark_action)

        if qt_material is None:
            self.qt_material_dark_action.setEnabled(False)
            self.qt_material_dark_action.setToolTip(
                "qt_material not installed. Run: pip install qt-material"
            )
        else:
            self.qt_material_dark_action.setToolTip("Toggle Qt-Material dark theme.")
        self.view_manager.addSeparator()

        # Action to restore default dock layout
        restore_layout_action = QAction("Restore Default Layout", self)
        restore_layout_action.triggered.connect(self.restore_default_dock_layout)
        self.view_manager.addAction(restore_layout_action)

        # instantiate the default receiver
        self.receiver = self.default_source(self.control_panel)
        self.processor    = DataProcessor(roi=(0, 50))
        self.results_data = []

        self._connect_receiver_signals() # Connect signals from the new receiver

        # plot‐line handles
        # self.trace_line   = self.trace_plot.plot() # Old single trace line
        self.results_line = self.results_plot.plot()

        # status bar
        self.statusBar().showMessage("Ready")

        # placeholders for our asyncio task & timing
        self._data_task     = None
        self._last_receive  = None

    def _setup_plot_appearance_settings(self):
        """Sets up and adds the plot appearance settings panel."""
        # Determine initial style for the results plot
        # StyledPlotWidget for results_plot uses default_color="#dd7700"
        # and its _default_pen has width=2.
        results_initial_color = QColor("#dd7700")
        results_initial_thickness = 2

        self.results_appearance_panel = PlotAppearanceSettingsPanel(
            title="Results Plot Style",
            initial_color=results_initial_color,
            initial_thickness=results_initial_thickness,
            parent=self.control_panel # Parent for proper object lifetime management
        )
        self.control_panel.add_panel(self.results_appearance_panel)

        # Connect signals to update the plot pen
        self.results_appearance_panel.color_changed.connect(self._update_results_plot_pen)
        self.results_appearance_panel.thickness_changed.connect(self._update_results_plot_pen)

    def _update_results_plot_pen(self, _=None): # Slot can receive emitted value, but we use panel's state
        """Updates the pen of the results_line based on the settings panel."""
        if hasattr(self, 'results_line') and self.results_line and hasattr(self, 'results_appearance_panel'):
            new_pen = self.results_appearance_panel.get_current_pen()
            self.results_line.setPen(new_pen)

    def toggle_qt_material_dark_style(self, checked: bool) -> None:
        """Applies or removes the Qt-Material dark_teal stylesheet."""
        app = QApplication.instance()
        if app and qt_material:
            if checked:
                # You can choose other themes from qt_material, e.g., 'dark_blue.xml'
                qt_material.apply_stylesheet(app, theme='dark_teal.xml')
            else:
                app.setStyleSheet("") # type: ignore # Revert to default or QStyleFactory style
            # Update the status bar or log
            status = "enabled" if checked else "disabled"
            self.statusBar().showMessage(f"Qt-Material (Dark) style {status}.")


    def restore_default_dock_layout(self):
        """Restores the dock layout to its initial configuration."""
        self.dock_area.restoreState(self.initial_dock_state)

    def switch_data_source(self, source_cls):
        # TODO: add logic to reset control panel.
        """Cancel the old loop, clear plots, re-init receiver, restart."""
        # 1) cancel
        if self._data_task:
            self._data_task.cancel()

        # 2) clear history and plots
        self.results_data.clear()
        # self.trace_line.setData([], []) # Old single trace line
        for item in self.trace_plot_items.values():
            item.setData([], []) # Clear data for each trace item
        # self.trace_plot.clear() # Alternative: Clears all items, might need to re-add axes, labels etc.
        # Or, more selectively:
        # for ch_idx in list(self.trace_plot_items.keys()): # Iterate over a copy of keys
        #     item_to_remove = self.trace_plot_items.pop(ch_idx)
        #     self.trace_plot.removeItem(item_to_remove)
        # self.trace_plot_items.clear() # Ensure the dictionary is empty

        self.trace_plot.refresh_crosshair() # Update crosshair after clearing
        self.results_line.setData([], [])
        self.results_plot.refresh_crosshair() # Update crosshair after clearing

        # 3) new receiver
        if self.receiver: # Disconnect old receiver's signals if it exists
            try:
                self.receiver.trace_color_changed.disconnect(self._handle_trace_color_changed)
                self.receiver.trace_display_changed.disconnect(self._handle_trace_display_changed)
            except (TypeError, RuntimeError): #TypeError if no connections, RuntimeError if obj deleted
                pass 
        self.receiver = source_cls(self.control_panel)
        self._connect_receiver_signals() # Connect new receiver's signals

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
        # TODO: we can keep collecting data separately, but we should setData once per cycle so we're not double-drawing.
        now = time.perf_counter()
        self._last_receive = now
        self._last_channel = -1
        self._channel_skips = 0
        try:
            # get_trace now yields (channel_idx, t, signal) for multi-channel sources
            async for data_tuple in self.receiver.get_trace(): 
                channel_idx, t, signal = data_tuple

                # measure arrival interval
                now = time.perf_counter()
                if (self._last_channel == -1) or (self._channel_skips > 10): # Assign new channel to measure intervals
                    self._last_channel = channel_idx
                if channel_idx == self._last_channel:
                    interval_ms = (now - self._last_receive) * 1e3
                    self._last_receive = now
                    self._channel_skips = 0
                else:
                    self._channel_skips += 1 # If there hasn't been the recurring channel for a while, this counter triggers a reassignment.

                # draw timing
                t0 = time.perf_counter()
                
                # Get or create plot item for the channel
                if channel_idx not in self.trace_plot_items:
                    # Create a new plot item if it doesn't exist for this channel
                    # Use a default color or fetch from control panel if already set
                    # For now, using default plot color. Color will be updated by _handle_trace_color_changed
                    new_plot_item = self.trace_plot.plot() 
                    self.trace_plot_items[channel_idx] = new_plot_item
                
                plot_item = self.trace_plot_items[channel_idx]
                plot_item.setData(t, signal)
                self.trace_plot.refresh_crosshair() # Refresh crosshair after data update

                # process & plot results
                if channel_idx == 0:
                    val = self.processor.process((t, signal))
                    self.results_data.append(val)
                    self.results_line.setData(range(len(self.results_data)),
                                            self.results_data)
                    self.results_plot.refresh_crosshair() # Refresh crosshair after data update

                draw_ms = (time.perf_counter() - t0) * 1e3

                # show in status bar
                self.statusBar().showMessage(
                    f"Interval: {interval_ms:6.2f} ms   |   Draw: {draw_ms:6.2f} ms"
                )
        except asyncio.CancelledError:
            # task was cancelled by switch_data_source()
            pass

    def _connect_receiver_signals(self):
        if self.receiver:
            # Check if the receiver has the signals before connecting
            if hasattr(self.receiver, 'trace_color_changed'):
                self.receiver.trace_color_changed.connect(self._handle_trace_color_changed)
            if hasattr(self.receiver, 'trace_display_changed'):
                self.receiver.trace_display_changed.connect(self._handle_trace_display_changed)
            

    def _handle_trace_color_changed(self, channel_idx: int, color_tuple: tuple):
        """Handles the trace_color_changed signal from the DataReceiver."""
        if channel_idx in self.trace_plot_items:
            plot_item = self.trace_plot_items[channel_idx]
            q_color = QColor(*color_tuple)
            plot_item.setPen(pg.mkPen(color=q_color, width=plot_item.opts.get('pen', pg.mkPen()).width()))
        else:
            # This might happen if the control panel is created before the first trace data arrives.
            # We can either pre-create plot_items or ensure color is applied when item is created.
            # For now, we'll create it here if it's missing, assuming a plot should exist.
            # This part might need refinement based on exact application flow.
            new_plot_item = self.trace_plot.plot(pen=pg.mkPen(color=QColor(*color_tuple)))
            self.trace_plot_items[channel_idx] = new_plot_item

    def _handle_trace_display_changed(self, channel_idx: int, is_visible: bool):
        """Handles the trace_display_changed signal from the DataReceiver."""
        if channel_idx in self.trace_plot_items:
            plot_item = self.trace_plot_items[channel_idx]
            if is_visible:
                plot_item.show()
            else:
                plot_item.hide()
        elif is_visible: # If item doesn't exist but should be visible, create it
            # This case implies a trace should be shown but its item hasn't been created by update_data yet.
            # It's generally better if update_data creates items first.
            # For now, create with default pen; color/other attributes will be set if their signals fire.
            new_plot_item = self.trace_plot.plot()
            self.trace_plot_items[channel_idx] = new_plot_item
            new_plot_item.show()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *args: QApplication.quit())
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    async def run_app():
        window.start_data_loop() # Start the data acquisition loop
        await asyncio.sleep(0) # Keep the asyncio loop running for Qt interactions

    if sys.platform == "win32": # SIGINT handling for Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    QtAsyncio.run(run_app(), handle_sigint=True)