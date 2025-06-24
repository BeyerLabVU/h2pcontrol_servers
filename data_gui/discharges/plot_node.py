import asyncio
import logging
import numpy as np
from typing import Any, Optional, Dict, Union, Tuple
from PySide6.QtCore import QObject, Signal, QTimer
import pyqtgraph as pg

from data_node import Node
from discharges.styled_plot import StyledPlotWidget

# Performance optimization settings
DOWNSAMPLE_THRESHOLD = 10000  # Number of points above which to apply downsampling
MAX_POINTS_PER_PIXEL = 2      # Maximum number of points to display per pixel

# Set up logger for this module
logger = logging.getLogger(__name__)


class PlotNode(Node, QObject):
    """
    A Node subclass that acts as a data discharge by plotting incoming data streams.
    
    This node represents a single trace/plot item within a StyledPlotWidget.
    It receives data from upstream nodes, buffers it, and displays it in a plot.
    The node handles thread-safe GUI updates using Qt signals and slots.
    
    Attributes:
        plot_widget (StyledPlotWidget): The widget where this trace will be displayed
        trace_index (int): Index of this trace in the plot
        trace_color (str): Color of this trace in hex format
        buffer_size (int): Maximum number of data points to keep in the buffer
        pen (pg.mkPen): PyQtGraph pen object for styling the trace
        plot_item: PyQtGraph plot item for this trace
        time_buffer (np.array): Buffer for time values
        signal_buffer (np.array): Buffer for signal values
        visible (bool): Whether this trace is currently visible
    """
    
    # Qt signals for thread-safe GUI updates
    data_received = Signal(object)  # Emitted when new data is received
    
    def __init__(self, node_id: str, styled_plot_widget: StyledPlotWidget, 
                 trace_index: int = 0, trace_color: str = "#0077bb",
                 params: Optional[dict] = None, loop: Optional[asyncio.AbstractEventLoop] = None):
        """
        Initialize a new PlotNode.
        
        Args:
            node_id (str): Unique identifier for this node
            styled_plot_widget (StyledPlotWidget): The widget where this trace will be displayed
            trace_index (int): Index of this trace in the plot
            trace_color (str): Color of this trace in hex format
            params (dict, optional): Configuration parameters for this node
                - buffer_size (int): Maximum number of data points to keep in the buffer
            loop (asyncio.AbstractEventLoop, optional): AsyncIO event loop to use
        """
        Node.__init__(self, node_id, node_type="discharge", params=params or {}, loop=loop)
        QObject.__init__(self)
        
        self.plot_widget = styled_plot_widget
        self.trace_index = trace_index
        self.trace_color = trace_color
        self.buffer_size = params.get('buffer_size', 10000) if params else 10000
        
        # Create the plot item for this specific trace
        self.pen = pg.mkPen(color=trace_color, width=2)
        self.plot_item = None  # Will be created when first data arrives
        
        # Data buffers for plotting
        self.max_points = self.buffer_size
        
        # Connect signal for thread-safe data handling
        self.data_received.connect(self._handle_data_on_gui_thread)
        
        # Track visibility state
        self.visible = True  # Traces are visible by default
        
        logger.info(f"PlotNode '{self.id}' initialized with buffer size {self.buffer_size}, trace index {trace_index}, color {trace_color}")
        
    def process_input(self, data: Any, input_node_id: str):
        """
        Process incoming data from upstream nodes.
        
        This method is called when data is received from an upstream node.
        It emits a signal to handle the data on the GUI thread to ensure
        thread-safe updates to the plot.
        
        Args:
            data (Any): The data received from the upstream node.
                Expected format: {"time_array": np.array, "signal_array": np.array, "name": str}
            input_node_id (str): The ID of the node that sent this data
        """
        logger.debug(f"Node '{self.id}': Received data from '{input_node_id}'")
        
        # Emit signal to handle data on GUI thread
        self.data_received.emit(data)
        
        # Don't forward data (this is a discharge node)
        # Discharge nodes are endpoints in the data flow graph
        
    def _handle_data_on_gui_thread(self, data: Dict[str, Any]):
        """
        Handle incoming data on the GUI thread.
        
        This method is called via Qt signal to ensure thread-safe handling of data.
        It validates the incoming data format and passes it to the plot widget.
        
        Args:
            data (Dict[str, Any]): The data received from an upstream node.
                Expected format: {"time_array": np.array, "signal_array": np.array, "name": str}
        """
        try:
            if isinstance(data, dict) and 'time_array' in data and 'signal_array' in data:
                time_array = data['time_array']
                signal_array = data['signal_array']
                
                if isinstance(time_array, np.ndarray) and isinstance(signal_array, np.ndarray):
                    self.plot_widget.update_trace_data(self.id, time_array, signal_array)
                    logger.debug(f"Node '{self.id}': Received valid data with shape {signal_array.shape}")
                else:
                    logger.warning(f"Node '{self.id}': Invalid data types - expected numpy arrays, got time_array: {type(time_array)}, signal_array: {type(signal_array)}")
            else:
                logger.warning(f"Node '{self.id}': Invalid data format - expected dict with time_array and signal_array keys, got keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                
        except Exception as e:
            logger.error(f"Node '{self.id}': Error handling data: {str(e)}", exc_info=True)
    
    def _downsample_data(self, x_data: np.ndarray, y_data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Apply intelligent downsampling to the data for improved plotting performance.
        
        This method uses PyQtGraph's built-in decimation algorithm to reduce the number
        of points displayed while preserving visual fidelity. It ensures that important
        features like peaks and valleys are preserved.
        
        Args:
            x_data (np.ndarray): The x-axis data (time values)
            y_data (np.ndarray): The y-axis data (signal values)
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: Downsampled x and y data arrays
        """
        if len(x_data) <= DOWNSAMPLE_THRESHOLD:
            # No downsampling needed for small datasets
            return x_data, y_data
            
        try:
            # Get the visible range of the plot
            view_box = self.plot_widget.plot_widget.getViewBox()
            if view_box is None:
                return x_data, y_data
                
            # Get the visible width in pixels
            view_range = view_box.viewRange()
            if not view_range:
                return x_data, y_data
                
            # Calculate the visible width in pixels
            view_width = view_box.width()
            if view_width <= 0:
                return x_data, y_data
                
            # Calculate the target number of points based on the view width
            # We want at most MAX_POINTS_PER_PIXEL points per pixel
            target_points = int(view_width * MAX_POINTS_PER_PIXEL)
            
            # Ensure we don't go below a minimum number of points
            target_points = max(target_points, 1000)
            
            if len(x_data) > target_points:
                # Use PyQtGraph's built-in decimation algorithm
                # This preserves visual features like peaks and valleys
                decimated_data = pg.downsample(x_data, y_data, target_points)
                logger.debug(f"Node '{self.id}': Downsampled from {len(x_data)} to {len(decimated_data[0])} points")
                return decimated_data
                
            return x_data, y_data
            
        except Exception as e:
            logger.warning(f"Node '{self.id}': Error during downsampling: {str(e)}")
            return x_data, y_data
    
    
    def clear_buffers(self):
        """
        Clear the data buffers and remove the plot item.
        
        This method resets the node to its initial state with empty buffers
        and no plot item. It's useful when you want to start fresh or
        when the plot needs to be reset.
        """
        logger.info(f"Node '{self.id}': Clearing buffers and removing plot item")
        if self.id in self.plot_widget._data_buffers:
            del self.plot_widget._data_buffers[self.id]
        
        # Clear this specific plot item
        if self.plot_item is not None:
            self.plot_widget.plot_widget.removeItem(self.plot_item)
            self.plot_item = None
    
    def set_buffer_size(self, size: int):
        """
        Set the maximum number of points to display.
        
        This method updates the buffer size limit. If the current buffers
        exceed this size, they will be trimmed on the next update cycle.
        
        Args:
            size (int): The new maximum buffer size
        """
        if size <= 0:
            logger.warning(f"Node '{self.id}': Invalid buffer size {size}, must be positive")
            return
            
        logger.info(f"Node '{self.id}': Setting buffer size to {size} points")
        self.max_points = size
        self.buffer_size = size
    
    def create_plot_item(self):
        """
        Create a plot item for this trace if it doesn't exist.
        
        This method is useful when loading a saved node network, as it ensures
        that the plot item is properly created and added to the plot widget.
        """
        if self.plot_item is None:
            logger.info(f"Node '{self.id}': Creating new plot item")
            self.pen = pg.mkPen(color=self.trace_color, width=2)
            self.plot_item = self.plot_widget.plot_widget.plot(
                [], [], 
                pen=self.pen, name=f"Trace {self.trace_index}",
                antialias=True
            )
            self.plot_item.setVisible(self.visible)
            
            # Enable downsampling in the plot item itself
            if hasattr(self.plot_item, 'setDownsampling'):
                self.plot_item.setDownsampling(auto=True, ds=2)  # ds=2 means downsample by factor of 2
                
            logger.debug(f"Node '{self.id}': Created new plot item")
            
    def set_visible(self, visible: bool):
        """
        Set the visibility of this plot trace.
        
        This method controls whether the trace is visible in the plot widget.
        It updates the internal visibility state and applies it to the plot item
        if one exists.
        
        Args:
            visible (bool): Whether the trace should be visible
        """
        logger.info(f"Node '{self.id}': Setting visibility to {visible}")
        self.visible = visible
        if self.plot_item is not None:
            self.plot_item.setVisible(visible)
    
    def subscribe_to_input(self, input_node: 'Node') -> bool:
        """
        Subscribe to an input node to receive its data.
        
        This method overrides the base Node.subscribe_to_input to implement
        the specific subscription logic for PlotNode. Unlike some other node types,
        PlotNode accepts input connections since it needs to receive data to plot.
        
        Args:
            input_node (Node): The node to subscribe to for input data
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        if input_node.id in self.input_subscriptions:
            logger.info(f"Node '{self.id}': Already subscribed to '{input_node.id}'")
            return False

        logger.info(f"Node '{self.id}': Subscribing to '{input_node.id}'")
        subscription = input_node.subject.pipe().subscribe(  # type: ignore
            on_next=lambda data: self.handle_input_data(data, input_node.id),
            on_error=self.subject.on_error,  # Propagate error
            on_completed=lambda: self.handle_input_completion(input_node.id),
        )
        self.input_subscriptions[input_node.id] = subscription
        return True
    
    def dispose(self):
        """
        Clean up resources used by this node.
        
        This method performs the following cleanup tasks:
        1. Stops the update timer to prevent further updates
        2. Clears the plot buffers and removes the plot item
        3. Calls the parent class's dispose method to clean up other resources
        
        This method should be called when the node is no longer needed to
        ensure proper cleanup of resources.
        """
        logger.info(f"Node '{self.id}': Disposing resources")
        
        # Stop the update timer
        if hasattr(self, 'update_timer'):
            logger.debug(f"Node '{self.id}': Stopping update timer")
            self.update_timer.stop()
        
        # Clear plot
        self.clear_buffers()
        
        # Call parent dispose
        super().dispose()
