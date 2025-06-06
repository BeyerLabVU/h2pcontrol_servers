import importlib.util
import inspect
import sys
import asyncio # Added for async operations

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QApplication,
    QHBoxLayout,
    QDialog,
    QMessageBox,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Slot

from discharges.styled_plot import StyledPlotWidget
from bottom_status_bar import BottomStatusBar
from control_panel import ControlPanel
from settings_panels.run_stop_panel import RunStopPanel
from settings_panels.plot_manager_panel import PlotManagerPanel
from top_menu_bar import MenuBar

from node_dialog import NodeDialog
from data_node import Node, PipelineGraph

from catchments.data_source import DataSource
from catchments.test_source_node import CatchmentNode
from discharges.plot_node import PlotNode

# Attempt to import qt_material for theming
try:
    import qt_material
except ImportError:
    qt_material = None


def load_node_subclass_from_file(file_path):
    """Dynamically load a Node subclass from a Python file."""
    module_name = f"custom_node_{hash(file_path)}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None:
        raise ImportError(f"Could not load spec from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore

    # Find all subclasses of Node in the module
    node_subclasses = [
        obj for name, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, Node) and obj is not Node
    ]
    if not node_subclasses:
        raise ValueError(f"No subclass of Node found in {file_path}")
    if len(node_subclasses) > 1:
        print(f"Warning: Multiple Node subclasses found in {file_path}, using the first one.")

    return node_subclasses[0]


class MainWindow(QMainWindow):
    def __init__(self, loop=None):
        super().__init__()
        self.loop = loop if loop else asyncio.get_event_loop()
        self.active_data_source = None
        self.active_subscription = None
        self.pipeline_graph = PipelineGraph(loop=self.loop)
        self.active_plot_subscription = None  # For PlotNode input
        self.active_stream_node_id = None

        self.setWindowTitle("Oscilloscope: Direct Trace View")
        self.setMinimumSize(1920 // 2, 1080 // 2)  # Prevent shrinking too small
        
        # ---- Status bar & Plot widget ----
        self.plot_status_bar = BottomStatusBar()
        self.plotwidget = StyledPlotWidget(self.plot_status_bar)
        
        # ---- Multiple PlotNodes for different traces ----
        self.plot_nodes = {}  # Changed to dict for easier management by node_id
        self.num_traces = 3  # Default number of traces, can be made configurable
        
        # Define colors for different traces
        trace_colors = ['#0077bb', '#ff0000', '#00ff00', '#ff00ff', '#00ffff', '#ffff00']
        
        # Create initial PlotNode instances, one for each trace
        for i in range(self.num_traces):
            color = trace_colors[i % len(trace_colors)]
            node_id = f"plot_trace_{i}"
            plot_node = PlotNode(
                node_id, 
                self.plotwidget, 
                trace_index=i, 
                trace_color=color,
                loop=self.loop
            )
            self.plot_nodes[node_id] = plot_node
            self.pipeline_graph.add_node(plot_node)

        # ---- Data Sources ----
        self.data_sources = {}
        available_stream_names = list(self.data_sources.keys())
        
        # ---- Control panel (scroll area on the right) ----
        self.control_panel = ControlPanel()
        self.run_stop_panel = RunStopPanel(self.control_panel, available_streams=available_stream_names)
        self.control_panel.add_panel(self.run_stop_panel)
        
        # Add plot manager panel
        self.plot_manager_panel = PlotManagerPanel(self.control_panel, max_traces=10)
        self.control_panel.add_panel(self.plot_manager_panel)
        
        # Connect plot manager signals
        self.plot_manager_panel.create_plot_node_signal.connect(self.create_plot_node)
        self.plot_manager_panel.destroy_plot_node_signal.connect(self.destroy_plot_node)
        self.plot_manager_panel.clear_all_plot_nodes_signal.connect(self.clear_all_plot_nodes)
        
        # Sync the plot manager with initial plot nodes
        self.plot_manager_panel.sync_with_plot_nodes(self.plot_nodes)

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
        graph_menu.addAction(self.add_node_action)
        self.add_node_action.triggered.connect(self.open_add_node_dialog)

        self.edit_node_action = QAction("Edit Node...", parent=self)
        graph_menu.addAction(self.edit_node_action)
        self.edit_node_action.triggered.connect(self.open_edit_node_dialog)

        self.add_catchment_action = QAction("Add Catchment", parent=self)
        graph_menu.addAction(self.add_catchment_action)

        self.add_discharge_action = QAction("Add Discharge", parent=self)
        graph_menu.addAction(self.add_discharge_action)

        graph_menu.addSeparator()

        self.add_test_catchment_action = QAction("Add Test Catchment", parent=self)
        graph_menu.addAction(self.add_test_catchment_action)
        self.test_catchment_initialized = False
        self.add_test_catchment_action.triggered.connect(self.configure_test_catchment)

        # Connect signals from RunStopPanel
        self.run_stop_panel.stream_selected_signal.connect(self.on_stream_selected)
        self.run_stop_panel.start_data_signal.connect(self.start_selected_data_stream)
        self.run_stop_panel.stop_data_signal.connect(self.stop_current_data_stream)

        # Initialize with the first stream selected, if any
        if available_stream_names:
            self.on_stream_selected(available_stream_names[0])
        else:
            self.plotwidget.clear_all_traces() # Show screensaver if no streams

    def configure_test_catchment(self) -> None:
        test_source = CatchmentNode(
            node_id="test_catchment",
            data_source=DataSource(), 
        )
        if not self.test_catchment_initialized:            
            self.pipeline_graph.add_node(test_source)
            self.plot_status_bar.showMessage(f"Added test catchment node '{test_source.id}'.")
            self.loop.create_task(test_source.data_source.start())
            # Optionally update available streams and RunStopPanel
            self.data_sources[test_source.id] = test_source.data_source
            self.run_stop_panel.update_available_streams(list(self.data_sources.keys()))
            self.test_catchment_initialized = True
            self.add_test_catchment_action.setEnabled(False)  # Disable after adding
    
    @Slot(str)
    def on_stream_selected(self, stream_name: str):
        print(f"MainWindow: Stream selected: {stream_name}")
        # Unsubscribe all PlotNodes from previous input
        if self.active_stream_node_id:
            try:
                for plot_node in self.plot_nodes.values():
                    plot_node.unsubscribe_from_input(self.active_stream_node_id)
            except Exception as e:
                print(f"Error unsubscribing plot nodes: {e}")
            self.active_stream_node_id = None
        
        # Find the node in the pipeline corresponding to the stream
        stream_node = self.pipeline_graph.nodes.get(stream_name)
        if stream_node:
            # For now, connect all traces to the same stream (single-channel)
            # In the future, this could be enhanced to support multi-channel streams
            for plot_node in self.plot_nodes.values():
                plot_node.subscribe_to_input(stream_node)
            self.active_stream_node_id = stream_node.id
            self.plotwidget.clear_all_traces()
        else:
            self.plotwidget.clear_all_traces()
            print(f"Warning: Stream node '{stream_name}' not found in pipeline.")

    @Slot(str)
    def start_selected_data_stream(self, stream_name: str):
        print(f"MainWindow: Attempting to start stream: {stream_name}")
        # Start the data source if available
        data_source = self.data_sources.get(stream_name)
        if data_source:
            asyncio.ensure_future(data_source.start(), loop=self.loop)
            self.plot_status_bar.update_status(f"Running: {stream_name}")
        else:
            print(f"Error: Stream '{stream_name}' not active or not found for starting.")

    @Slot()
    def stop_current_data_stream(self):
        print("MainWindow: Stopping current data stream")
        if self.active_stream_node_id:
            # Clear plot buffers for all traces
            for plot_node in self.plot_nodes.values():
                plot_node.clear_buffers()
        if self.active_data_source:
            asyncio.ensure_future(self.active_data_source.stop(), loop=self.loop)
            self.plot_status_bar.update_status(f"Stopped: {self.active_data_source.name}")
        else:
            self.plot_status_bar.update_status("No stream active to stop.")

    @Slot(str, str)
    def create_plot_node(self, color: str, node_id: str):
        """Create a new plot node with the specified color and ID."""
        print(f"Creating plot node: {node_id} with color {color}")
        
        # Check if node_id already exists
        if node_id in self.plot_nodes:
            print(f"Warning: Plot node {node_id} already exists, skipping creation")
            return
        
        # Determine trace_index (next available index)
        trace_index = len(self.plot_nodes)
        
        # Create the new plot node
        plot_node = PlotNode(
            node_id,
            self.plotwidget,
            trace_index=trace_index,
            trace_color=color,
            loop=self.loop
        )
        
        # Add to our collections
        self.plot_nodes[node_id] = plot_node
        self.pipeline_graph.add_node(plot_node)
        
        # If there's an active stream, subscribe the new plot node to it
        if self.active_stream_node_id:
            stream_node = self.pipeline_graph.nodes.get(self.active_stream_node_id)
            if stream_node:
                plot_node.subscribe_to_input(stream_node)
        
        print(f"Successfully created plot node: {node_id}")

    @Slot(str)
    def destroy_plot_node(self, node_id: str):
        """Destroy the specified plot node."""
        print(f"Destroying plot node: {node_id}")
        
        plot_node = self.plot_nodes.get(node_id)
        if not plot_node:
            print(f"Warning: Plot node {node_id} not found")
            return
        
        # Unsubscribe from any inputs
        if self.active_stream_node_id:
            try:
                plot_node.unsubscribe_from_input(self.active_stream_node_id)
            except Exception as e:
                print(f"Error unsubscribing plot node {node_id}: {e}")
        
        # Clear the plot node's buffers and remove its trace
        plot_node.clear_buffers()
        
        # Remove from collections
        del self.plot_nodes[node_id]
        self.pipeline_graph.remove_node(node_id)
        
        print(f"Successfully destroyed plot node: {node_id}")

    @Slot()
    def clear_all_plot_nodes(self):
        """Clear all plot nodes."""
        print("Clearing all plot nodes")
        
        # Get a copy of the keys since we'll be modifying the dict
        node_ids = list(self.plot_nodes.keys())
        
        for node_id in node_ids:
            self.destroy_plot_node(node_id)
        
        # Clear the plot widget
        self.plotwidget.clear_all_traces()
        
        print("Successfully cleared all plot nodes")

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
        dlg = NodeDialog(self.pipeline_graph, mode="add", parent=self)
        if dlg.exec_() == QDialog.Accepted: # type: ignore
            data = dlg.get_results()
            node_id = data["id"]
            op_file = data["operator_file"]
            params = data["params"]

            params["operator_file"] = op_file

            # --- New: Load Node subclass from file if needed ---
            import os
            if os.path.isabs(op_file) or op_file.endswith(".py"):
                try:
                    NodeClass = load_node_subclass_from_file(op_file if os.path.isabs(op_file) else os.path.join("operators", op_file))
                except Exception as e:
                    self.plot_status_bar.showMessage(f"Error loading Node subclass: {e}")
                    return
            else:
                NodeClass = Node  # fallback
                print(f"Warning: Node type '{op_file}' was fonud to be invalid, using base Node class.")

            # Create the new Node and add it to the graph:
            new_node = NodeClass(node_id, node_type=op_file, params=params, loop=self.loop)
            self.pipeline_graph.add_node(new_node)
            self.plot_status_bar.showMessage(f"Added node '{node_id}'.")

            # Make the node subscribe to the user-configured inputs
            inputs = list(data['inputs'])
            for input_node in inputs:
                new_node.subscribe_to_input(self.pipeline_graph.nodes[input_node])

            # --- Update data_sources and RunStopPanel to include all non-discharge nodes as streams ---
            # Heuristic: exclude PlotNode and any node with node_type == 'discharge'
            is_discharge = isinstance(new_node, PlotNode) or getattr(new_node, 'node_type', None) == 'discharge'
            if not is_discharge:
                self.data_sources[node_id] = getattr(new_node, 'data_source', new_node)
                self.run_stop_panel.update_available_streams(list(self.data_sources.keys()))

    @Slot()
    def open_edit_node_dialog(self):
        if not self.pipeline_graph.nodes:
            QMessageBox.information(self, "Edit Node", "No nodes to edit. Please add one first.")
            return

        dlg = NodeDialog(self.pipeline_graph, mode="edit", parent=self)
        if dlg.exec_() == QDialog.Accepted: # type: ignore
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

            self.plot_status_bar.showMessage(f"Updated node '{node_id}'.")
