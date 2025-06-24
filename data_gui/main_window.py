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
    QFileDialog,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Slot

from discharges.styled_plot import StyledPlotWidget
from bottom_status_bar import BottomStatusBar
from control_panel import ControlPanel
from settings_panels.plot_manager_panel import PlotManagerPanel
from settings_panels.node_manager_panel import NodeManagerPanel
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

        # ---- Data Sources ----
        self.data_sources = {}
        
        # ---- Control panel (scroll area on the right) ----
        self.control_panel = ControlPanel()
        
        # Add plot manager panel
        self.plot_manager_panel = PlotManagerPanel(self.control_panel)
        self.control_panel.add_panel(self.plot_manager_panel)
        
        # Add node manager panel
        self.node_manager_panel = NodeManagerPanel(self.pipeline_graph, self.control_panel)
        self.control_panel.add_panel(self.node_manager_panel)
        # Connect node manager signals
        self.node_manager_panel.edit_node_signal.connect(self.edit_node_dialog)
          
        # Connect plot manager signals
        self.plot_manager_panel.create_plot_node_signal.connect(self.create_plot_node)
        self.plot_manager_panel.destroy_plot_node_signal.connect(self.destroy_plot_node)
        self.plot_manager_panel.clear_all_plot_nodes_signal.connect(self.clear_all_plot_nodes)
        self.plot_manager_panel.edit_plot_node_signal.connect(self.edit_plot_node_dialog)
        self.plot_manager_panel.rename_plot_node_signal.connect(self.rename_plot_node)
        self.plot_manager_panel.trace_order_changed_signal.connect(self.update_trace_z_order)
        self.plot_manager_panel.trace_visibility_changed_signal.connect(self.update_trace_visibility)
        self.plot_manager_panel.trace_color_changed_signal.connect(self.update_trace_color)
        
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
        
        # Connect save and load nodes actions
        self.menu.save_nodes_action.triggered.connect(self.save_node_network)
        self.menu.load_nodes_action.triggered.connect(self.load_node_network)
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

        # Initialize with the first stream selected, if any
        # if available_stream_names:
        #     self.on_stream_selected(available_stream_names[0])
        # else:
        #     self.plotwidget.clear_all_traces() # Show screensaver if no streams

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
            # self.run_stop_panel.update_available_streams(list(self.data_sources.keys()))
            self.test_catchment_initialized = True
            self.add_test_catchment_action.setEnabled(False)  # Disable after adding
            
            # Update the node manager panel to reflect the new test catchment node
            self.node_manager_panel.sync_with_pipeline_graph()
    
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
                self.pipeline_graph.add_edge(stream_node.id, plot_node.id)
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

        # --- Hide screen saver trace if more than one plot node exists ---
        if len(self.plot_nodes) > 0:
            if hasattr(self.plotwidget, '_screen_saver_item') and self.plotwidget._screen_saver_item:
                self.plotwidget._screen_saver_item.setVisible(False)

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

        # --- Show screen saver trace if no plot nodes remain ---
        if len(self.plot_nodes) == 0:
            self.plotwidget.screen_saver_trace()
            
        # Update the node manager panel to reflect the removed node
        self.node_manager_panel.sync_with_pipeline_graph()

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
        
        # Update the node manager panel to reflect the cleared nodes
        self.node_manager_panel.sync_with_pipeline_graph()

    def save_node_network(self):
        """Save the current node network to a JSON file."""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Node Network",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            if not filename.endswith('.json'):
                filename += '.json'
            try:
                from data_node import serialize_pipeline
                serialize_pipeline(self.pipeline_graph, filename)
                self.plot_status_bar.showMessage(f"Node network saved to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save node network: {str(e)}")
                
    def load_node_network(self):
        """Load a node network from a JSON file."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load Node Network",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            try:
                # Clear existing nodes first
                self.clear_all_plot_nodes()
                
                # Clear any remaining non-plot nodes
                non_plot_node_ids = [node_id for node_id in self.pipeline_graph.nodes.keys()]
                for node_id in non_plot_node_ids:
                    self.pipeline_graph.remove_node(node_id)
                
                # Load the new pipeline with the plot widget
                from data_node import deserialize_pipeline
                new_pipeline = deserialize_pipeline(filename, loop=self.loop, plotwidget=self.plotwidget)
                
                # First pass: Add all nodes to the pipeline
                for node_id, node in new_pipeline.nodes.items():
                    self.pipeline_graph.add_node(node)
                    
                    # If it's a plot node, add it to plot_nodes dict
                    if isinstance(node, PlotNode):
                        self.plot_nodes[node_id] = node
                        # Create a new plot item if needed
                        if not hasattr(node, 'plot_item') or node.plot_item is None:
                            # Check if the create_plot_item method exists
                            if hasattr(node, 'create_plot_item'):
                                node.create_plot_item()
                            else:
                                # Manually create a plot item
                                import pyqtgraph as pg
                                node.pen = pg.mkPen(color=node.trace_color, width=2)
                                node.plot_item = self.plotwidget.plot_widget.plot(
                                    [], [], 
                                    pen=node.pen, name=f"Trace {node.trace_index}",
                                    antialias=True
                                )
                                node.plot_item.setVisible(node.visible)
                        # Ensure the plot widget updates with any restored data
                        if hasattr(self.plotwidget, '_data_buffers') and node_id in self.plotwidget._data_buffers:
                            buffers = self.plotwidget._data_buffers[node_id]
                            if 'time_array' in buffers and 'signal_array' in buffers:
                                self.plotwidget.update_trace_data(node_id, buffers['time_array'], buffers['signal_array'])
                                print(f"Restored data buffers for plot node: {node_id}")
                    # If it's a catchment node, add it to data_sources and start it
                    elif isinstance(node, CatchmentNode) or "catchment" in getattr(node, 'node_type', '').lower():
                        self.data_sources[node_id] = getattr(node, 'data_source', node)
                        # Start the catchment data source
                        data_source = getattr(node, 'data_source', None)
                        if data_source:
                            self.loop.create_task(data_source.start())
                            print(f"Started catchment node: {node_id}")
                    # If it's any other non-discharge node, add it to data_sources
                    elif not getattr(node, 'node_type', None) == 'discharge':
                        self.data_sources[node_id] = getattr(node, 'data_source', node)
                
                # Second pass: Reconnect all nodes based on their inputs
                for node_id, node in new_pipeline.nodes.items():
                    # Reconnect inputs
                    if hasattr(node, 'inputs') and node.inputs:
                        for input_id in node.inputs:
                            if input_id in self.pipeline_graph.nodes:
                                self.pipeline_graph.add_edge(input_id, node_id)
                                print(f"Reconnected {node_id} to input {input_id}")
                
                # Update the node manager panel
                self.node_manager_panel.sync_with_pipeline_graph()
                
                # Update the plot manager panel
                self.plot_manager_panel.sync_with_plot_nodes(self.plot_nodes)
                
                # If there are any plot nodes, make sure the screen saver is hidden
                if self.plot_nodes:
                    if hasattr(self.plotwidget, '_screen_saver_item') and self.plotwidget._screen_saver_item:
                        self.plotwidget._screen_saver_item.setVisible(False)
                else:
                    # Show screen saver if no plot nodes
                    self.plotwidget.screen_saver_trace()
                
                self.plot_status_bar.showMessage(f"Node network loaded from {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load node network: {str(e)}")
    
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
                print(f"Warning: Node type '{op_file}' was found to be invalid, using base Node class.")

            # Create the new Node and add it to the graph:
            new_node = NodeClass(node_id, node_type=op_file, params=params, loop=self.loop)
            self.pipeline_graph.add_node(new_node)
            self.plot_status_bar.showMessage(f"Added node '{node_id}'.")

            # Make the node subscribe to the user-configured inputs
            inputs = list(data['inputs'])
            for input_node in inputs:
                if input_node in self.pipeline_graph.nodes:
                    self.pipeline_graph.add_edge(input_node, new_node.id)
                else:
                    print(f"Warning: Input node '{input_node}' not found in pipeline for connection to '{new_node.id}'")

            # --- Update data_sources and RunStopPanel to include all non-discharge nodes as streams ---
            # Heuristic: exclude PlotNode and any node with node_type == 'discharge'
            is_discharge = isinstance(new_node, PlotNode) or getattr(new_node, 'node_type', None) == 'discharge'
            if not is_discharge:
                self.data_sources[node_id] = getattr(new_node, 'data_source', new_node)
                # self.run_stop_panel.update_available_streams(list(self.data_sources.keys()))
            
            # Update the node manager panel to reflect the new node
            self.node_manager_panel.sync_with_pipeline_graph()

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

            # Update the existing node in-place:
            node = self.pipeline_graph.nodes[node_id]
            node.node_type = op_file
            node.params = params

            self.plot_status_bar.showMessage(f"Updated node '{node_id}'.")
            
            # Update the node manager panel to reflect the changes
            self.node_manager_panel.sync_with_pipeline_graph()

    @Slot(str)
    def edit_plot_node_dialog(self, node_id: str):
        """Open the edit node dialog and select the node with the given node_id."""
        dialog = NodeDialog(self.pipeline_graph, mode="edit", parent=self)
        # Find the index of the node_id in the dialog's node_ids list
        if hasattr(dialog, "node_ids") and node_id in dialog.node_ids:
            idx = dialog.node_ids.index(node_id)
            dialog.node_index_spin.setValue(idx)
        dialog.exec()
        
    @Slot(str)
    def edit_node_dialog(self, node_id: str):
        """Open the edit node dialog and select the node with the given node_id."""
        dialog = NodeDialog(self.pipeline_graph, mode="edit", parent=self)
        # Find the index of the node_id in the dialog's node_ids list
        if hasattr(dialog, "node_ids") and node_id in dialog.node_ids:
            idx = dialog.node_ids.index(node_id)
            dialog.node_index_spin.setValue(idx)
        if dialog.exec() == QDialog.Accepted:
            # Update the node manager panel to reflect any changes
            self.node_manager_panel.sync_with_pipeline_graph()

    @Slot(str, str)
    def rename_plot_node(self, old_node_id: str, new_node_id: str):
        """Rename a plot node and update the pipeline graph and plot_nodes dict."""
        # Update plot_nodes dict
        if old_node_id in self.plot_nodes:
            self.plot_nodes[new_node_id] = self.plot_nodes.pop(old_node_id)
            self.plot_nodes[new_node_id].id = new_node_id
        # Update pipeline_graph.nodes dict
        if old_node_id in self.pipeline_graph.nodes:
            self.pipeline_graph.nodes[new_node_id] = self.pipeline_graph.nodes.pop(old_node_id)
            self.pipeline_graph.nodes[new_node_id].id = new_node_id
        # If the renamed node is the active stream node, update the reference
        if self.active_stream_node_id == old_node_id:
            self.active_stream_node_id = new_node_id
            
        # Update the node manager panel to reflect the renamed node
        self.node_manager_panel.sync_with_pipeline_graph()

    @Slot(list)
    def update_trace_z_order(self, node_id_order):
        """Update the z-order of traces in the plot widget so that higher traces are drawn above."""
        # node_id_order: list of node_ids, topmost first
        # Reorder plot items in StyledPlotWidget accordingly
        # We'll remove and re-add plot items in the desired order
        plot_items = []
        for node_id in node_id_order:
            plot_node = self.plot_nodes.get(node_id)
            if plot_node and plot_node.plot_item is not None:
                plot_items.append(plot_node.plot_item)
        # Remove all plot items
        for plot_node in self.plot_nodes.values():
            if plot_node.plot_item is not None:
                try:
                    self.plotwidget.plot_widget.removeItem(plot_node.plot_item)
                except Exception:
                    pass
        # Add them back in order, bottom to top
        for plot_item in plot_items[::-1]:
            self.plotwidget.plot_widget.addItem(plot_item)

    @Slot(str, bool)
    def update_trace_visibility(self, node_id: str, visible: bool):
        """Update the visibility of a trace in the plot widget."""
        plot_node = self.plot_nodes.get(node_id)
        if plot_node:
            plot_node.set_visible(visible)
            print(f"Updated visibility for trace {node_id}: {visible}")
        else:
            print(f"Warning: Could not find plot node {node_id} to update visibility")
            
    @Slot(str, str)
    def update_trace_color(self, node_id: str, color: str):
        """Update the color of a trace in the plot widget."""
        plot_node = self.plot_nodes.get(node_id)
        if plot_node:
            plot_node.trace_color = color
            if hasattr(plot_node, 'plot_item') and plot_node.plot_item is not None:
                plot_node.plot_item.setPen(color)
            print(f"Updated color for trace {node_id}: {color}")
        else:
            print(f"Warning: Could not find plot node {node_id} to update color")
