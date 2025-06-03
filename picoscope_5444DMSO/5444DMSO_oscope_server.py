"""
### BEGIN NODE INFO
[info]
name = Oscilloscope Picoscope 5444D MSO
version = 0.1
description = For interfacing with Picoscope 5444D MSO using USB3

[startup]
cmdline = %PYTHON% %FILE%
timeout = 20

[shutdown]
message = 987654321
timeout = 20
### END NODE INFO
"""

from labrad.server import LabradServer
from labrad.server import setting

import ctypes
import numpy as np
from picosdk.ps5000a import ps5000a as ps
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc
from picosdk.constants import PICO_STATUS

from si_prefix import si_format

from datetime import datetime

import numpy as np
import tempfile

from time import sleep
import threading

from enum import Enum
import json

class osci_channel():
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

class PS5444DMSO_oscope_server(LabradServer):
    """Server for interfacing with Picoscope 5444D MSO oscilloscope via tcp/ip"""
    name = 'PS5444DMSO'

    def initServer(self):
        self.valid_voltage_scale_names, self.valid_voltage_scales \
            = self.util_generate_valid_voltage_scales()

        # Open 5000 series PicoScope
        # Resolution set to 12 Bit
        self.resolution = ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_8BIT"]
        self.open_picoscope()

        self.maxADC = ctypes.c_int16()
        self.status["maximumValue"] = ps.ps5000aMaximumValue(self.chandle, ctypes.byref(self.maxADC))
        assert_pico_ok(self.status["maximumValue"])
        
        print("Picoscope connected.")

        self.running = False
        self.next_tag = 'notag';

        self.save_data = False
        self.last_waveform_shared = False
        self.Vch = []

        self.repeat = False

        self.stop_repeat = threading.Event()
        self.callback_repeat = threading.Event()
        self.settings_changed = threading.Event()
        self.settings_changed.set()
        self.loop_thread = threading.Thread(target = self.loop_in_thread, args=())

        self.last_trigger = datetime.now()

        self.tagging_enum = Enum('tag state', [('NO_TAG', 0), ('TAG_READY', 1), ('WAVEFORM_TAGGED', 2), ('WAVEFORM_NOT_SENT', 3), ('TAG_EXPIRED', 4)])
        self.tag_state = self.tagging_enum.NO_TAG
        self.tag = ''

        # Initialize oscilloscope channel settings recording
        self.channels = [osci_channel(idx) for idx in range(4)]

        self.preTriggerSamples = 0

    def open_picoscope(self):
        # Create chandle and status ready for use
        self.chandle = ctypes.c_int16()
        self.status = {}
        # Returns handle to chandle for use in future API functions
        self.status["openunit"] = ps.ps5000aOpenUnit(ctypes.byref(self.chandle), None, self.resolution)
        # Open Picoscope and configure the power source
        try:
            assert_pico_ok(self.status["openunit"])
            print("External power source available.")
        except: # PicoNotOkError:
            print("WARNING: Picoscope powered by USB")
            self.powerStatus = self.status["openunit"]

            if self.powerStatus == 286:
                self.status["changePowerSource"] = ps.ps5000aChangePowerSource(self.chandle, self.powerStatus)
            elif self.powerStatus == 282:
                self.status["changePowerSource"] = ps.ps5000aChangePowerSource(self.chandle, self.powerStatus)
            else:
                raise
            assert_pico_ok(self.status["changePowerSource"])

    def stopServer(self):
        if self.repeat:
            self.util_stop_loop(reopen = False)
        if self.loop_thread.is_alive():
            print("Waiting loop thread join.")
            self.loop_thread.join()
            print("Loop thread gracefully killed.")
        ps.ps5000aCloseUnit(self.chandle)
        print("Picoscope disconnected.")

    def util_generate_valid_voltage_scales(self):
        idx = -1
        valid_scale_names = []
        valid_scales = []
        for exponent in [1, 2, 3, 4]:
            for first_digit in [1, 2, 5]:
                idx += 1
                channel_range = first_digit * (10**(exponent - 3))
                valid_scales.append(channel_range)
                valid_scale_names.append(f'+/-{si_format(channel_range)}V : {list(ps.PS5000A_RANGE.keys())[idx]}')
        return valid_scale_names, valid_scales

    def util_timebase_sampling_rate_8bit(self, n):
        if n < 0 or n > (2**32 - 1):
            raise Exception("Invalid timebase input")
        elif n < 3:
            return (2**n) / 1.0e+9
        else:
            return (n - 2) / 1.25e+8

    def timebase_sampling_rate_12bit(n):
        if n < 1 or n > (2**32 - 1):
            raise Exception("Invalid timebase input")
        elif n < 4:
            return 2**(n - 1) / 5.0e+8
        else:
            return (n - 3) / 62.5e+6

    @setting(4, n = 'i', returns = 'v[]')
    def timebase_sampling_rate_8bit(self, c, n):
        return self.util_timebase_sampling_rate_8bit(n)

    @setting(5, n = 'i', returns = 'v[]')
    def timebase_sampling_rate_12bit(self, c, n):
        return self.util_timebase_sampling_rate_12bit(n)

    @setting(6, returns = 's')
    def valid_voltage_scale_names(self, c):
        return ','.join(self.valid_voltage_scale_names)

    @setting(96, returns = 'y')
    def valid_voltage_scales(self, c):
        return self.encode_data_numpy_to_bytes(np.array(self.valid_voltage_scales))

    def wait_to_update_settings(self):
        self.settings_changed.clear()
        if self.running:
            self.callback_repeat.wait()

    def done_updating_settings(self):
        self.settings_changed.set()


    @setting(7, resolution = 'i')
    def set_scope_resolution(self, c, resolution):
        if not self.running and not self.repeat:
            if resolution not in (8, 12, 14):
                raise Exception("Picoscope server: Unknown or unimplemented scope resolution specification")
            if resolution == 8:
                self.resolution = ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_8BIT"]
            elif resolution == 12:
                self.resolution = ps.PS5000A_DEVICE_RESOLUTION["PS5000A_DR_12BIT"]
            ps.ps5000aCloseUnit(self.chandle)
            self.open_picoscope()
            self.maxADC = ctypes.c_int16()
            self.status["maximumValue"] = ps.ps5000aMaximumValue(self.chandle, ctypes.byref(self.maxADC))
            assert_pico_ok(self.status["maximumValue"])

    @setting(8, channel_idx = 'i', range_idx = 'i', coupling_type = 's')
    def set_active_channel(self, c, channel_idx, range_idx, coupling_type):
        self.wait_to_update_settings()
        if coupling_type not in ("AC", "DC"):
            raise Exception("Picoscope server: unrecognized channel coupling type specification")
        if coupling_type == 'AC':
            coupling = ps.PS5000A_COUPLING['PS5000A_AC']
        else:
            coupling = ps.PS5000A_COUPLING['PS5000A_DC']
        if channel_idx < 0 or channel_idx > 3:
            raise Exception("Picoscope server: unrecognized channel specification")
        self.status["setActiveChannel"] = ps.ps5000aSetChannel(
            self.chandle, 
            channel_idx, 
            1, 
            coupling, 
            range_idx, 
            0
        )
        assert_pico_ok(self.status["setActiveChannel"])
        self.channels[channel_idx].activate_channel(range_idx, coupling_type)
        self.done_updating_settings()

    @setting(28, channel_idx = 'i')
    def deactivate_channel(self, c, channel_idx):
        self.wait_to_update_settings()
        if channel_idx < 0 or channel_idx > 3:
            raise Exception("Picoscope server: unrecognized channel specification")
        self.status["DeactivateChannel"] = ps.ps5000aSetChannel(
            self.chandle, 
            channel_idx, 
            1, 
            0, 
            0, 
            0
        )
        assert_pico_ok(self.status["DeactivateChannel"])
        self.channels[channel_idx].deactivate_channel()
        self.done_updating_settings()

    @setting(9, timebase = 'i', n_samples = 'i')
    def set_timebase(self, c, timebase, n_samples):
        self.wait_to_update_settings()
        print(f"Setting timebase {timebase}, {n_samples} samples")
        self.timebase = int(timebase)
        timeIntervalns = ctypes.c_int32()
        returnedMaxSamples = ctypes.c_int32()
        self.n_samples = int(n_samples)
        self.status["getTimebase2"] = ps.ps5000aGetTimebase(self.chandle, self.timebase, self.n_samples, ctypes.byref(timeIntervalns), ctypes.byref(returnedMaxSamples), 0)
        print("NEW TIMEBASE: sample interval: %.3g ns, max returned samples %d" % (timeIntervalns.value, returnedMaxSamples.value))
        self.time_interval_ns = float(timeIntervalns.value)
        assert_pico_ok(self.status["getTimebase2"])
        self.done_updating_settings()

    @setting(10, trigger_channel = 'i', threshold_V = 'v[]', direction = 's', holdoff = 'i')
    def set_trigger(self, c, trigger_channel, threshold_V, direction, holdoff):
        self.wait_to_update_settings()
        if direction.upper() == 'RISING':
            dr = 2
        elif direction.upper() == 'FALLING':
            dr = 3
        else:
            raise Exception("Picoscope server: unrecognized trigger mode")
        if holdoff < 0:
            raise Exception("Picoscope server: holdoff must not be negative")
        threshold_ADC = int(mV2adc(threshold_V * 1.0e+3, self.channels[trigger_channel].read_range_idx(), self.maxADC))
        print('Trigger level readback: ', adc2mV([threshold_ADC], self.channels[trigger_channel].read_range_idx(), self.maxADC))
        self.status["trigger"] = ps.ps5000aSetSimpleTrigger(self.chandle, 1, trigger_channel, threshold_ADC, dr, holdoff, 200)
        assert_pico_ok(self.status["trigger"])
        self.done_updating_settings()

    def encode_data_numpy_to_bytes(self, numpy_array):
        send = tempfile.TemporaryFile()
        np.savez_compressed(send, data = numpy_array)
        send.seek(0)
        return send.read()

    @setting(50, preTriggerSamples = 'i')
    def set_pre_trigger_samples(self, c, preTriggerSamples):
        self.preTriggerSamples = preTriggerSamples

    def util_run_block(self, tag):
        if not self.running:
            self.next_tag = tag
            postTriggerSamples = self.n_samples - self.preTriggerSamples
            # Prep the callback function
            self.cFuncPtr = ps.BlockReadyType(self.block_ready_callback)
            # Run the block
            self.running = True
            self.status["runBlock"] = ps.ps5000aRunBlock(self.chandle, self.preTriggerSamples, postTriggerSamples, self.timebase, None, 0, self.cFuncPtr, None)
            assert_pico_ok(self.status["runBlock"])
            if not self.repeat:
                print("Block dispatched.")
        else:
            print("Block initiated while already running")

    @setting(11, tag = 's')
    def run_block(self, c, tag):
        self.util_run_block(tag)

    @setting(12)
    def run_loop(self, c):
        self.repeat = True
        # ps.ps5000aStop(self.chandle)
        print(f"Starting continuous run, {si_format(int(self.n_samples))} samples, timebase {self.timebase}")
        self.stop_repeat.clear()
        print(threading.enumerate())
        if self.loop_thread.is_alive():
            print("Waiting loop thread join.")
            self.loop_thread.join()
            print("Loop thread gracefully killed.")
        self.loop_thread = threading.Thread(target = self.loop_in_thread, args=())
        self.loop_thread.start()
        print("Loop thread alive: ", self.loop_thread.is_alive(), flush = True)

    def loop_in_thread(self):
        print("Loop thread initiated.", flush = True)
        while not self.stop_repeat.is_set():
            self.util_run_block("continuous run")
            now = datetime.now()
            # print(f"Callback wait.  Elapsed since trigger: {now - self.last_trigger}", flush = True)
            self.last_trigger = now
            self.callback_repeat.wait()
            self.callback_repeat.clear()
            self.settings_changed.wait()
        if self.stop_repeat.is_set():
            print("Received stop_repeat signal", flush = True)

    @setting(13)
    def stop_loop(self, c):
        self.util_stop_loop()

    # reopen param: deprecate?
    def util_stop_loop(self,  reopen = True):
        self.repeat = False
        self.stop_repeat.set()
        self.callback_repeat.set()
        print("Stop loop!")
        if self.loop_thread.is_alive():
            print("Waiting loop thread join.")
            self.loop_thread.join()
            print("Loop thread gracefully killed.")

    def block_ready_callback(self, handle, statusCallback, param):
        waveform_timestamp = datetime.now().strftime('%H_%M_%S_%f')
        if not self.repeat:
            print("Block callback")
        if statusCallback == PICO_STATUS['PICO_CANCELLED']:
            print("Picoscope block capture cancelled")
        else:
            # Read off the data, send it to the data saver server
            trace_dict1 = {}
            trace_dict2 = {}
            for channel in self.channels:
                if channel.is_active():
                    # First, prepare the buffer for the data
                    trace_dict1[channel] = (ctypes.c_int16 * self.n_samples)()
                    trace_dict2[channel] = (ctypes.c_int16 * self.n_samples)()
                    self.status["setDataBuffers"] = ps.ps5000aSetDataBuffers(
                        self.chandle, 
                        channel.channel_idx, 
                        ctypes.byref(trace_dict1[channel]), 
                        ctypes.byref(trace_dict2[channel]), 
                        self.n_samples, 
                        0, 
                        0
                    )
                    assert_pico_ok(self.status["setDataBuffers"])
            # Read off the data
            # create overflow loaction
            overflow = ctypes.c_int16()
            # create converted type maxSamples
            cmaxSamples = ctypes.c_int32(self.n_samples)
            self.status["getValues"] = ps.ps5000aGetValues(self.chandle, 0, ctypes.byref(cmaxSamples), 0, 0, 0, ctypes.byref(overflow))
            count = 0
            if self.status["getValues"] == PICO_STATUS["PICO_NOT_RESPONDING"]:
                print("PICOSCOPE CRASH DETECTED")
                self.last_waveform_shared = True
                self.tag_state = self.tagging_enum.TAG_EXPIRED
                print("Closing...")
                ps.ps5000aCloseUnit(self.chandle)
                print("Reopening...")
                self.open_picoscope()
            else:
                assert_pico_ok(self.status["getValues"])
                time = np.linspace(0.0, float((self.n_samples - 1) * self.time_interval_ns) * 1.0e-9, self.n_samples)
                self.Vch = [time]
                for channel in self.channels:
                    if channel.is_active():
                        # Convert it to human readable units
                        self.Vch.append(np.array(adc2mV(trace_dict1[channel], channel.read_range_idx(), self.maxADC), dtype = 'float') * 1.0e-3)

                if self.save_data:
                    # Send it to the data saver!
                    self.client.data_saver.add_data_item(f"picoscope_trace__ch{channel}_tag_{self.next_tag}_{waveform_timestamp}", 
                                                          "no description for now.  add later.", 
                                                          self.encode_data_numpy_to_bytes(np.vstack(self.Vch)))
                    print("Data sent to data_saver")

                self.last_waveform_shared = False
                self.running = False
                if self.tag_state == self.tagging_enum.WAVEFORM_TAGGED or self.tag_state == self.tagging_enum.WAVEFORM_NOT_SENT:
                    self.tag_state = self.tagging_enum.TAG_EXPIRED
                elif self.tag_state == self.tagging_enum.TAG_READY:
                    self.tag_info["timestamp"] = waveform_timestamp
                    self.tag = json.dumps(self.tag_info)
                    self.tag_state = self.tagging_enum.WAVEFORM_TAGGED

        if self.repeat:
            # print("Callback repeat")
            self.callback_repeat.set()

    @setting(21, rid = 'i', sweep_param = 'v[]')
    def tag_next(self, c, rid, sweep_param):
        if self.repeat:
            # Prep the info for the waveform tag.  The tag is finalized on the block callback, where the timestamp is added
            self.tag_info = {'RID': rid, 'SweepParam': sweep_param}
            # print(f"Tag received: RID {rid}, SweepParam {sweep_param}")
            if self.tag_state == self.tagging_enum.WAVEFORM_TAGGED:
                self.tag_state = self.tagging_enum.WAVEFORM_NOT_SENT
            else:
                self.tag_state = self.tagging_enum.TAG_READY

    @setting(22, returns = 'b')
    def new_waveform_available(self, c):
        available = (not self.last_waveform_shared) and (len(self.Vch) > 1)
        self.last_waveform_shared = True
        return available

    @setting(23, returns = 'y')
    def send_latest_waveform(self, c):
        self.last_waveform_shared = True
        if self.running:
            self.tag_state = self.tagging_enum.TAG_EXPIRED
            return self.encode_data_numpy_to_bytes(np.vstack(self.Vch))
        else:
            return b'NONE'

    @setting(24, returns = '(is)')
    def send_tag(self, c):
        if self.tag_state == self.tagging_enum.WAVEFORM_NOT_SENT:
            return self.tagging_enum.WAVEFORM_TAGGED.value, self.tag
        return self.tag_state.value, self.tag

# create an instance of our server class
__server__ = PS5444DMSO_oscope_server()

# this is some boilerplate code to run the
# server when this module is executed
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)