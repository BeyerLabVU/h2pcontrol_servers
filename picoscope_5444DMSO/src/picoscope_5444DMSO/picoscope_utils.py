# Picoscope imports
from collections.abc import AsyncIterator
from picosdk.ps5000a import ps5000a as ps

# Utility imports
import asyncio
import logging
import datetime
from si_prefix import si_format
import numpy as np

# GRPC imports
from ps5444DMSO.picoscope_5444DMSO import (
    Empty, ConfigBase, VoltScale, VoltScaleListResponse, 
    AllTraces, ChannelTrace, Timestamp, StreamAllTracesBase
)

class Config(ConfigBase):
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.logger.info("Config initialized")
        self.valid_scale_names, self.valid_scales = self.util_generate_valid_voltage_scales()

    def util_generate_valid_voltage_scales(self):
        '''Generates the valid voltage scales for the picoscope'''
        idx = -1
        valid_scale_names = []
        valid_scales = []
        for exponent in [1, 2, 3, 4]:
            for first_digit in [1, 2, 5]:
                idx += 1
                channel_range = first_digit * (10**(exponent - 3))
                valid_scales.append(channel_range)
                valid_scale_names.append(f'+/-{si_format(channel_range)}V : {list(ps.PS5000A_RANGE.keys())[idx]}') # type: ignore
        self.logger.info(f"voltage scales: {valid_scale_names}")
        return valid_scale_names, valid_scales

    async def get_valid_voltage_scales(self, message: Empty) -> VoltScaleListResponse:
        response = VoltScaleListResponse()
        for name, scale in zip(self.valid_scale_names, self.valid_scales):
            response.scales.append(VoltScale(name, scale))
        self.logger.info(response)
        return response

class StreamAllTraces(StreamAllTracesBase):
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.logger.info("Trace Streamer initialized")

    def timestamp_now(self) -> Timestamp:
        t = datetime.datetime.now().timestamp()
        seconds = int(t)
        nanos = int(t % 1 * 1e9)
        return Timestamp(seconds, nanos)

    async def stream_traces(self, message: Empty) -> AsyncIterator[AllTraces]:
        
        self.logger.info("Starting stream!")
        while True:
            # Make a fake trace
            channel = 0
            sample_interval = 1
            voltage_scale = 0.1
            ts = self.timestamp_now()
            trace = np.random.normal(size = [1000, 1])
            trace = ChannelTrace(channel, sample_interval, voltage_scale, ts)

            # Collect the individual traces
            trace_list = AllTraces()
            trace_list.traces.append(trace)

            yield trace_list
            await asyncio.sleep(0.1)