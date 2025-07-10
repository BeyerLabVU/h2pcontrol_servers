import argparse
import asyncio
import logging
import signal
import sys

import tomllib
from grpclib.server import Server

from lioptec_server.lioptec import (
    LioptecServiceBase,
    IsOk,
    LaserRequest,
    WavelengthRequest,
    Empty,
)
import re
import socket

class LioptecService(LioptecServiceBase):
    def __init__(self):
        super().__init__()
        self.socket = None  # Placeholder for the socket connection
        self.connection_ok = False
        self.wavelength = None
        # NOTE: In very specific cases, checking if the current resonator position is equal to the last resonator position
        # will not actually give the correct result as to whether the laser has finished tuning.
        # We will ignore these edge cases, which are extremely unlikely to show up in practice.  They would require the user to either:
        # a) switch directions for incrementing the wavelength
        # b) poll to check if the laser is ready at the same instant that a new wavelength is requested
        self.last_resonator_position = None

    async def Connect(self, request: LaserRequest):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((request.ip, request.port))
        except socket.error as e:
            return IsOk(ok=False, status=f"Connection failed: {e}")
        self.socket.sendall(b"RemoteConnect\r\n")
        data = self.socket.recv(1024)
        print(data.decode())
        self.connection_ok = (b'OK' in data)
        return IsOk(ok=self.connection_ok, status=data)
    

    async def Disconnect(self, request: Empty):
        if not self.connection_ok:
            return IsOk(ok=False, status="Not connected in the first place")
        
        self.socket.sendall(b"RemoteDisconnect\r\n") # type: ignore
        data = self.socket.recv(1024) # type: ignore
        print(data.decode())
        return IsOk(ok=(b'OK' in data), status=data)
        

    async def SetWavelength(self, request: WavelengthRequest):
        if not self.connection_ok:
            return IsOk(ok=False, status="Not connected")
        
        self.socket.sendall(f"SetWavelength {request.wavelength}\r\n".encode("utf-8")) # type: ignore
        data = self.socket.recv(1024) # type: ignore
        print(data.decode())
        wavelength_ok = (b'OK' in data)
        if wavelength_ok:
            self.wavelength = request.wavelength
        else:
            self.wavelength = None
        return IsOk(ok=wavelength_ok, status=data)
    
    async def IsReady(self, request: Empty):
        if not self.connection_ok:
            return IsOk(ok=False, status="Not connected")
        if self.wavelength is None:
            return IsOk(ok=False, status="Wavelength not set")
        
        # Ask for the current resonator position
        self.socket.sendall(b"GetActualPosition\r\n") # type: ignore
        data = self.socket.recv(1024) # type: ignore
        match = re.search(r'Resonator: (\d+)', data.decode())
        if match:
            resonator = int(match.group(1))
            if resonator == self.last_resonator_position:
                self.last_resonator_position = resonator
                return IsOk(ok=True, status="Ready")
            else:
                self.last_resonator_position = resonator
                return IsOk(ok=False, status="Not ready, resonator moving")


async def main(port_override=None):
    # Replace this list with your actual service implementations
    server = Server([])

    # We gather the port from the h2pcontrol.server.toml file by default, if we can not get that port we take a default port.
    port = port_override or configuration.get("port", 50052)
    await server.start("127.0.0.1", port)

    logger.info(f"Server started on 127.0.0.1:{port}")

    # Use an asyncio Event to wait for shutdown signal
    should_stop = asyncio.Event()

    # To gracefully handle shutdown
    def _signal_handler():
        logger.info("Shutdown signal received.")
        should_stop.set()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)
    else:
        signal.signal(signal.SIGINT, lambda s, f: _signal_handler())
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, lambda s, f: _signal_handler())

    await should_stop.wait()

    logger.info("Shutting down server...")
    server.close()
    await server.wait_closed()
    logger.info("Server shutdown complete.")


# Default logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

with open("h2pcontrol.server.toml", "rb") as f:
    config = tomllib.load(f)
configuration = config.get("configuration", {})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the gRPC server")
    parser.add_argument("--port", type=int, help="Port number to listen on")
    args = parser.parse_args()

    asyncio.run(main(args.port))
