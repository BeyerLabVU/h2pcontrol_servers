import sys
import signal
import time
import asyncio # Added for async operations

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QApplication,
    QHBoxLayout,
    QDialog,
    QMessageBox,
)
from PySide6.QtGui import QColor, QAction
from PySide6.QtCore import Slot

from styled_plot import StyledPlotWidget
from bottom_status_bar import BottomStatusBar
from control_panel import ControlPanel
from settings_panels.run_stop_panel import RunStopPanel
from top_menu_bar import MenuBar
from catchments.data_source import DataSource
from node_dialog import NodeDialog
from operators.data_node import Node, PipelineGraph

# Attempt to import qt_material for theming
try:
    import qt_material
except ImportError:
    qt_material = None

class MainWindow(QMainWindow):
    def __init__(self, loop=None):
        super().__init__()
        self.loop = loop if loop else asyncio.get_event_loop()
        self.active_data_source = None
        self.active_subscription = None
        self.pipeline_graph = PipelineGraph(loop=self.loop)

        self.setWindowTitle("Oscilloscope: Direct Trace View")
        self.setMinimumSize(1920 // 2, 1080 // 2)  # Prevent shrinking too small

        # ---- Status bar & Plot widget ----
        self.plot_status_bar = BottomStatusBar()
        self.plotwidget = StyledPlotWidget(self.plot_status_bar)

        # ---- Data Sources ----
        self.data_sources = {}
        available_stream_names = list(self.data_sources.keys())

        # ---- Control panel (scroll area on the right) ----
        self.control_panel = ControlPanel()
        self.run_stop_panel = RunStopPanel(self.control_panel, available_streams=available_stream_names)
        self.control_panel.add_panel(self.run_stop_panel)

        # ---- Central widget layout ----
        central_widget = QWidget()
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.plotwidget, stretch=1)
        layout.addWidget(self.control_panel, stretch=0)
        self.setCentralWidget(central_widget)

        # Set our custom status bar
        self.setStatusBar(self.plot_status_bar)

        # ---- Build menus via MenuBar helper ----
        self.menu = MenuBar(self, self.plot_status_bar)
        # ---- Data streams menu ----
        graph_menu = self.menu.menubar.addMenu("&Graph")

        self.add_node_action = QAction("Add Node...", parent=self)
        self.edit_node_action = QAction("Edit Node...", parent=self)

        graph_menu.addAction(self.add_node_action)
        graph_menu.addAction(self.edit_node_action)

        self.add_node_action.triggered.connect(self.open_add_node_dialog)
        self.edit_node_action.triggered.connect(self.open_edit_node_dialog)

        self.add_catchment_action = QAction("Add Catchment", parent=self)
        graph_menu.addAction(self.add_catchment_action)
        self.add_node_action.triggered.connect(self.add_catchment_action)

        self.add_diischarge_action = QAction("Add Discharge", parent=self)
        graph_menu.addAction(self.add_diischarge_action)
        self.add_node_action.triggered.connect(self.add_diischarge_action)

        # Connect signals from RunStopPanel
        self.run_stop_panel.stream_selected_signal.connect(self.on_stream_selected)
        self.run_stop_panel.start_data_signal.connect(self.start_selected_data_stream)
        self.run_stop_panel.stop_data_signal.connect(self.stop_current_data_stream)

        # Initialize with the first stream selected, if any
        if available_stream_names:
            self.on_stream_selected(available_stream_names[0])
        else:
            self.plotwidget.clear_all_traces() # Show screensaver if no streams

    @Slot(str)
    def on_stream_selected(self, stream_name: str):
        print(f"MainWindow: Stream selected: {stream_name}")
        if self.active_data_source and self.active_data_source.name == stream_name:
            return

        if self.active_data_source:
            self.stop_current_data_stream()
        
        self.active_data_source = self.data_sources.get(stream_name)
        if self.active_data_source:
            self.plotwidget.setup_traces(self.active_data_source.n_channels)
            if self.run_stop_panel.run_stop_btn.isChecked():
                self.start_selected_data_stream(stream_name)
        else:
            self.plotwidget.clear_all_traces()
            print(f"Warning: Data source '{stream_name}' not found.")

    @Slot(str)
    def start_selected_data_stream(self, stream_name: str):
        print(f"MainWindow: Attempting to start stream: {stream_name}")
        if self.active_subscription:
            self.active_subscription.dispose()
            self.active_subscription = None

        # TODO: rewrite this function, it doesn't match the current paradigm
        if self.active_data_source and self.active_data_source.name == stream_name:
            # Ensure the plot is set up for the correct number of channels
            self.plotwidget.setup_traces(self.active_data_source.n_channels)

            self.active_subscription = self.active_data_source.trace_subject.pipe(
            ).subscribe(
                on_next=self.handle_trace_data,
                on_error=lambda e: print(f"Error from {stream_name}: {e}"),
                on_completed=lambda: print(f"{stream_name} completed")
            )
            asyncio.ensure_future(self.active_data_source.start(), loop=self.loop)
            self.plot_status_bar.update_status(f"Running: {stream_name}")
        else:
            print(f"Error: Stream '{stream_name}' not active or not found for starting.")
            self.run_stop_panel.run_stop_btn.setChecked(False)

    def handle_trace_data(self, trace_data):
        channel_idx = trace_data['channel_idx']
        x_data = trace_data['time_array']
        y_data = trace_data['signal_array']
        self.plotwidget.update_trace_data(channel_idx, x_data, y_data)

    @Slot()
    def stop_current_data_stream(self):
        print("MainWindow: Stopping current data stream")
        if self.active_subscription:
            self.active_subscription.dispose()
            self.active_subscription = None
        if self.active_data_source:
            asyncio.ensure_future(self.active_data_source.stop(), loop=self.loop)
            self.plot_status_bar.update_status(f"Stopped: {self.active_data_source.name}")
        else:
            self.plot_status_bar.update_status("No stream active to stop.")

    def toggle_qt_material_dark_style(self, checked: bool) -> None:
        """Applies or removes the Qt-Material dark theme."""
        app = QApplication.instance()
        if app and qt_material:
            if checked:
                qt_material.apply_stylesheet(app, theme='dark_teal.xml')
            else:
                app.setStyleSheet("")  # type: ignore

            status_text = "enabled" if checked else "disabled"
            self.plot_status_bar.showMessage(f"Qt-Material (Dark) style {status_text}.")

    @Slot()
    def open_add_node_dialog(self):
        # Pops up NodeDialog in 'add' mode.
        dlg = NodeDialog(self.pipeline_graph, mode="add", parent=self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_results()
            node_id = data["id"]
            op_file = data["operator_file"]
            params = data["params"]
            params["operator_file"] = op_file

            # Create the new Node and add it to the graph:
            new_node = Node(node_id, node_type=op_file, params=params, loop=self.loop)
            self.pipeline_graph.add_node(new_node)

            try:
                self.rebind_pipeline()
            except AttributeError:
                pass

            self.plot_status_bar.showMessage(f"Added node '{node_id}'.")

    @Slot()
    def open_edit_node_dialog(self):
        if not self.pipeline_graph.nodes:
            QMessageBox.information(self, "Edit Node", "No nodes to edit. Please add one first.")
            return

        dlg = NodeDialog(self.pipeline_graph, mode="edit", parent=self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_results()
            idx = data["index"]
            node_id = self.pipeline_graph.nodes.keys().__iter__().__next__()  # dummy
            # Actually, NodeDialog already records which index:
            node_id = list(self.pipeline_graph.nodes.keys())[idx]
            op_file = data["operator_file"]
            params = data["params"]
            params["operator_file"] = op_file

            # Update the existing node in-place:
            node = self.pipeline_graph.nodes[node_id]
            node.node_type = op_file
            node.params = params

            # Rebind Rx subscriptions if needed:
            try:
                self.rebind_pipeline()
            except AttributeError:
                pass

            self.plot_status_bar.showMessage(f"Updated node '{node_id}'.")