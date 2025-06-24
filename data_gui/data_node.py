from typing import List, Dict, Any, Optional
from graphlib import TopologicalSorter
import json
import asyncio

from reactivex import Subject
from reactivex import operators as ops
from reactivex.scheduler.eventloop import AsyncIOScheduler


node_types = ("discharge", "operator", "catchment")

def serialize_pipeline(pipeline: 'PipelineGraph', filename: str):
    nodes_list = []
    for node in pipeline.nodes.values():
        # Filter out operator_file from params to store only configuration data
        filtered_params = {k: v for k, v in node.params.items() if k != "operator_file"}
        node_data = {
            "id": node.id,
            "type": node.node_type,
            "params": filtered_params,
            "inputs": list(node.inputs),
            "outputs": list(node.outputs),
        }
        
        # Add specialized attributes for different node types
        if node.__class__.__name__ == "PlotNode":
            node_data["class"] = "PlotNode"
            node_data["trace_color"] = getattr(node, 'trace_color', "#0077bb")
            node_data["trace_index"] = getattr(node, 'trace_index', 0)
            node_data["visible"] = getattr(node, 'visible', True)
            # Capture data buffers if available
            if hasattr(node, 'plot_widget') and hasattr(node.plot_widget, '_data_buffers'):
                buffers = node.plot_widget._data_buffers.get(node.id, {})
                if 'time_array' in buffers and 'signal_array' in buffers:
                    # Convert numpy arrays to lists for JSON serialization
                    node_data["time_buffer"] = buffers['time_array'].tolist() if buffers['time_array'] is not None else []
                    node_data["signal_buffer"] = buffers['signal_array'].tolist() if buffers['signal_array'] is not None else []
                else:
                    node_data["time_buffer"] = []
                    node_data["signal_buffer"] = []
            else:
                node_data["time_buffer"] = []
                node_data["signal_buffer"] = []
        elif node.__class__.__name__ == "CatchmentNode":
            node_data["class"] = "CatchmentNode"
        else:
            node_data["class"] = "Node"
            
        nodes_list.append(node_data)
    data = {"nodes": nodes_list}
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def create_node_from_data(entry: dict, loop=None, plotwidget=None):
    """Create the appropriate node type based on the saved data."""
    node_class = entry.get("class", "Node")
    node_id = entry["id"]
    node_type = entry["type"]
    params = entry["params"]
    
    if node_class == "PlotNode" and plotwidget is not None:
        # Import here to avoid circular imports
        from discharges.plot_node import PlotNode
        trace_color = entry.get("trace_color", "#0077bb")
        trace_index = entry.get("trace_index", 0)
        node = PlotNode(
            node_id=node_id,
            styled_plot_widget=plotwidget,
            trace_index=trace_index,
            trace_color=trace_color,
            params=params,
            loop=loop
        )
        # Set additional attributes
        node.visible = entry.get("visible", True)
        # Restore data buffers if available
        if "time_buffer" in entry and "signal_buffer" in entry:
            import numpy as np
            time_buffer = np.array(entry.get("time_buffer", []))
            signal_buffer = np.array(entry.get("signal_buffer", []))
            if time_buffer.size > 0 and signal_buffer.size > 0:
                if not hasattr(plotwidget, '_data_buffers'):
                    plotwidget._data_buffers = {}
                plotwidget._data_buffers[node_id] = {
                    "time_array": time_buffer,
                    "signal_array": signal_buffer
                }
                # Ensure plot item is created and updated with restored data
                if hasattr(node, 'create_plot_item'):
                    node.create_plot_item()
                if hasattr(plotwidget, 'update_trace_data'):
                    plotwidget.update_trace_data(node_id, time_buffer, signal_buffer)
        return node
    elif node_class == "CatchmentNode":
        # Import here to avoid circular imports
        from catchments.test_source_node import CatchmentNode
        from catchments.data_source import DataSource
        node = CatchmentNode(
            node_id=node_id,
            data_source=DataSource(),
            loop=loop
        )
        return node
    else:
        # Default to base Node
        return Node(node_id, node_type, params, loop=loop)

def deserialize_pipeline(filename: str, loop: Optional[asyncio.AbstractEventLoop] = None, plotwidget=None) -> 'PipelineGraph':
    with open(filename, "r") as f:
        data = json.load(f)

    graph = PipelineGraph(loop=loop)
    # 1) Recreate nodes
    for entry in data["nodes"]:
        node = create_node_from_data(entry, loop=graph.loop, plotwidget=plotwidget)
        graph.add_node(node)
    # 2) Recreate edges
    for entry in data["nodes"]:
        from_id = entry["id"]
        for to_id in entry["outputs"]:
            graph.add_edge(from_id, to_id)
    return graph

class Node:
    def __init__(self, node_id: str, node_type: str, params: dict, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.id = node_id
        self.node_type = node_type
        self.params = params
        self.inputs: List[str] = []  # List of input node IDs
        self.outputs: List[str] = [] # List of output node IDs

        self.loop = loop or asyncio.get_event_loop()
        self.scheduler = AsyncIOScheduler(loop=self.loop)
        
        self.subject = Subject() # This node's output stream
        self.input_subscriptions = dict()

    def handle_input_data(self, data: Any, input_node_id: str):
        # Ensure processing happens on the node's event loop
        if asyncio.get_running_loop() is self.loop:
            self.process_input(data, input_node_id)
        else:
            self.loop.call_soon_threadsafe(self.process_input, data, input_node_id)

    def process_input(self, data: Any, input_node_id: str):
        """
        Process incoming data from a specific input and potentially emit to own subject.
        Subclasses should override this for custom processing logic.
        Default behavior: pass through data.
        """
        print(f"Node {self.id} (type: {self.node_type}) processing data from {input_node_id}")
        self.subject.on_next(data)

    def subscribe_to_input(self, input_node: 'Node') -> bool:
        if self.node_type == "catchment":
            print("Node is not intended to receive data")
            return False
        if input_node.id in self.input_subscriptions:
            print(f"Node {self.id} already subscribed to {input_node.id}")
            return False

        print(f"Node {self.id} subscribing to {input_node.id}")
        subscription = input_node.subject.pipe(
            ops.observe_on(self.scheduler) # Ensure on_next, on_error, on_completed are called on this node's scheduler
        ).subscribe(
            on_next=lambda data: self.handle_input_data(data, input_node.id),
            on_error=self.subject.on_error, # Propagate error to own subject
            on_completed=lambda: self.handle_input_completion(input_node.id),
            scheduler=self.scheduler
        )
        self.input_subscriptions[input_node.id] = subscription
        print(subscription)
        return True

    def unsubscribe_from_input(self, input_node_id: str):
        if input_node_id in self.input_subscriptions:
            print(f"Node {self.id} unsubscribing from {input_node_id}")
            self.input_subscriptions[input_node_id].dispose()
            del self.input_subscriptions[input_node_id]

    def handle_input_completion(self, input_node_id: str):
        print(f"Node {self.id} received completion from input {input_node_id}")
        self.unsubscribe_from_input(input_node_id)

    def dispose(self):
        print(f"Disposing Node {self.id} (type: {self.node_type})")
        for input_id in list(self.input_subscriptions.keys()):
            self.unsubscribe_from_input(input_id)
        
        # Complete and dispose own subject
        try:
            self.subject.on_completed()
        except Exception as e:
            print(f"Error during on_completed for node {self.id}: {e}")
        try:
            self.subject.dispose()
        except Exception as e:
            pass


class PipelineGraph:
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.nodes: Dict[str, Node] = {}
        self.loop = loop or asyncio.get_event_loop()

    def add_node(self, node: Node):
        self.nodes[node.id] = node

    def remove_node(self, node_id: str):
        node_to_remove = self.nodes.get(node_id)
        if not node_to_remove:
            return

        print(f"Removing node {node_id} from graph.")

        upstream_ids = list(node_to_remove.inputs)
        downstream_ids = list(node_to_remove.outputs)

        node_to_remove.dispose()

        for up_id in upstream_ids:
            if up_id in self.nodes:
                upstream_node = self.nodes[up_id]
                if node_id in upstream_node.outputs:
                    upstream_node.outputs.remove(node_id)
        
        for down_id in downstream_ids:
            if down_id in self.nodes:
                downstream_node = self.nodes[down_id]
                if node_id in downstream_node.inputs:
                    downstream_node.inputs.remove(node_id)

        if node_id in self.nodes:
            del self.nodes[node_id]

    def add_edge(self, from_id: str, to_id: str):
        if from_id not in self.nodes or to_id not in self.nodes:
            raise KeyError(f"Node {from_id} or {to_id} does not exist")
        
        from_node = self.nodes[from_id]
        to_node = self.nodes[to_id]

        # Update structural links
        if to_id not in from_node.outputs:
            from_node.outputs.append(to_id)
        if from_id not in to_node.inputs:
            to_node.inputs.append(from_id)

        to_node.subscribe_to_input(from_node)

    def remove_edge(self, from_id: str, to_id: str):
        if from_id not in self.nodes or to_id not in self.nodes:
            print(f"Warning: Cannot remove edge, node {from_id} or {to_id} does not exist.")
            return

        from_node = self.nodes[from_id]
        to_node = self.nodes[to_id]

        to_node.unsubscribe_from_input(from_id)
        
        # Update structural links
        if to_id in from_node.outputs:
            from_node.outputs.remove(to_id)
        if from_id in to_node.inputs:
            to_node.inputs.remove(from_id)

    def topological_order(self) -> List[str]:
        dependency_map = {
            node_id: set(node.inputs)
            for node_id, node in self.nodes.items()
        }
        ts = TopologicalSorter(dependency_map)
        return list(ts.static_order())

    def would_create_cycle(self, from_id: str, to_id: str) -> bool:
        if from_id not in self.nodes or to_id not in self.nodes:
            return False
        
        # Simple case: self-loop
        if from_id == to_id:
            return True
        
        # Temporarily add the edge to test for cycles
        temp_dependency_map = {
            node_id: set(node.inputs)
            for node_id, node in self.nodes.items()
        }
        
        # Add the potential new edge
        temp_dependency_map[to_id].add(from_id)
        
        try:
            ts = TopologicalSorter(temp_dependency_map)
            list(ts.static_order())  # This will raise CycleError if there's a cycle
            return False
        except Exception:
            return True

    def get_reachable_nodes(self, from_id: str) -> set:
        if from_id not in self.nodes:
            return set()
        
        visited = set()
        stack = [from_id]
        
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            
            if current in self.nodes:
                for output_id in self.nodes[current].outputs:
                    if output_id not in visited:
                        stack.append(output_id)
        
        return visited
