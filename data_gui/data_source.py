# data_source.py
import logging
import time
import numpy as np
import asyncio
from PySide6.QtCore import Signal, QObject # Added Signal, QObject

# This class is a basic parent class for any oscilloscope.
# All specific implementations, e.g. picoscope, should inherit from this one.
class DataReceiver(QObject): # Inherit from QObject to support signals
    menu_name = "Dummy Source (2 Channels)" # Updated name
    menu_tooltip = \
        "This is a dummy data source that doubles as the parent class for implementations of \
            interfaces for real oscilloscopes (or other data sources).  It is also intended as \
                a sort of worst-case scenario, running at 20Hz and sending much more data than a \
                    typical oscilloscope would."

    # Signals for visual properties of traces, including channel index
    trace_color_changed = Signal(int, tuple)      # channel_idx, (r, g, b)
    trace_display_changed = Signal(int, bool)     # channel_idx, is_visible
    # Add other signals as needed, e.g., for voltage scale, offset affecting display directly

    NUM_CHANNELS = 2 # Define number of channels
    CHANNEL_COLORS = [(255, 100, 100), (100, 100, 255)] # Default colors for channels

    def __init__(self, control_panel=None) -> None:
        super().__init__() # Call QObject constructor
        self.logger = logging.getLogger(__name__) 
        self.logger.info(f"{self.menu_name} initialized")
        self.control_panel = control_panel
        self.oscilloscope_controls = [] # Store multiple control panels

        if self.control_panel is not None:
            self.add_oscilloscope_controls() 

    # Functions for populating settings
    def valid_vscales_volts(self) -> list[float]:
        return [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]

    def valid_sample_intervals_ns(self) -> list[float]:
        return [1, 5, 10, 50, 100, 500, 1000]

    async def get_trace(self):
        trace_count = 0
        self.logger.info("Starting continuous trace generation for multiple channels...")

        start_time = time.perf_counter()
        sleep_time_adj = 0.0
        while True:
            t = np.linspace(0, 1, 10000)
            for i in range(self.NUM_CHANNELS):
                phase_shift = trace_count * np.pi / (30 + i*5)
                noise = np.random.randn(len(t)) * (0.05 + i*0.02)

                if i == 0:
                    signal = np.sin(10.0 * np.pi * t + phase_shift) + noise
                else:
                    signal = np.cos(12.0 * np.pi * t + phase_shift) + noise

                self.logger.debug(f"Yielding trace {trace_count} for channel {i}")
                yield i, t, signal

            trace_count += 1

            # Calculate how much time to sleep to maintain 20Hz
            elapsed_time = time.perf_counter() - start_time
            start_time = time.perf_counter()
            sleep_time_error = 0.05 - elapsed_time
            sleep_time_adj += 0.1 * sleep_time_error
            await asyncio.sleep(max(0, 0.05 + sleep_time_adj))

    def add_oscilloscope_controls(self):
        # Placeholder
        pass

    # Utility methods for channel control panels
    def update_save_data(self, channel_idx, state):
        # Placeholder for logic to handle logging state change for a channel
        pass

    def update_display(self, channel_idx, state):
        # Placeholder for logic to handle display state change for a channel
        pass

    def set_voltage_scale(self, channel_idx, scale):
        # Placeholder for logic to set voltage scale for a channel
        pass

    def set_offset(self, channel_idx, offset):
        # Placeholder for logic to set offset for a channel
        pass

    def set_enabled(self, channel_idx, enabled):
        # Placeholder for logic to enable/disable a channel
        pass

    def set_logging(self, channel_idx, logging):
        # Placeholder for logic to enable/disable logging for a channel
        pass

    def set_display(self, channel_idx, display):
        # Placeholder for logic to show/hide trace for a channel
        pass