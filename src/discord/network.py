import websockets
import asyncio
from aiohttp import ClientSession, TCPConnector, FormData
from zlib import decompressobj

ZLIB_SUFFIX = b"\x00\x00\xff\xff"


class _network:
    """abstract network class"""

    network_se: ClientSession = None

    def __init__(self):
        pass

    @staticmethod
    async def create_session():
        _network.network_se = ClientSession(connector=TCPConnector())


class _websocket:
    """general websocket class"""

    def __init__(self):
        self.inflator = None
        self.buffer = None

    async def _connect(self, uri):
        """create a websocket connection with simple error handlers"""
        self.inflator = decompressobj()
        self.buffer = bytearray()
        async with websockets.connect(
            uri, read_limit=2**512, max_size=2**512
        ) as self.socket:
            while True:
                try:
                    recv = await self.socket.recv()
                    asyncio.create_task(self.on_message(recv))
                except websockets.exceptions.ConnectionClosed as err:
                    await self.err_code_handler(err, uri)
                    break
                except websockets.exceptions.ConnectionClosedOK:
                    print("socket closed normally")
                    break
                except Exception as x:
                    print(x)

    async def err_code_handler(self, err, uri):
        """handle err code properly"""
        pass

    async def disconnect(self):
        pass

    async def on_message(self, msg):
        pass

    async def decode(self, msg):
        """Compress out of zlib and start correct op"""
        self.buffer.extend(msg)
        if len(msg) < 4 or msg[-4:] != ZLIB_SUFFIX:
            return
        msg = self.inflator.decompress(self.buffer)
        self.buffer = bytearray()
        return msg
