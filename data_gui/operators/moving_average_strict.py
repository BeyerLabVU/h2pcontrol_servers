from copy import deepcopy
import asyncio
from collections import deque
from typing import Any, Optional
from data_node import Node

class StrictMovingAverage(Node):
    def __init__(self, node_id: str, node_type: str, params: dict, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(node_id = node_id, node_type=node_type, params=params, loop = loop)
        print("Test square operator initialized")

        self.averaging_window = deque(maxlen = params.get('window', 10) - 1) # Default window size is 10

        # The deque maxlen - 1 is because the received trace is included in the average
        self.received_shape = None
    
    def process_input(self, data: Any, input_node_id: str):
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
                    print(f"Shape mismatch: resetting averaging window from {self.received_shape} to {received_data.shape}")
                    self.averaging_window.clear()

                    # Append most recent data to the averaging window
                    self.averaging_window.append(deepcopy(received_data))

                    self.subject.on_next(data)
                else:
                    # Append most recent data to the averaging window
                    self.averaging_window.append(deepcopy(received_data))
                    N = 1
                    for data_array in self.averaging_window:
                        N += 1
                        received_data += data_array
                    data['signal_array'] = received_data / N
                    self.subject.on_next(data)
        else:
            print("erropr")
            raise ValueError("Input data must contain 'signal_array'.")