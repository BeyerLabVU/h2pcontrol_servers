# data_source.py
import logging
import numpy as np
import asyncio
import PySide6.QtAsyncio as QtAsyncio

# This class is a basic parent class for any oscilloscope.
# All specific implementations, e.g. picoscope, should inherit from this one.
class DataReceiver():
    menu_name = "Dummy Source"
    menu_tooltip = \
        "This is a dummy data source that doubles as the parent class for implementations of \
            interfaces for real oscilloscopes (or other data sources).  It is also intended as \
                a sort of worst-case scenario, running at 20Hz and sending much more data than a \
                    typical oscilloscope would."

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__) # Use a module-specific logger
        self.logger.info("DataReceiver initialized")

    # Functions for populating settings
    def valid_vscales_volts(self) -> list[float]:
        return [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]

    def valid_sample_intervals_ns(self) -> list[float]:
        return [1, 5, 10, 50, 100, 500, 1000]

    async def get_trace(self):
        """
        Asynchronously generates oscilloscope traces continuously.
        Yields:
            tuple: (time_array, signal_array)
        """
        trace_count = 0
        self.logger.info("Starting continuous trace generation...")
        while True:  # Loop to continuously generate data
            await asyncio.sleep(0.04)  # Simulate data acquisition delay; controls update rate: double the update rate for stress testing
            t = np.linspace(0, 1, 10000)  # Reduced points for potentially smoother/faster plotting
            
            # Modify the signal over time to visualize updates
            phase_shift = trace_count * np.pi / 30  # Introduce a phase shift
            noise = np.random.randn(len(t)) * 0.05 # Add a little noise
            signal = np.sin(10.0 * np.pi * t + phase_shift) + noise
            
            self.logger.debug(f"Yielding trace {trace_count}")
            yield t, signal
            trace_count += 1