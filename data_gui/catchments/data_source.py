import asyncio
import time
import logging
import numpy as np
import reactivex
from reactivex import operators as ops
from reactivex.subject import Subject
from reactivex.scheduler.eventloop import AsyncIOScheduler

# Set up logger for this module
logger = logging.getLogger(__name__)

class DataSource():
    """
    Base class for data sources that generate signal traces.
    
    This class provides the foundation for creating data sources that generate
    simulated signal data at regular intervals. It handles the lifecycle of the
    data generation process including starting, stopping, and emitting data through
    a ReactiveX Subject that consumers can subscribe to.
    
    Attributes:
        name (str): Descriptive name for this data source
        trace_subject (Subject): ReactiveX Subject that emits trace data
        _stop_requested (bool): Flag to signal stopping of data generation
        _is_running (bool): Flag indicating if the source is currently running
        loop (asyncio.AbstractEventLoop): AsyncIO event loop for scheduling
        scheduler (AsyncIOScheduler): ReactiveX scheduler for the event loop
    """
    def __init__(self, name="Dummy Data Source", loop=None):
        """
        Initialize a new data source.
        
        Args:
            name (str): Descriptive name for this data source
            loop (asyncio.AbstractEventLoop, optional): AsyncIO event loop to use.
                If None, the current event loop is used.
        """
        self.name = name
        self.trace_subject = Subject()
        self._stop_requested = False
        self._is_running = False
        self.loop = loop if loop else asyncio.get_event_loop()
        self.scheduler = AsyncIOScheduler(loop=self.loop)
        self._subscription = None
        logger.info(f"DataSource '{name}' initialized")

    async def start(self):
        """
        Start generating data traces.
        
        This method starts the asynchronous data generation process if it's not already running.
        It creates a new asyncio task that runs the gen_traces_signal method.
        
        Returns:
            None
        """
        if self._is_running:
            logger.info(f"DataSource '{self.name}' is already running")
            return
            
        logger.info(f"Starting DataSource '{self.name}'")
        self._stop_requested = False
        self._is_running = True
        # Create a task to generate traces in the background
        asyncio.create_task(self.gen_traces_signal())

    async def stop(self):
        """
        Stop generating data traces.
        
        This method signals the data generation process to stop by setting
        the _stop_requested flag. The actual stopping happens asynchronously
        when the gen_traces_signal method checks this flag.
        
        Returns:
            None
        """
        if not self._is_running:
            logger.info(f"DataSource '{self.name}' is not running")
            return
            
        logger.info(f"Stopping DataSource '{self.name}'")
        self._stop_requested = True
        self._is_running = False

    async def gen_traces_signal(self):
        """
        Asynchronously generates simulated signal traces at regular intervals.
        
        This method runs in a loop until _stop_requested is set to True.
        For each iteration, it:
        1. Generates a time array and corresponding signal with noise
        2. Emits the data through the trace_subject
        3. Adjusts sleep time to maintain a target update rate (approx. 20Hz)
        
        The generated signal is a damped sine wave with random noise and
        a phase shift that changes with each trace.
        
        Returns:
            None
        """
        trace_count = 0
        logger.info(f"Starting continuous trace generation for '{self.name}'")

        start_time = time.perf_counter()
        sleep_time_adj = 0.0
        while not self._stop_requested:
            t = np.linspace(0, 10e-6, 10000) # Example time base
            # Adjust signal generation based on channel index or source properties
            phase_shift = trace_count * np.pi / (30 + hash(self.name)%10) # Vary per source
            noise = np.random.randn(len(t)) * (0.05)

            signal =  1.0 * np.exp(-t / (3e-6)) * np.sin(2 * np.pi * (1e6) * t + phase_shift) + noise
            
            if not self._stop_requested: # Check again before emitting
                self.trace_subject.on_next({"name": self.name, "time_array": t, "signal_array": signal})

            trace_count += 1
            if self._stop_requested:
                break

            # Calculate how much time to sleep to maintain approx 20Hz update rate per source
            current_time = time.perf_counter()
            elapsed_time = current_time - start_time
            start_time = current_time # Reset start_time for next iteration's measurement
            
            target_interval = 0.025
            sleep_time_error = target_interval - elapsed_time
            sleep_time_adj += 0.1 * sleep_time_error # Proportional adjustment
            sleep_time_adj = max(-target_interval*0.5, min(target_interval*0.5, sleep_time_adj)) # Clamp adjustment

            actual_sleep_time = max(0, target_interval + sleep_time_adj)
            
            try:
                await asyncio.sleep(actual_sleep_time)
            except asyncio.CancelledError:
                logger.warning(f"DataSource '{self.name}': Generation task cancelled")
                break
        
        logger.info(f"DataSource '{self.name}': Trace generation stopped after {trace_count} traces")

async def main():
    """
    Example function demonstrating how to use the DataSource class.
    
    This function:
    1. Creates a data source
    2. Sets up a subscription to receive and process the data
    3. Starts the data source
    4. Runs for a fixed duration
    5. Properly cleans up resources
    
    Returns:
        None
    """
    # Configure basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get the event loop
    loop = asyncio.get_event_loop()
    source1 = DataSource(name="RF Source 1", loop=loop)

    def handle_trace_data(trace_data):
        """Process received trace data"""
        logger.info(
            f"Received trace from '{trace_data['name']}' with "
            f"{len(trace_data['time_array'])} points"
        )

    # Subscribe before starting the signal generator
    # Each source has its own subject
    sub1 = source1.trace_subject.pipe(
        ops.observe_on(source1.scheduler)
    ).subscribe(
        on_next=handle_trace_data,
        on_error=lambda e: logger.error(f"Error in source1: {e}"),
        on_completed=lambda: logger.info("Source1 completed")
    )

    await source1.start()

    try:
        # Keep the loop running for a bit
        logger.info("Running data source for 10 seconds...")
        await asyncio.sleep(10)
    finally:
        logger.info("Cleaning up resources...")
        await source1.stop()
        sub1.dispose()
        logger.info("Data sources stopped and subscriptions disposed")
        # Allow tasks to complete
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Application interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
