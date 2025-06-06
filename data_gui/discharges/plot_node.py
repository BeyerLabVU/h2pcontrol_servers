import asyncio
import numpy as np
from typing import Any, Optional, Dict
from PySide6.QtCore import QObject, Signal, QTimer
import pyqtgraph as pg

from data_node import Node
from discharges.styled_plot import StyledPlotWidget


class PlotNode(Node, QObject):
    """
    A Node subclass that acts as a data discharge by plotting incoming data streams.
    It represents a single trace/plot item within a StyledPlotWidget.
    """
    
    # Qt signals for thread-safe GUI updates
    data_received = Signal(object)  # Emitted when new data is received
    
    def __init__(self, node_id: str, styled_plot_widget: StyledPlotWidget, 
                 trace_index: int = 0, trace_color: str = "#0077bb",
                 params: Optional[dict] = None, loop: Optional[asyncio.AbstractEventLoop] = None):
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
        self.update_timer.start(10)  # Start timer
        
        # Connect signal for thread-safe data handling
        self.data_received.connect(self._handle_data_on_gui_thread)
        
        # Track if we have data to display
        self._has_new_data = False
        self._temp_time_data = None
        self._temp_signal_data = None
        
        # Track visibility state
        self.visible = True  # Traces are visible by default
        
        print(f"PlotNode {self.id} initialized with buffer size {self.buffer_size}")
        
    def process_input(self, data: Any, input_node_id: str):
        """
        Process incoming data from upstream nodes.
        Expected data format: {"time_array": np.array, "signal_array": np.array, "name": str}
        """
        # print(f"PlotNode {self.id} received data from {input_node_id}")
        
        # Emit signal to handle data on GUI thread
        self.data_received.emit(data)
        
        # Don't forward data (this is a discharge node)
        # self.subject.on_next(data)  # Commented out - discharge nodes don't forward data
        
    def _handle_data_on_gui_thread(self, data: Dict[str, Any]):
        """Handle incoming data on the GUI thread (called via Qt signal)"""
        try:
            if isinstance(data, dict) and 'time_array' in data and 'signal_array' in data:
                time_array = data['time_array']
                signal_array = data['signal_array']
                
                if isinstance(time_array, np.ndarray) and isinstance(signal_array, np.ndarray):
                    # Store data for next update cycle
                    self._temp_time_data = time_array
                    self._temp_signal_data = signal_array
                    self._has_new_data = True
                else:
                    print(f"PlotNode {self.id}: Invalid data types - expected numpy arrays")
            else:
                print(f"PlotNode {self.id}: Invalid data format - expected dict with time_array and signal_array")
                
        except Exception as e:
            print(f"PlotNode {self.id}: Error handling data: {e}")
    
    def _update_plot_display(self):
        """Update the plot display (called by QTimer on GUI thread)"""
        if not self._has_new_data or self._temp_time_data is None or self._temp_signal_data is None:
            return
            
        try:
            # Add new data to buffers
            self.time_buffer = np.append(self.time_buffer, self._temp_time_data)
            self.signal_buffer = np.append(self.signal_buffer, self._temp_signal_data)
            
            # Trim buffers to max size
            if len(self.time_buffer) > self.max_points:
                excess = len(self.time_buffer) - self.max_points
                self.time_buffer = self.time_buffer[excess:]
                self.signal_buffer = self.signal_buffer[excess:]            # Create plot item if not exists and add to the plot widget
            if self.plot_item is None and len(self.time_buffer) > 0:
                self.plot_item = self.plot_widget.plot_widget.plot(
                    self.time_buffer, self.signal_buffer, 
                    pen=self.pen, name=f"Trace {self.trace_index}"
                )
                # Set initial visibility based on current state
                self.plot_item.setVisible(self.visible)
            elif self.plot_item is not None:
                # Update existing plot item
                self.plot_item.setData(self.time_buffer, self.signal_buffer)
            
            # Reset flags
            self._has_new_data = False
            self._temp_time_data = None
            self._temp_signal_data = None
            
        except Exception as e:
            print(f"PlotNode {self.id}: Error updating plot: {e}")
    
    def clear_buffers(self):
        """Clear the data buffers and plot"""
        self.time_buffer = np.array([])
        self.signal_buffer = np.array([])
          # Clear this specific plot item
        if self.plot_item is not None:
            self.plot_widget.plot_widget.removeItem(self.plot_item)
            self.plot_item = None
            
        print(f"PlotNode {self.id} buffers cleared")
    
    def set_buffer_size(self, size: int):
        """Set the maximum number of points to display"""
        self.max_points = size
        self.buffer_size = size
        print(f"PlotNode {self.id} buffer size set to {size}")
    
    def set_visible(self, visible: bool):
        """Set the visibility of this plot trace"""
        self.visible = visible
        if self.plot_item is not None:
            self.plot_item.setVisible(visible)
        print(f"PlotNode {self.id} visibility set to {visible}")
    
    def subscribe_to_input(self, input_node: 'Node') -> bool:
        """Override to allow subscribing to inputs (unlike base catchment logic)"""
        if input_node.id in self.input_subscriptions:
            print(f"PlotNode {self.id} already subscribed to {input_node.id}")
            return False

        print(f"PlotNode {self.id} subscribing to {input_node.id}")
        subscription = input_node.subject.pipe().subscribe(  # type: ignore
            on_next=lambda data: self.handle_input_data(data, input_node.id),
            on_error=self.subject.on_error,  # Propagate error
            on_completed=lambda: self.handle_input_completion(input_node.id),
        )
        self.input_subscriptions[input_node.id] = subscription
        return True
    
    def dispose(self):
        """Clean up resources"""
        print(f"Disposing PlotNode {self.id}")
        
        # Stop the update timer
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        
        # Clear plot
        self.clear_buffers()
        
        # Call parent dispose
        super().dispose()