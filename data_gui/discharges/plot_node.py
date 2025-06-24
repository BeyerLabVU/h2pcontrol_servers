import asyncio
import logging
import numpy as np
from typing import Any, Optional, Dict, Union
from PySide6.QtCore import QObject, Signal, QTimer
import pyqtgraph as pg

from data_node import Node
from discharges.styled_plot import StyledPlotWidget

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
        self.time_buffer = np.array([])
        self.signal_buffer = np.array([])
        self.max_points = self.buffer_size
        
        # Setup Qt timer for GUI updates (runs on main GUI thread)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_plot_display)
        self.update_timer.start(10)  # Start timer with 10ms interval
        
        # Connect signal for thread-safe data handling
        self.data_received.connect(self._handle_data_on_gui_thread)
        
        # Track if we have data to display
        self._has_new_data = False
        self._temp_time_data = None
        self._temp_signal_data = None
        
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
        It validates the incoming data format and stores it for the next update cycle.
        
        Args:
            data (Dict[str, Any]): The data received from an upstream node.
                Expected format: {"time_array": np.array, "signal_array": np.array, "name": str}
        """
        try:
            if isinstance(data, dict) and 'time_array' in data and 'signal_array' in data:
                time_array = data['time_array']
                signal_array = data['signal_array']
                
                if isinstance(time_array, np.ndarray) and isinstance(signal_array, np.ndarray):
                    # Store data for next update cycle
                    self._temp_time_data = time_array
                    self._temp_signal_data = signal_array
                    self._has_new_data = True
                    logger.debug(f"Node '{self.id}': Received valid data with shape {signal_array.shape}")
                else:
                    logger.warning(f"Node '{self.id}': Invalid data types - expected numpy arrays, got time_array: {type(time_array)}, signal_array: {type(signal_array)}")
            else:
                logger.warning(f"Node '{self.id}': Invalid data format - expected dict with time_array and signal_array keys, got keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                
        except Exception as e:
            logger.error(f"Node '{self.id}': Error handling data: {str(e)}", exc_info=True)
    
    def _update_plot_display(self):
        """
        Update the plot display with new data.
        
        This method is called periodically by a QTimer on the GUI thread.
        It appends new data to the buffers, trims them to the maximum size,
        and updates the plot item with the new data.
        
        If this is the first data received, it creates a new plot item.
        """
        # Skip if no new data is available
        if not self._has_new_data or self._temp_time_data is None or self._temp_signal_data is None:
            return
            
        try:
            # Add new data to buffers
            self.time_buffer = np.append(self.time_buffer, self._temp_time_data)
            self.signal_buffer = np.append(self.signal_buffer, self._temp_signal_data)
            
            # Trim buffers to max size if needed
            if len(self.time_buffer) > self.max_points:
                excess = len(self.time_buffer) - self.max_points
                self.time_buffer = self.time_buffer[excess:]
                self.signal_buffer = self.signal_buffer[excess:]
                logger.debug(f"Node '{self.id}': Trimmed buffers to {self.max_points} points (removed {excess} points)")
                
            # Create plot item if not exists and add to the plot widget
            if self.plot_item is None and len(self.time_buffer) > 0:
                self.plot_item = self.plot_widget.plot_widget.plot(
                    self.time_buffer, self.signal_buffer, 
                    pen=self.pen, name=f"Trace {self.trace_index}"
                )
                # Set initial visibility based on current state
                self.plot_item.setVisible(self.visible)
                logger.debug(f"Node '{self.id}': Created new plot item with {len(self.time_buffer)} points")
            elif self.plot_item is not None:
                # Update existing plot item
                self.plot_item.setData(self.time_buffer, self.signal_buffer)
                logger.debug(f"Node '{self.id}': Updated plot with {len(self.time_buffer)} points")
            
            # Reset flags
            self._has_new_data = False
            self._temp_time_data = None
            self._temp_signal_data = None
            
        except Exception as e:
            logger.error(f"Node '{self.id}': Error updating plot: {str(e)}", exc_info=True)
    
    def clear_buffers(self):
        """
        Clear the data buffers and remove the plot item.
        
        This method resets the node to its initial state with empty buffers
        and no plot item. It's useful when you want to start fresh or
        when the plot needs to be reset.
        """
        logger.info(f"Node '{self.id}': Clearing buffers and removing plot item")
        self.time_buffer = np.array([])
        self.signal_buffer = np.array([])
        
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
