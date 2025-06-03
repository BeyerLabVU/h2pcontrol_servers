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
    0: ps.PS5000A_CHANNEL['PS5000A_CHANNEL_A'],
    1: ps.PS5000A_CHANNEL['PS5000A_CHANNEL_B'],
    2: ps.PS5000A_CHANNEL['PS5000A_CHANNEL_C'],
    3: ps.PS5000A_CHANNEL['PS5000A_CHANNEL_D'],
}

NUM_CHANNELS = 4

class _osci_channel():
    def __init__(self, channel_idx):
        self.channel_initialized = False
        self.channel_idx = channel_idx
        self.range_idx = None
        self.coupling_type = None
        self.active = False

    def activate_channel(self, range_idx, coupling_type):
        self.range_idx = range_idx
        self.coupling_type = coupling_type
        self.channel_initialized = True
        self.active = True

    def deactivate_channel(self):
        self.active = False

    def read_range_idx(self):
        if self.channel_initialized:
            return self.range_idx
        else:
            raise Exception("Reading channel range of unitialized channel!")

    def read_coupling_type(self):
        if self.channel_initialized:
            return self.coupling_type
        else:
            raise Exception("Reading coupling of unitialized channel!")

    def is_active(self):
        return self.active

class Config(ConfigBase):
    def __init__(self) -> None:
        self.picoscope_open = False
        self.logger = logging.getLogger(__name__)
        self.logger.info("Config initialized")
        self.valid_scale_names, self.valid_scales = self.util_generate_valid_voltage_scales()
        self.open_picoscope()

        self._channel_info = []
        for idx in range(NUM_CHANNELS):
            channel = _osci_channel(idx)
            self._channel_info.append(channel)


    def open_picoscope(self):
        # Create chandle and status ready for use
        self.chandle = ctypes.c_int16()
        self.status = {}
        # Returns handle to chandle for use in future API functions
        self.status["openunit"] = ps.ps5000aOpenUnit(ctypes.byref(self.chandle), None, resolution_dict[8])
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
        self.logger.info("Picoscope opened successfully.")
        self.logger.info(f"Maximum ADC value: {self.maxADC.value}")
        self.picoscope_open = True

    async def configure_trigger(self, message: TriggerConfig) -> ChannelResponse:
        try:
            self.logger.info(f"Configuring trigger: {trigger_type_dict[message.trigger_type]} on channel {message.trigger_channel_idx}")
            if message.trigger_holdoff_ns < 0:
                raise Exception("Picoscope server: holdoff must not be negative")
            ps_voltage_range = self._channel_info[message.trigger_channel_idx].read_range_idx()
            threshold_ADC = int(
                mV2adc(
                    message.trigger_level_volts * 1.0e+3, 
                    ps_voltage_range, 
                    self.maxADC
                )
            )
            self.logger.info(f'Trigger level readback: {round(adc2mV([threshold_ADC], ps_voltage_range, self.maxADC)[0])} mV')
            self.status["trigger"] = ps.ps5000aSetSimpleTrigger(
                self.chandle, 
                1,
                message.trigger_channel_idx,
                threshold_ADC, 
                message.trigger_type,
                message.trigger_holdoff_ns, 
                200, # automatic trigger timeout in ms
            )
            assert_pico_ok(self.status["trigger"])
            return ChannelResponse(
                success=True,
                message=None
            )
        except Exception as e:
            self.logger.error(f"Failed to configure trigger: {str(e)}")
            return ChannelResponse(
                success=False,
                message=f"Failed to configure trigger: {str(e)}"
            )
    
    async def configure_channel(self, message: ChannelRequest) -> ChannelResponse:
        self.logger.info(f"Configuring channel: {message.channel_idx}")
        # Check if the channel is valid
        if message.channel_idx < 0 or message.channel_idx > 3:
            self.logger.error(f"Invalid channel: {message.channel_idx}. Must be between 0 and 3.")
            raise ValueError(f"Invalid channel: {message.channel_idx}. Must be between 0 and 3.")
        # Check if the coupling type is valid
        if message.channel_coupling not in coupling_type_dict:
            self.logger.error(f"Invalid coupling type: {message.channel_coupling}. Must be 0 or 1.")
            raise ValueError(f"Invalid coupling type: {message.channel_coupling}. Must be 0 or 1.")
        # Check if the voltage scale is valid
        if message.channel_voltage_scale not in self.valid_scales:
            self.logger.error(f"Invalid voltage scale: {message.channel_voltage_scale}. Must be one of the valid scales.")
            raise ValueError(f"Invalid voltage scale: {message.channel_voltage_scale}. Must be one of the valid scales.")
        
        self.logger.info(f"Configuring channel {message.channel_idx} with coupling {coupling_type_dict[message.channel_coupling]}")
        self.logger.info(f"Voltage scale set to {message.channel_voltage_scale} V")

        try:
            self.status["setActiveChannel"] = ps.ps5000aSetChannel(
                self.chandle, 
                channel_dict[message.channel_idx], 
                ctypes.c_int16(1) if message.activate else ctypes.c_int16(0),
                coupling_type_dict[message.channel_coupling], 
                self.voltage_to_range[message.channel_voltage_scale],
                message.analog_offset_volts if message.analog_offset_volts is not None else 0.0,
            )
        except Exception as e:
            return ChannelResponse(
                success=False,
                message=f"Failed to set channel: {str(e)}"
            )
        if message.activate:
            self._channel_info[message.channel_idx].activate_channel(
                self.valid_scales.index(message.channel_voltage_scale), 
                message.channel_coupling
            )
        else:
            self._channel_info[message.channel_idx].deactivate_channel()
        return ChannelResponse(
            success=True,
            message=None
        )
    
    async def parse_timebase(self, message):
        # TODO
        raise NotImplementedError()
        return await super().parse_timebase(message)
    
    async def get_shortest_timebase(self, message):
        # TODO
        raise NotImplementedError()
        return await super().get_shortest_timebase(message)

    async def configure_timebase(self, message: TimebaseRequest) -> TimebaseResponse:
        self.logger.info(f"Configuring timebase: {message.timebase_idx} with {message.n_samples_pre_trigger} + {message.n_samples_post_trigger} samples")
        timeIntervalns = ctypes.c_int32()
        returnedMaxSamples = ctypes.c_int32()
        self.status["getTimebase2"] = ps.ps5000aGetTimebase(
            self.chandle, 
            message.timebase_idx, 
            message.n_samples_pre_trigger + message.n_samples_post_trigger, 
            ctypes.byref(timeIntervalns),
            ctypes.byref(returnedMaxSamples), 
            0,
        )
        print("NEW TIMEBASE: sample interval: %.3g ns, max returned samples %d" % (timeIntervalns.value, returnedMaxSamples.value))
        self.time_interval_ns = float(timeIntervalns.value)
        assert_pico_ok(self.status["getTimebase2"])
        return TimebaseResponse(
            timebase_idx = message.timebase_idx,
            sample_interval_ns = timeIntervalns.value,
            success = True,
            description = None,
        )

    def util_generate_valid_voltage_scales(self):
        # TODO: use PS5000AGetChannelInformation to get the valid ranges
        # also, generally just fix this, it's a really bad way to do it.
        idx = -1
        valid_scale_names = []
        valid_scales = []
        # Create a mapping from voltage values to PS5000A_RANGE values
        self.voltage_to_range = {}
        
        for exponent in [1, 2, 3, 4]:
            for first_digit in [1, 2, 5]:
                idx += 1
                channel_range = first_digit * (10**(exponent - 3))
                valid_scales.append(channel_range)
                range_key = list(ps.PS5000A_RANGE.keys())[idx]
                range_value = ps.PS5000A_RANGE[range_key]
                self.voltage_to_range[channel_range] = range_value
                valid_scale_names.append(f'+/-{si_format(channel_range)}V : {range_key}')
        
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
        # These will be set once stream_traces() starts running:
        self.queue: asyncio.Queue[AllTraces] | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        # We'll build the C‐callable block callback once:
        self.cFuncPtr = None

    def timestamp_now(self) -> Timestamp:
        t = datetime.datetime.now().timestamp()
        seconds = int(t)
        nanos = int((t % 1) * 1e9)
        return Timestamp(seconds, nanos)

    def util_run_block(self, timebase, set_pre_trigger_samples: int, postTriggerSamples: int) -> bool:
        """
        Kick off a single block‐mode capture. We assume:
         - self.cFuncPtr is already set to a ps.BlockReadyType(...) around self.block_ready_callback
         - self.preTriggerSamples, self.n_samples, self.timebase are already configured.
        """
        try:
            self.status["runBlock"] = ps.ps5000aRunBlock(
                self.chandle,
                ctypes.c_int32(preTriggerSamples),
                ctypes.c_int32(postTriggerSamples),
                ctypes.c_int32(timebase),
                None,
                ctypes.c_int16(0),
                self.cFuncPtr,
                None
            )
            assert_pico_ok(self.status["runBlock"])
            return True
        except Exception as e:
            self.logger.error(f"Failed to start block capture: {str(e)}")
            return False

    def block_ready_callback(self, handle, statusCallback, param):
        """
        This is invoked on a PicoSDK thread when a block of data is ready.
        We must:
          1. Read out all active channels into numpy arrays,
          2. Convert ADC->mV->V,
          3. Build an AllTraces proto containing one Trace per active channel,
          4. Put it into self.queue via loop.call_soon_threadsafe(...).
        """
        if statusCallback != PICO_STATUS['PICO_OK']:
            self.logger.error(f"Block capture failed with status: {statusCallback}")
            # You could choose to signal an error‐message via the queue or raise
            return

        # 1) For each active channel, set up two buffers (primary + overflow)
        trace_raw_buffers = {}
        for channel in self.channels:
            if channel.is_active():
                buf1 = (ctypes.c_int16 * self.n_samples)()
                buf2 = (ctypes.c_int16 * self.n_samples)()
                self.status["setDataBuffers_{}".format(channel.channel_idx)] = ps.ps5000aSetDataBuffers(
                    self.chandle,
                    channel.channel_idx,
                    ctypes.byref(buf1),
                    ctypes.byref(buf2),
                    ctypes.c_int32(self.n_samples),
                    0,
                    0
                )
                assert_pico_ok(self.status["setDataBuffers_{}".format(channel.channel_idx)])
                trace_raw_buffers[channel.channel_idx] = buf1

        # 2) Pull all values from the scope
        overflow = ctypes.c_int16()
        cmaxSamples = ctypes.c_int32(self.n_samples)
        self.status["getValues"] = ps.ps5000aGetValues(
            self.chandle,
            ctypes.c_int32(0),
            ctypes.byref(cmaxSamples),
            ctypes.c_int32(0),
            ctypes.c_int32(0),
            ctypes.c_int32(0),
            ctypes.byref(overflow)
        )
        if self.status["getValues"] == PICO_STATUS["PICO_NOT_RESPONDING"]:
            self.logger.error("PICOSCOPE CRASH DETECTED")
            return
        else:
            assert_pico_ok(self.status["getValues"])

        # 3) Convert time base -> seconds; convert ADC -> volts
        time_axis = np.linspace(
            0.0,
            float((self.n_samples - 1) * self.time_interval_ns) * 1.0e-9,
            num=self.n_samples
        )
        # List of numpy arrays: index 0 is time_axis, then each channel’s voltage array in volts.
        Vch = [time_axis]
        for channel in self.channels:
            if channel.is_active():
                raw_buf = trace_raw_buffers[channel.channel_idx]
                # Convert raw ADC to mV, then to V
                volts = np.array(
                    adc2mV(raw_buf, channel.read_range_idx(), self.maxADC),
                    dtype='float'
                ) * 1.0e-3
                Vch.append(volts)

        # 4) Build AllTraces proto
        all_traces_msg = AllTraces()
        ts_proto = self.timestamp_now()

        idx = 1  # index into Vch: Vch[1] corresponds to first active channel
        for channel in self.channels:
            if channel.is_active():
                trace_proto = Trace()
                trace_proto.channel_idx = channel.channel_idx
                trace_proto.timestamp.CopyFrom(ts_proto)
                # sample_interval in seconds (time_interval_ns * 1e-9)
                trace_proto.sample_interval = float(self.time_interval_ns) * 1.0e-9
                # We store the waveform as a repeated field of doubles (one per sample)
                trace_proto.values.extend(Vch[idx].tolist())
                idx += 1
                all_traces_msg.traces.append(trace_proto)

        # 5) Hand off to asyncio side
        if (self.loop is not None) and (self.queue is not None):
            self.loop.call_soon_threadsafe(self.queue.put_nowait, all_traces_msg)

    async def stream_traces(self, message: Empty) -> AsyncIterator[AllTraces]:
        """
        - Set up self.loop and self.queue
        - Create the C‐callback pointer exactly once
        - Repeatedly: start block, await queue.get(), yield it.
        """
        self.logger.info("Starting Block‐Mode Trace Stream!")

        # 1) Grab the current asyncio loop and create our queue
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()

        # 2) Build the C‐callable function pointer for block_ready_callback
        #    (so PicoSDK will invoke self.block_ready_callback)
        self.cFuncPtr = ps.BlockReadyType(self.block_ready_callback)

        # 3) Continuously start a new block, wait for it, yield it
        try:
            while True:
                # Kick off one block capture. As soon as it finishes, block_ready_callback will enqueue data.
                self.util_run_block()

                # Wait until block_ready_callback pushes into self.queue
                all_traces_msg: AllTraces = await self.queue.get()

                # Yield the newly‐acquired block
                yield all_traces_msg

                # Loop around: the next iteration will re‐trigger util_run_block()
        finally:
            # If the consumer cancels or the server shuts down, ensure we stop the scope
            try:
                ps.ps5000aStop(self.chandle)
                ps.ps5000aCloseUnit(self.chandle)
            except Exception:
                pass


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("TESTING Picoscope 5444DMSO Utils")

    config = Config()
    logger.info(config.valid_scale_names)
    logger.info(config.valid_scales)

    # Example usage of configure_channel
    async def run_configure_channel():
        channel_request = ChannelRequest(
            channel_idx=0,
            activate = True,
            trace_resolution_bits = 8,
            channel_coupling = 0,  # 0 for DC, 1 for AC
            channel_voltage_scale = config.valid_scales[9],
            analog_offset_volts = 0.0,  # No offset
        )
        response = await config.configure_channel(channel_request)
        logger.info(response)

    asyncio.run(run_configure_channel())

    # Example usage of configure_trigger
    async def run_configure_trigger():
        trigger_config = TriggerConfig(
            trigger_channel_idx = 0,
            trigger_type = 0,  # 0 for ABOVE
            trigger_level_volts = 0.5,  # Trigger level in volts
            trigger_holdoff_ns = 0,
        )
        response = await config.configure_trigger(trigger_config)
        logger.info(response)

    asyncio.run(run_configure_trigger())

    # Example usage of configure_timebase
    async def run_configure_timebase():
        timebase_request = TimebaseRequest(
            timebase_idx = 3,
            n_samples_pre_trigger = 0,
            n_samples_post_trigger = 1000,
        )
        response = await config.configure_timebase(timebase_request)
        logger.info(response)
    asyncio.run(run_configure_timebase())

    # Example usage of stream_traces (block mode)
    streamer = StreamAllTraces()

    async def run_stream():
        async for traces in streamer.stream_traces(Empty()):
            logger.info(f"Received block with {len(traces.traces)} channels.")
            for tr in traces.traces:
                logger.info(f"  Channel {tr.channel_idx}: {len(tr.values)} samples @ {tr.sample_interval}s")

    asyncio.run(run_stream())  # Uncomment once you have the timebase & channels set up

