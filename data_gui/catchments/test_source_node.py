import asyncio
from data_node import Node
from catchments.data_source import DataSource

class CatchmentNode(Node):
    """
    A Node subclass that acts as a data source catchment.
    It ignores all input connections and subscribes to a DataSource.
    """

    def __init__(self, node_id: str, data_source: DataSource, params: dict = None, loop=None):
        super().__init__(node_id, node_type="catchment", params=params or {}, loop=loop)
        self.data_source = data_source
        self._data_subscription = None
        self._setup_data_source_subscription()

    def _setup_data_source_subscription(self):
        # Subscribe to the DataSource's trace_subject and forward data to this node's subject
        self._data_subscription = self.data_source.trace_subject.pipe().subscribe( # type: ignore
            on_next=self._on_data,
            on_error=self._on_error,
            on_completed=self._on_completed
        )

    def _on_data(self, data):
        # Forward data to this node's subject
        self.subject.on_next(data)

    def _on_error(self, error):
        print(f"[{self.id}] DataSource error: {error}")
        self.subject.on_error(error)

    def _on_completed(self):
        print(f"[{self.id}] DataSource completed.")
        self.subject.on_completed()

    def subscribe_to_input(self, input_node: 'Node') -> bool:
        # Ignore all input connections for catchment nodes
        print(f"[{self.id}] CatchmentNode ignores input connections.")
        return False

    def dispose(self):
        # Clean up the subscription to the data source
        if self._data_subscription:
            self._data_subscription.dispose()
            self._data_subscription = None
        super().dispose()