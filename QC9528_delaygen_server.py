"""
### BEGIN NODE INFO
[info]
name = Delay Generator QC9528
version = 0.1
description = For interfacing with Quantum Composers 9528 delay generators via RS232

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

import serial
import io

import numpy as np


class QC9528_delaygen_server(LabradServer):
    """Server for interfacing with Quantum Composers 9528 delay generators via RS232"""
    name = 'QC9528'

    def command(self, scpi_command):
        """ Send command over SCPI """
        message = f'{scpi_command}\r\n'
        print(f"Sending {repr(message)}")
        self.ser.write(message)

    def query(self, scpi_query):
        """ Send command and return the received response """
        self.command(scpi_query)
        reply = self.ser.readline()
        print(f"Reply   {repr(reply)}")
        return reply

    # Server startup and shutdown
    #
    # these functions are called after we first connect to
    # LabRAD and before disconnecting.  Here you should perform
    # any global initialization or cleanup.
    def initServer(self):
        self.channel_dict = {
            'A' : 1,
            'B' : 2,
            'C' : 3,
            'D' : 4,
            'E' : 5,
            'F' : 6,
            'G' : 7,
            'H' : 8,
        }

    def stopServer(self):
        try:
            self.ser_port.close()
        except:
            pass

    @setting(1, path='s')
    def set_device_path(self, c, path):
        self.usb_device_path = path
        self.ser_port = serial.Serial(self.usb_device_path, baudrate = 115200, timeout=0.1)
        self.ser = io.TextIOWrapper(\
            io.BufferedRWPair(self.ser_port, self.ser_port, 1), \
            newline='\r\n', \
            line_buffering = True)
        if not self.ser_port.is_open:
            raise Exception("QC9528 server: Could not make connection")

        # Check that the connection is working, and that we have the right device
        self.ser.write('*IDN?\n')
        reply = self.ser.readline()
        print(f'Device identity @{self.usb_device_path}: {repr(reply)}')
        assert('QC,9528' in reply)

    def update_display(self):
        self.query(":DISP:UPDATE?")

    @setting(21)
    def reset(self, c):
        """ Reset the delay generator to default settings """
        self.query("*RST")
        self.update_display()

    def channel_to_int(self, channel):
        try:
            return self.channel_dict[channel.upper()]
        except:
            raise Exception('QC9528 server: invalid channel input')

    # =======================================================================================
    # Reading settings of the channels

    @setting(31, channel = 's', returns = 'b')
    def read_channel_enabled(self, c, channel):
        """ Is the channel enabled? """
        return self.query(f":PULSe{self.channel_to_int(channel)}:STATE?") == '1\r\n'

    @setting(32, channel = 's', returns = 'v[]')
    def read_channel_delay(self, c, channel):
        reply = self.query(f":PULSe{self.channel_to_int(channel)}:DELAY?")
        return float(reply[:-2])

    @setting(33, channel = 's', returns = 'v[]')
    def read_channel_width(self, c, channel):
        reply = self.query(f":PULSe{self.channel_to_int(channel)}:WIDTH?")
        return float(reply[:-2])

    @setting(34, channel = 's', returns = 's')
    def read_channel_sync(self, c, channel):
        reply = self.query(f":PULSe{self.channel_to_int(channel)}:SYNC?")
        return reply[:-2]

    @setting(35, channel = 's', returns = 's')
    def read_channel_polarity(self, c, channel):
        reply = self.query(f":PULSe{self.channel_to_int(channel)}:POLARITY?")
        return reply[:-2]

    @setting(36, channel = 's', returns = 'v[]')
    def read_channel_electrical_output(self, c, channel):
        output_type_reply = self.query(f":PULSe{self.channel_to_int(channel)}:OUTPUT:MODE?")
        if output_type_reply[:-2] == 'TTL':
            return 0.0
        reply = self.query(f":PULSe{self.channel_to_int(channel)}:OUTPUT:AMPLITUDE?")
        return float(reply[:-2])

    # =======================================================================================
    # Writing settings of the channels

    @setting(41, channel = 's', enabled = 'b')
    def write_channel_enabled(self, c, channel, enabled):
        if enabled:
            state = "ON"
        else:
            state = "OFF"
        self.query(f":PULSe{self.channel_to_int(channel)}:STATE {state}")

    @setting(42, channel = 's', delay = 'v[]')
    def write_channel_delay(self, c, channel, delay):
        reply = self.query(f":PULSe{self.channel_to_int(channel)}:DELAY " \
                            + np.format_float_scientific(delay, precision=6))

    @setting(43, channel = 's', width = 'v[]')
    def write_channel_width(self, c, channel, width):
        reply = self.query(f":PULSe{self.channel_to_int(channel)}:WIDTH " \
                            + np.format_float_scientific(width, precision=6))

    @setting(44, channel = 's', sync_channel = 's')
    def write_channel_sync(self, c, channel, sync_channel):
        if sync_channel.upper() == 'T0':
            sync = 'T0'
        else:
            # If this line runs fine, we have a valid channel.
            self.channel_to_int(sync_channel)
            # We need to pass a string
            sync = 'CH' + sync_channel.upper()
        # The channel being synced follows the same format as usual        
        channel_to_sync = self.channel_to_int(channel)
        # Send the message
        self.query(f":PULSe{channel_to_sync}:SYNC {sync}")

    @setting(45, channel = 's', polarity = 's')
    def write_channel_polarity(self, c, channel, polarity):
        # 'INVERTED' and 'COMPLEMENT' are aliases of the same idea:
        #       the channel starts high as the default state and pulses low.
        if polarity.upper() in ('NORMAL', 'COMPLEMENT', 'INVERTED'):
            reply = self.query(f":PULSe{self.channel_to_int(channel)}:POLARITY " \
                                + polarity.upper())
        else:
            raise Exception("QC9528 server: invalid polarity input")

    @setting(46, channel = 's', amplitude = 'v[]')
    def write_channel_electrical_output(self, c, channel, amplitude):
        """ 
            Choose the type of output from the channel.
            If amplitude = 0.0, standard TTL output.
            For anything else, variable amplitude output, range from 2.0 to 20V 
        """
        if amplitude == 0.0:
            mode = 'TTL'
        else:
            mode = 'ADJUSTABLE'
            if not (amplitude >= 2.0 and amplitude <= 20.0):
                raise Exception("QC9528 server: invalid amplitude input")
        self.query(f":PULSe{self.channel_to_int(channel)}:OUTPUT:MODE {mode}")
        self.query(f":PULSe{self.channel_to_int(channel)}:OUTPUT:AMPLITUDE {amplitude}")

    # =======================================================================================
    # Triggering, running, stopping

    @setting(50)
    def set_burst(self, c):
        ''' Set up burst mode so that the DG triggers once every TTL pulse from the ARTIQ '''
        self.query(":PULSE0:MODE BURST")
        self.query(":PULSE0:BCOUNTER 1")

    @setting(51)
    def run(self, c):
        self.query(":INST:STATE ON")

    @setting(52)
    def stop(self, c):
        self.query(":INST:STATE OFF")

    @setting(53, returns = 'b')
    def is_running(self, c):
        return self.query(":INST:STATE?") == '1\r\n'

    @setting(54, enable = 'b', edge = 's', level = 'v[]')
    def configure_trigger(self, c, enable, edge = "RISING", level = 2.5):
        if enable:
            mode = "TRIG"
        else:
            mode = "DIS"
        if not edge.upper() in ("RISING", "FALLING"):
            raise Exception("QC9528 server: invalid trigger edge specification")
        if not (level >= 0.2 and level <= 15.0):
            raise Exception("QC9528 server: invalid trigger threshold level input")
        self.query(f":PULSE0:TRIGGER:MODE {mode}")
        self.query(f":PULSE0:TRIGGER:EDGE {edge.upper()}")
        self.query(f":PULSE0:TRIGGER:LEVEL {np.format_float_scientific(level, precision=6)}")

    @setting(55, returns = 'b')
    def is_trigger_enabled(self, c):
        return self.query(f":PULSE0:TRIGGER:MODE?") == 'TRIG\r\n'

    @setting(56, returns = 's')
    def read_edge_type(self, c):
        reply = self.query(":PULSE0:TRIGGER:EDGE?")
        if reply[:-2] == "RIS":
            edge = "RISING"
        elif reply[:-2] == "FALL":
            edge = "FALLING"
        else:
            raise Exception("QC9528 server: couldn't parse edge type.")
        return edge

    @setting(57, returns = 'v[]')
    def read_trigger_level(self, c):
        reply = self.query(":PULSE0:TRIGGER:LEVEL?")
        return float(reply[:-2])

    # =======================================================================================
    # Other utilities

    @setting(60, lock='b')
    def keylock(self, c, lock):
        if lock:
            state = "1"
        else:
            state = "0"
        self.query(f":SYSTEM:KLOCK {state}")

# create an instance of our server class
__server__ = QC9528_delaygen_server()

# this is some boilerplate code to run the
# server when this module is executed
if __name__ == '__main__':
    from labrad import util
    util.runServer(__server__)