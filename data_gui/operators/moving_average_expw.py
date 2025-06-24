from copy import deepcopy
import asyncio
import logging
from typing import Optional, Tuple, Any
from data_node import Node
from reactivex import operators as ops

# Set up logger for this module
logger = logging.getLogger(__name__)

class ExpWeightedMovingAverage(Node):
    """
    A Node that implements an exponentially weighted moving average filter.
    
    This operator applies an EWMA filter to the input signal, which gives
    more weight to recent data points and less weight to older ones.
    The smoothing factor alpha controls how much weight is given to the most recent
    observation compared to older observations.
    
    Parameters:
        alpha (float): Smoothing factor between 0 and 1. Default is 0.1.
                      Higher values give more weight to recent observations.
    """
    def __init__(self, node_id: str, node_type: str, params: dict, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(node_id=node_id, node_type=node_type, params=params, loop=loop)
        self.alpha = params.get('alpha', 0.1)  # Smoothing factor, default 0.1
        logger.info(f"ExpWeightedMovingAverage operator initialized: {node_id} with alpha={self.alpha}")

    def subscribe_to_input(self, input_node: 'Node') -> bool:
        """
        Subscribe to an input node and set up the EWMA processing pipeline.
        
        This method overrides the base Node.subscribe_to_input to implement
        the exponentially weighted moving average calculation using ReactiveX operators.
        
        Args:
            input_node (Node): The node to subscribe to for input data
            
        Returns:
            bool: True if subscription was successful, False otherwise
        """
        if self.node_type == "catchment":
            logger.warning(f"Node {self.id}: Cannot subscribe - node type 'catchment' is not intended to receive data")
            return False
        if input_node.id in self.input_subscriptions:
            logger.info(f"Node {self.id}: Already subscribed to {input_node.id}")
            return False

        logger.info(f"Node {self.id}: Subscribing to {input_node.id} with EWMA filter (alpha={self.alpha})")
        alpha = self.alpha

        def ewma(acc: Tuple[Any, Any], data: dict) -> Tuple[Any, dict]:
            """
            Apply exponentially weighted moving average to the signal data.
            
            Args:
                acc: Tuple containing (previous_avg, previous_output)
                data: Input data dictionary with 'signal_array' key
                
            Returns:
                Tuple of (new_avg, new_output_data)
                
            Raises:
                KeyError: If data doesn't contain 'signal_array'
                ValueError: If signal arrays have incompatible shapes
            """
            try:
                if 'signal_array' not in data:
                    logger.error(f"Node {self.id}: Input data missing required 'signal_array' key")
                    raise KeyError(f"Input data must contain 'signal_array' key. Received keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                
                # For first data point, use input as initial value
                prev_avg = acc[0] if acc and acc[0] is not None else data['signal_array']
                
                # Check for shape compatibility
                if prev_avg is not None and hasattr(prev_avg, 'shape') and hasattr(data['signal_array'], 'shape'):
                    if prev_avg.shape != data['signal_array'].shape:
                        logger.warning(f"Node {self.id}: Shape mismatch in EWMA - prev: {prev_avg.shape}, current: {data['signal_array'].shape}")
                        # Reset by using current data as new baseline
                        prev_avg = data['signal_array']
                
                # Calculate EWMA: new_avg = α * current + (1-α) * prev_avg
                avg = alpha * data['signal_array'] + (1 - alpha) * prev_avg
                
                # Create output data with the averaged signal
                out = deepcopy(data)
                out['signal_array'] = avg
                return (avg, out)
                
            except Exception as e:
                logger.error(f"Node {self.id}: Error in EWMA calculation: {str(e)}")
                # Pass through original data on error
                return (data.get('signal_array'), data)

        subscription = input_node.subject.pipe(
            ops.scan(lambda acc, data: ewma(acc, data), seed=(None, None)),
            ops.map(lambda tup: tup[1]),
            ops.observe_on(self.scheduler)
        ).subscribe(
            on_next=lambda data: self.subject.on_next(data),
            on_error=self.subject.on_error,
            on_completed=lambda: self.handle_input_completion(input_node.id),
            scheduler=self.scheduler
        )
        self.input_subscriptions[input_node.id] = subscription
        logger.debug(f"Node {self.id}: Subscription created: {subscription}")
        return True
