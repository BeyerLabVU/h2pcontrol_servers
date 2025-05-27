"""
### BEGIN NODE INFO
[info]
name = Oscilloscope DS1054Z
version = 0.1
description = For interfacing with Rigol DS1054Z using tcp/ip

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

from ds1054z import DS1054Z

import numpy as np
import tempfile

class DS1054Z_oscope_server(LabradServer):
    """Server for interfacing with Rigol DS1054Z oscilloscope via tcp/ip"""
    name = 'DS1054Z'

    def initServer(self):
        self.valid_timebase_scales \
            = self.generate_valid_timebase_scales()
        self.valid_voltage_scales \
            = self.generate_valid_voltage_scales()

    def stopServer(self):
        pass

    @setting(1, ip = 's')
    def set_device_ip(self, c, ip):
        self.scope = DS1054Z(ip)
        print(f'Device identity @{ip}: {self.scope.idn}')

    @setting(2, lock = 'b')
    def keylock(self, c, lock):
        if lock:
            lck = "ON"
        else:
            lck = "OFF"
        self.scope.write(f":SYSTEM:LOCKED {lck}")

    @setting(3)
    def reset(self, c):
        self.scope.write("*RST")

    # =======================================================================================
    # Reading/setting trigger settings
    # Assume that we are always using an edge trigger

    @setting(11, returns = 'v[]')
    def read_trigger_level(self, c):
        return float(self.scope.query(":TRIGGER:EDGE:LEVEL?"))

    @setting(21)
    def write_trigger_level(self, c, level):
        return self.scope.write(f":TRIGGER:EDGE:LEVEL "\
            + f"{np.format_float_scientific(level, precision = 6)}")

    @setting(12, returns = 's')
    def read_trigger_edge_slope(self, c):
        return self.scope.query(":TRIGGER:EDGE:SLOPE?")

    @setting(22, slope = 's')
    def write_trigger_edge_slope(self, c, slope):
        if not (slope in ("POS", "NEG", "RFAL")):
            raise Exception("DS1054Z server: invalid trigger slope")
        self.scope.write(f":TRIGGER:EDGE:SLOPE "\
            + f"{slope}")

    @setting(13, returns = 's')
    def read_trigger_channel(self, c):
        return self.scope.query(":TRIGGER:EDGE:SOURCE?")

    @setting(23, channel = 'i')
    def write_trigger_channel(self, c, channel):
        if not (channel in (1, 2, 3, 4)):
            raise Exception("DS1054Z server: invalid channel")
        self.scope.write(f":TRIGGER:EDGE:SOURCE CHAN{channel}")

    @setting(24, mode = 's')
    def write_trigger_mode(self, c, mode):
        if not (mode.upper() in ("AUTO", "NORM", "SING")):
            raise Exception("DS1054Z server: invalid trigger mode")
        self.scope.write(f"TRIGGER:SWEEP {mode.upper()}")

    @setting(25)
    def force_trigger(self, c):
        self.scope.write(":TFORCE")

    @setting(26)
    def run(self, c):
        self.scope.write(":RUN")

    @setting(27)
    def stop(self, c):
        self.scope.write(":STOP")

    # =======================================================================================
    # Reading/setting timebase settings

    def util_read_timebase_scale(self):
        return float(self.scope.query(":TIMEBASE:MAIN:SCALE?"))

    @setting(31, returns = ['v[]'])
    def read_timebase_scale(self, c):
        return self.util_read_timebase_scale()

    def generate_valid_timebase_scales(self):
        scales = []
        first_digits = [5, 10, 20]
        magnitudes = list(range(-9, 2))
        for fd in first_digits:
            for mag in magnitudes:
                scales.append(fd * (10**mag))
        return np.sort(scales)

    @setting(101, returns = '*v[]')
    def valid_timebase_scales(self, c):
        return self.valid_timebase_scales

    @setting(41, scale = 'v[]')
    def write_timebase_scale(self, c, scale):
        if not (scale in self.valid_timebase_scales):
            raise Exception("DS1054Z server: invalid timebase scale")
        self.scope.write(f"TIMEBASE:MAIN:SCALE {scale}")

    def util_read_timebase_offset(self):
        return float(self.scope.query(":TIMEBASE:MAIN:OFFSET?"))

    @setting(32, returns = 'v[]')
    def read_timebase_offset(self, c):
        return self.util_read_timebase_offset()

    @setting(42, offset = 'v[]')
    def write_timebase_offset(self, c, offset):
        self.scope.write(f":TIMEBASE:MAIN:OFFSET {offset}")

    def util_read_sampling_rate(self):
        return float(self.scope.query(":ACQUIRE:SRATE?"))

    @setting(33, returns = 'v[]')
    def read_sampling_rate(self, c):
        return self.util_read_sampling_rate()

    @setting(34, returns = 'v[]')
    def read_memory_depth(self, c):
        memdepth = self.scope.query(":ACQUIRE:MDEPTH?")
        if memdepth == 'AUTO':
            memdepth = '0'
        return float(memdepth)

    # =======================================================================================
    # Reading/setting channel settings

    @setting(51, channel = 'i', returns = 's')
    def read_channel_coupling(self, c, channel):
        if not (channel in (1, 2, 3, 4)):
            raise Exception("DS1054Z server: invalid channel")
        return self.scope.query(f":CHANNEL{channel}:COUPLING?")

    @setting(61, channel = 'i', coupling = 's')
    def write_channel_coupling(self, c, channel, coupling):
        if not (channel in (1, 2, 3, 4)):
            raise Exception("DS1054Z server: invalid channel")
        if not (coupling in ("AC", "DC", "GND")):
            raise Exception("DS1054Z server: invalid coupling")
        self.scope.write(f":CHANNEL{channel}:COUPLING {coupling}")

    @setting(52, channel = 'i', returns = 's')
    def read_channel_display(self, c, channel):
        if not (channel in (1, 2, 3, 4)):
            raise Exception("DS1054Z server: invalid channel")
        return self.scope.query(f":CHANNEL{channel}:DISPLAY?")

    @setting(62, channel = 'i', display = 'b')
    def write_channel_display(self, c, channel, display):
        if not (channel in (1, 2, 3, 4)):
            raise Exception("DS1054Z server: invalid channel")
        if display:
            disp = "1"
        else:
            disp = "0"
        self.scope.write(f":CHANNEL{channel}:DISPLAY {disp}")

    @setting(53, channel = 'i', returns = 'v[]')
    def read_channel_offset(self, c, channel):
        if not (channel in (1, 2, 3, 4)):
            raise Exception("DS1054Z server: invalid channel")
        return float(self.scope.query(f":CHANNEL{channel}:OFFSET?"))

    @setting(63, channel = 'i', offset = 'v[]')
    def write_channel_offset(self, c, channel, offset):
        if not (channel in (1, 2, 3, 4)):
            raise Exception("DS1054Z server: invalid channel")
        self.scope.write(f":CHANNEL{channel}:OFFSET "\
            + f"{np.format_float_scientific(offset, precision = 6)}")

    def generate_valid_voltage_scales(self):
        scales = []
        first_digits = [1, 2, 5]
        magnitudes = list(range(-3, 1))
        for fd in first_digits:
            for mag in magnitudes:
                scales.append(fd * (10**mag))
        scales.append(10)
        return np.sort(scales)

    @setting(102, returns = '*v[]')
    def valid_voltage_scales(self, c):
        return self.valid_voltage_scales

    @setting(54, channel = 'i', returns = 'v[]')
    def read_channel_range(self, c, channel):
        if not (channel in (1, 2, 3, 4)):
            raise Exception("DS1054Z server: invalid channel")
        return float(self.scope.query(f":CHANNEL{channel}:RANGE?"))

    @setting(64, channel = 'i', scale = 'v[]')
    def write_channel_range(self, c, channel, scale):
        if not (channel in (1, 2, 3, 4)):
            raise Exception("DS1054Z server: invalid channel")
        self.scope.write(f":CHANNEL{channel}:PROBE 1")
        self.scope.write(f":CHANNEL{channel}:SCALE {scale}")
            # + f"{np.format_float_scientific(scale, precision = 6)}")

    # =======================================================================================
    # Retrieving traces from the oscilloscope, saving

    def util_read_waveform_samples(self, channel):
        # voltages = self.scope.get_waveform_samples(channel)
        # self.scope.write(f":WAVEFORM:SOURCE CHANNEL{channel}")
        raw = self.scope.query_raw(f":WAVEFORM:DATA?")
        raw = raw[11:-1]
        voltages = np.frombuffer(raw, dtype = np.uint8)
        times = np.arange(len(voltages)) / self.util_read_sampling_rate()
        return np.vstack((times, voltages))

    @setting(70, channel = 'i', returns = '*2v[]')
    def read_waveform_samples(self, c, channel):
        return self.util_read_waveform_samples(channel)

    def encode_data_numpy_to_bytes(self, numpy_array):
        send = tempfile.TemporaryFile()
        np.savez_compressed(send, data = numpy_array)
        send.seek(0)
        return send.read()

    @setting(80, channel = 'i', name = 's', description = 's')
    def send_waveform_to_storage(self, c, channel, name, description):
        self.client.data_saver.add_data_item(name, description, 
            self.encode_data_numpy_to_bytes(
                self.util_read_waveform_samples(channel)))

# create an instance of our server class
__server__ = DS1054Z_oscope_server()

# this is some boilerplate code to run the
# server when this module is executed
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)