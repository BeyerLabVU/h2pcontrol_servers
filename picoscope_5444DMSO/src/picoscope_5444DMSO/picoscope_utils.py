# Picoscope imports
from collections.abc import AsyncIterator
from picosdk.ps5000a import ps5000a as ps
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc
from picosdk.constants import PICO_STATUS

# Utility imports
import ctypes
import asyncio
import logging
import datetime
from si_prefix import si_format
import numpy as np

# GRPC imports
from ps5444DMSO.picoscope_5444DMSO import *

coupling_type_dict = {
    0: ps.PS5000A_COUPLING['PS5000A_DC'],
    1: ps.PS5000A_COUPLING['PS5000A_AC'],
}

trigger_type_dict = {
    0: 'ABOVE',
    1: 'BELOW',
    2: 'RISING',
    3: 'FALLING',
    4: 'RISING_OR_FALLING',
}

resolution_dict = {
    8 : ps.PS5000A_DEVICE_RESOLUTION['PS5000A_DR_8BIT'],
    12: ps.PS5000A_DEVICE_RESOLUTION['PS5000A_DR_12BIT'],
    14: ps.PS5000A_DEVICE_RESOLUTION['PS5000A_DR_14BIT'],
    16: ps.PS5000A_DEVICE_RESOLUTION['PS5000A_DR_16BIT'],
}

channel_dict = {
    0: ps.PS5000ACHANNEL['PS5000A_CHANNEL_A'],
    1: ps.PS5000ACHANNEL['PS5000A_CHANNEL_B'],
    2: ps.PS5000ACHANNEL['PS5000A_CHANNEL_C'],
    3: ps.PS5000ACHANNEL['PS5000A_CHANNEL_D'],
}

class Config(ConfigBase):
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.logger.info("Config initialized")
        self.valid_scale_names, self.valid_scales = self.util_generate_valid_voltage_scales()
        self.voltage_scale_dict = {idx: ps.PS5000A_RANGE[scale_name] for idx, scale_name in enumerate(self.valid_scale_names)}
        self.open_picoscope()

    def open_picoscope(self):
        # Create chandle and status ready for use
        self.chandle = ctypes.c_int16()
        self.status = {}
        # Returns handle to chandle for use in future API functions
        self.status["openunit"] = ps.ps5000aOpenUnit(ctypes.byref(self.chandle), None, resolution_dict[8])  # 16-bit resolution
        # Open Picoscope and configure the power source
        try:
            assert_pico_ok(self.status["openunit"])
            self.logger.info("External power source available.")
        except: # PicoNotOkError:
            self.logger.info("WARNING: Picoscope powered by USB")
            self.powerStatus = self.status["openunit"]

            if self.powerStatus == 286:
                self.status["changePowerSource"] = ps.ps5000aChangePowerSource(self.chandle, self.powerStatus)
            elif self.powerStatus == 282:
                self.status["changePowerSource"] = ps.ps5000aChangePowerSource(self.chandle, self.powerStatus)
            else:
                raise
            assert_pico_ok(self.status["changePowerSource"])

        self.maxADC = ctypes.c_int16()
        self.status["maximumValue"] = ps.ps5000aMaximumValue(self.chandle, ctypes.byref(self.maxADC))
        assert_pico_ok(self.status["maximumValue"])
        self.logger.info("Picocscope opened successfully.")
    
    async def configure_channel(self, message: ChannelRequest) -> ChannelResponse:
        self.logger.info(f"Configuring channel: {message.channel}")
        # Check if the channel is valid
        if message.channel < 0 or message.channel > 3:
            self.logger.error(f"Invalid channel: {message.channel}. Must be between 0 and 3.")
            raise ValueError(f"Invalid channel: {message.channel}. Must be between 0 and 3.")
        # Check if the coupling type is valid
        if message.coupling not in coupling_type_dict:
            self.logger.error(f"Invalid coupling type: {message.coupling}. Must be 0 or 1.")
            raise ValueError(f"Invalid coupling type: {message.coupling}. Must be 0 or 1.")
        # Check if the trigger type is valid
        if message.trigger_type not in trigger_type_dict:
            self.logger.error(f"Invalid trigger type: {message.trigger_type}. Must be 0, 1, 2, 3, or 4.")
            raise ValueError(f"Invalid trigger type: {message.trigger_type}. Must be 0, 1, 2, 3, or 4.")
        # Check if the voltage scale is valid
        if message.voltage_scale not in self.valid_scales:
            self.logger.error(f"Invalid voltage scale: {message.voltage_scale}. Must be one of the valid scales.")
            raise ValueError(f"Invalid voltage scale: {message.voltage_scale}. Must be one of the valid scales.")
        
        self.logger.info(f"Configuring channel {message.channel} with coupling {coupling_type_dict[message.coupling]} and trigger type {trigger_type_dict[message.trigger_type]}")
        self.logger.info(f"Voltage scale set to {message.voltage_scale} V")
        self.logger.info(f"Sample interval set to {message.sample_interval} ns")

        try:
            self.status["setActiveChannel"] = ps.ps5000aSetChannel(
                self.chandle, 
                channel_dict[message.channel], 
                ctypes.c_int16(1) if message.enabled else ctypes.c_int16(0),
                coupling_type_dict[message.coupling], 
                self.voltage_scale_dict[message.voltage_scale],
                message.analog_offset if message.analog_offset_volts is not None else 0.0,
            )
        except Exception as e:
            return ChannelResponse(
                success=False,
                error_message=f"Failed to set channel: {str(e)}"
            )
        return ChannelResponse(
            success=True,
            error_message=None
        )
    
    async def parse_timebase(self, message):
        return await super().parse_timebase(message)
    
    async def get_shortest_timebase(self, message):
        return await super().get_shortest_timebase(message)
    
    async def configure_timebase(self, message):
        return await super().configure_timebase(message)

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

    async def get_valid_voltage_scales(self, message: Empty) -> VoltScaleList:
        response = VoltScaleList()
        for name, scale in zip(self.valid_scale_names, self.valid_scales):
            response.scales.append(VoltScale(name, scale))
        self.logger.info(response)
        return response
    
    async def get_valid_time_scales(self, message: Empty) -> TimeScaleList:
        return await super().get_valid_time_scales(message)
    
    async def get_valid_coupling_types(self, message: Empty) -> CouplingTypeList:
        return await super().get_valid_coupling_types(message)
    
    async def get_valid_trigger_types(self, message: Empty) -> TriggerTypeList:
        return await super().get_valid_trigger_types(message)

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