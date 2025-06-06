from copy import deepcopy
import asyncio
from typing import Optional
from data_node import Node
from reactivex import operators as ops

class ExpWeightedMovingAverage(Node):
    def __init__(self, node_id: str, node_type: str, params: dict, loop: Optional[asyncio.AbstractEventLoop] = None):
        super().__init__(node_id=node_id, node_type=node_type, params=params, loop=loop)
        print("ExpWeightedMovingAverage operator initialized")
        self.alpha = params.get('alpha', 0.1)  # Smoothing factor, default 0.1
        print(f"alpha = {self.alpha}")

    def subscribe_to_input(self, input_node: 'Node') -> bool:
        if self.node_type == "catchment":
            print("Node is not intended to receive data")
            return False
        if input_node.id in self.input_subscriptions:
            print(f"Node {self.id} already subscribed to {input_node.id}")
            return False

        print(f"Node {self.id} subscribing to {input_node.id} (exp weighted)")
        alpha = self.alpha

        def ewma(acc, data):
            prev_avg = acc[0] if acc and acc[0] is not None else data['signal_array']
            avg = alpha * data['signal_array'] + (1 - alpha) * prev_avg
            out = deepcopy(data)
            out['signal_array'] = avg
            return (avg, out)

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
        print(subscription)
        return True