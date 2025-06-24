from copy import deepcopy
import asyncio
import logging
from collections import deque
from typing import Any, Optional
from data_node import Node

# Set up logger for this module
logger = logging.getLogger(__name__)

class StrictMovingAverage(Node):
    """
    A Node that implements a strict moving average filter for signal data.
    
    This operator maintains a window of previous signal arrays and computes
    the average of all arrays in the window plus the current input.
    It handles shape mismatches by resetting the window when input dimensions change.
    
    Parameters:
        window (int): The size of the averaging window. Default is 10.
    """
    def __init__(self, node_id: str, node_type: str, params: dict, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(node_id = node_id, node_type=node_type, params=params, loop = loop)
        logger.info(f"StrictMovingAverage operator initialized with window size {params.get('window', 10)}")

        # Get the window size parameter, default is 10
        window_size = params.get('window', 10)
        self.averaging_window = deque(maxlen=window_size)
        
        # Track the shape of received data to detect changes
        self.received_shape = None
    
    def process_input(self, data: Any, input_node_id: str):
        """
        Process incoming data by applying a moving average filter.
        
        This method:
        1. Makes a deep copy of the input data to avoid modifying the original
        2. For the first data point, just passes it through and starts the window
        3. For subsequent data points, checks if the shape matches the window
        4. If shapes match, computes the average of all data in the window plus current input
        5. If shapes don't match, resets the window and passes the current data through
        
        Args:
            data (Any): The input data dictionary containing a 'signal_array' key
            input_node_id (str): The ID of the node that sent this data
            
        Raises:
            ValueError: If the input data doesn't contain a 'signal_array' key
        """
        if 'signal_array' in data:
            data = deepcopy(data)  # Make a copy to avoid modifying the original data
            received_data = data['signal_array']
            if len(self.averaging_window) == 0:
                self.subject.on_next(data)  # Pass through

                # Append most recent data to the averaging window
                self.averaging_window.append(deepcopy(received_data))
            else:
                self.received_shape = received_data.shape

                if self.averaging_window[0].shape != received_data.shape:
                    # Reset the averaging window if the shape has changed
                    logger.warning(f"Node {self.id}: Shape mismatch - resetting averaging window from {self.received_shape} to {received_data.shape}")
                    self.averaging_window.clear()

                    # Append most recent data to the averaging window
                    self.averaging_window.append(deepcopy(received_data))

                    self.subject.on_next(data)
                else:
                    # Append most recent data to the averaging window
                    self.averaging_window.append(deepcopy(received_data))
                    
                    # Calculate the average: sum all data in the window and divide by count
                    sum_data = received_data.copy()  # Start with the current data
                    for data_array in self.averaging_window:
                        sum_data += data_array
                    
                    # N is the number of arrays we're averaging (current + window)
                    N = len(self.averaging_window) + 1
                    data['signal_array'] = sum_data / N
                    self.subject.on_next(data)
        else:
            logger.error(f"Node {self.id}: Input data missing required 'signal_array' key")
            raise ValueError(f"Input data must contain 'signal_array' key. Received keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
