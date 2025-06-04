import asyncio
import time
import numpy as np
import reactivex
from reactivex import operators as ops
from reactivex.subject import Subject
from reactivex.scheduler.eventloop import AsyncIOScheduler

class DataSource():
    '''Base class for data sources.'''

    def __init__(self, name="Dummy Data Source", n_channels=2, loop=None):
        self.name = name
        self.n_channels = n_channels
        self.trace_subject = Subject()
        self._stop_requested = False
        self._is_running = False
        self.loop = loop if loop else asyncio.get_event_loop()
        self.scheduler = AsyncIOScheduler(loop=self.loop)
        self._subscription = None

    async def start(self):
        if self._is_running:
            print(f"{self.name} is already running.")
            return
        print(f"Starting {self.name}...")
        self._stop_requested = False
        self._is_running = True
        asyncio.create_task(self.gen_traces_signal())


    async def stop(self):
        if not self._is_running:
            print(f"{self.name} is not running.")
            return
        print(f"Stopping {self.name}...")
        self._stop_requested = True
        self._is_running = False

    async def gen_traces_signal(self):
        """
        Asynchronously generates oscilloscope traces continuously for multiple channels.
        Yields:
            tuple: (channel_idx, time_array, signal_array)
        """
        trace_count = 0
        print(f"Starting continuous trace generation for {self.name} with {self.n_channels} channels...")

        start_time = time.perf_counter()
        sleep_time_adj = 0.0
        while not self._stop_requested:
            t = np.linspace(0, 10e-6, 10000) # Example time base
            for i in range(self.n_channels):
                # Adjust signal generation based on channel index or source properties
                phase_shift = trace_count * np.pi / (30 + i*5 + hash(self.name)%10) # Vary per source
                noise = np.random.randn(len(t)) * (0.05 + i*0.02)

                if i % 2 == 0: # Example: different signals for even/odd channels
                    signal =  1.0 * np.exp(-t / (3e-6 + i*1e-7)) * np.sin(2 * np.pi * (1e6 + i*0.1e6) * t + phase_shift) + noise
                else:
                    signal = -0.5 * np.exp(-t / (3e-6 + i*1e-7)) * np.sin(2 * np.pi * (2e6 + i*0.1e6) * t + phase_shift) - noise
                
                if not self._stop_requested: # Check again before emitting
                    self.trace_subject.on_next({"name": self.name, "channel_idx": i, "time_array": t, "signal_array": signal})

            trace_count += 1
            if self._stop_requested:
                break

            # Calculate how much time to sleep to maintain approx 20Hz update rate per source
            current_time = time.perf_counter()
            elapsed_time = current_time - start_time
            start_time = current_time # Reset start_time for next iteration's measurement
            
            target_interval = 0.05 # 20 Hz
            sleep_time_error = target_interval - elapsed_time
            sleep_time_adj += 0.1 * sleep_time_error # Proportional adjustment
            sleep_time_adj = max(-target_interval*0.5, min(target_interval*0.5, sleep_time_adj)) # Clamp adjustment

            actual_sleep_time = max(0, target_interval + sleep_time_adj)
            
            try:
                await asyncio.sleep(actual_sleep_time)
            except asyncio.CancelledError:
                print(f"{self.name} generation task cancelled.")
                break
        
        print(f"{self.name} trace generation stopped.")

async def main():
    # Example of using multiple data sources
    loop = asyncio.get_event_loop()
    source1 = DataSource(name="RF Source 1", n_channels=2, loop=loop)
    source2 = DataSource(name="Sensor Array A", n_channels=4, loop=loop)

    def print_trace_info(trace_data):
        print(f"Received trace from {trace_data['name']} for channel {trace_data['channel_idx']} with {len(trace_data['time_array'])} points")

    # Subscribe before starting the signal generator
    # Each source has its own subject
    sub1 = source1.trace_subject.pipe(
        ops.observe_on(source1.scheduler)
    ).subscribe(
        on_next=print_trace_info,
        on_error=lambda e: print(f"Error in source1: {e}"),
        on_completed=lambda: print("Source1 completed")
    )

    sub2 = source2.trace_subject.pipe(
        ops.observe_on(source2.scheduler)
    ).subscribe(
        on_next=print_trace_info,
        on_error=lambda e: print(f"Error in source2: {e}"),
        on_completed=lambda: print("Source2 completed")
    )

    await source1.start()
    await source2.start()

    try:
        # Keep the loop running for a bit
        await asyncio.sleep(10)
    finally:
        print("Stopping data sources...")
        await source1.stop()
        await source2.stop()
        sub1.dispose()
        sub2.dispose()
        print("Data sources stopped and subscriptions disposed.")
        # Allow tasks to complete
        await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Application interrupted. Stopping data source...")