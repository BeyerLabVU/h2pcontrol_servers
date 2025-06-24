import asyncio
import logging
from typing import Any, Optional
from data_node import Node

# Set up logger for this module
logger = logging.getLogger(__name__)

class SquareOperator(Node):
    """
    A Node that squares the input signal data.
    
    This operator takes the input signal array and applies a square operation (x²)
    to each element, which can be useful for power calculations or emphasizing
    signal features.
    
    Parameters:
        No specific parameters required.
    """
    def __init__(self, node_id: str, node_type: str, params: dict, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(node_id = node_id, node_type=node_type, params=params, loop = loop)
        logger.info(f"SquareOperator initialized: {node_id}")
    
    def process_input(self, data: Any, input_node_id: str):
        """
        Process incoming data by squaring the signal array values.
        
        This method:
        1. Makes a shallow copy of the input data to avoid modifying the original
        2. Squares each value in the signal_array (element-wise x²)
        3. Forwards the modified data to downstream nodes
        
        Args:
            data (Any): The input data dictionary containing a 'signal_array' key
            input_node_id (str): The ID of the node that sent this data
            
        Raises:
            ValueError: If the input data doesn't contain a 'signal_array' key
        """
        if 'signal_array' in data:
            data = data.copy()
            data['signal_array'] = data['signal_array']**2
            self.subject.on_next(data)
        else:
            logger.error(f"Node {self.id}: Input data missing required 'signal_array' key")
            raise ValueError(f"Input data must contain 'signal_array' key. Received keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
