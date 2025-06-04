import asyncio
from h2pcontrol.h2pcontrol_connector import H2PControl
from delta300.delta_elektronica import (
    DeviceIdnRequest,
    DeviceIdnResponse,
    DeviceVoltageRequest,
    DeviceVoltageResponse,
    DeltaElektronicaServiceStub,
)

async def main():
    print("Trying to connect...")
    h2pcontroller = H2PControl("192.168.5.6:50051", None)
    await h2pcontroller.connect()
    print("Connected!")
    print(h2pcontroller.servers)
    channel, server = await h2pcontroller.register_server(h2pcontroller.servers.delta_elektronica, DeltaElektronicaServiceStub) # type: ignore
    stub = DeltaElektronicaServiceStub(channel) # type: ignore
    print(channel, server)
    request = DeviceIdnRequest(port = " ")
    result = await stub.get_device_idn(request)
    print(result.identification)



if __name__ == '__main__':
    asyncio.run(main())