import asyncio
from h2pcontrol.h2pcontrol_connector import H2PControl
from ps5444DMSO.picoscope_5444DMSO import (
    Empty, StreamAllTracesStub, 
)

async def main():
    print("Trying to connect...")
    h2pcontroller = H2PControl("127.0.0.1:50051")
    await h2pcontroller.connect()
    print("Connected to server successfully")
    channel, server = await h2pcontroller.register_server(h2pcontroller.servers.picoscope_5444DMSO, StreamAllTracesStub) # type: ignore
    print(channel, server)
    empty = Empty()
    # SEE MODIFIED STUB
    stub = StreamAllTracesStub(channel)
    async for trace in stub.stream_traces(empty):
        print(trace)


if __name__ == '__main__':
    asyncio.run(main())