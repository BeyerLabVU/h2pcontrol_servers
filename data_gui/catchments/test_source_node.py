import asyncio
import logging
from typing import Optional
from data_node import Node
from catchments.data_source import DataSource

# Set up logger for this module
logger = logging.getLogger(__name__)

class CatchmentNode(Node):
    """
    A Node subclass that acts as a data source catchment.
    
    This node serves as an adapter between a DataSource and the node network.
    It subscribes to a DataSource's trace_subject and forwards the received data
    to its own subject, making the data available to downstream nodes in the network.
    
    CatchmentNode ignores all input connections since it's designed to be a source node
    that only receives data from its associated DataSource.
    
    Attributes:
        data_source (DataSource): The data source this node is connected to
        _data_subscription: Subscription to the data source's trace_subject
    """

    def __init__(self, node_id: str, data_source: DataSource, params: dict = None, loop: Optional[asyncio.AbstractEventLoop] = None):
        """
        Initialize a new CatchmentNode.
        
        Args:
            node_id (str): Unique identifier for this node
            data_source (DataSource): The data source to subscribe to
            params (dict, optional): Configuration parameters for this node
            loop (asyncio.AbstractEventLoop, optional): AsyncIO event loop to use
        """
        super().__init__(node_id, node_type="catchment", params=params or {}, loop=loop)
        self.data_source = data_source
        self._data_subscription = None
        logger.info(f"CatchmentNode '{node_id}' initialized with data source '{data_source.name}'")
        self._setup_data_source_subscription()

    def _setup_data_source_subscription(self):
        """
        Set up the subscription to the data source's trace_subject.
        
        This method creates a subscription that forwards all data, errors,
        and completion events from the data source to this node's subject.
        """
        logger.debug(f"Node '{self.id}': Setting up subscription to data source '{self.data_source.name}'")
        self._data_subscription = self.data_source.trace_subject.pipe().subscribe( # type: ignore
            on_next=self._on_data,
            on_error=self._on_error,
            on_completed=self._on_completed
        )

    def _on_data(self, data):
        """
        Handle data received from the data source.
        
        This callback forwards the received data to this node's subject,
        making it available to downstream nodes.
        
        Args:
            data: The data received from the data source
        """
        # Forward data to this node's subject
        self.subject.on_next(data)

    def _on_error(self, error):
        """
        Handle errors from the data source.
        
        This callback logs the error and forwards it to this node's subject.
        
        Args:
            error: The error received from the data source
        """
        logger.error(f"Node '{self.id}': DataSource error: {error}")
        self.subject.on_error(error)

    def _on_completed(self):
        """
        Handle completion of the data source.
        
        This callback logs the completion and forwards it to this node's subject.
        """
        logger.info(f"Node '{self.id}': DataSource completed")
        self.subject.on_completed()

    def subscribe_to_input(self, input_node: 'Node') -> bool:
        """
        Override of Node.subscribe_to_input that always returns False.
        
        CatchmentNode is designed to be a source node that only receives data
        from its associated DataSource, so it ignores all input connections.
        
        Args:
            input_node (Node): The node attempting to connect to this node
            
        Returns:
            bool: Always False, indicating the subscription was rejected
        """
        logger.warning(f"Node '{self.id}': Ignoring attempt to subscribe to input node '{input_node.id}' - CatchmentNodes do not accept input connections")
        return False

    def dispose(self):
        """
        Clean up resources used by this node.
        
        This method disposes of the subscription to the data source and
        calls the parent class's dispose method to clean up other resources.
        """
        logger.info(f"Node '{self.id}': Disposing resources")
        # Clean up the subscription to the data source
        if self._data_subscription:
            logger.debug(f"Node '{self.id}': Disposing data source subscription")
            self._data_subscription.dispose()
            self._data_subscription = None
        super().dispose()
