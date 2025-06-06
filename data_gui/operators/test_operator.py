import asyncio
from typing import Any, Optional
from data_node import Node

class SquareOperator(Node):
    def __init__(self, node_id: str, node_type: str, params: dict, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(node_id = node_id, node_type=node_type, params=params, loop = loop)
        print("Test square operator initialized")
    
    def process_input(self, data: Any, input_node_id: str):
        if 'signal_array' in data:
            data = data.copy()
            data['signal_array'] = data['signal_array']**2
            self.subject.on_next(data)
        else:
            print("erropr")
            raise ValueError("Input data must contain 'signal_array'.")