import asyncio
import sys
import logging

from ntpdatagram import NTPdatagram, NTPmode
from ntpspymessage import NTPspyMessage

_DEFAULT = {
    "port": 1234,
    "magic": 0xDEADBEEF,
    "path": "./",
}

class NTPspyServer(asyncio.DatagramProtocol):
    def __init__(self, port=_DEFAULT["port"], magic=_DEFAULT["magic"], path=_DEFAULT["path"], verbose=False):
        self.interactive = sys.flags.interactive 
        self.transport = None
        self.incoming_queue = asyncio.Queue()
        self.outgoing_queue = asyncio.Queue()
        self.running = False
        self.mode = NTPmode.SERVER
        self.port = port
        self.magic = magic
        self.path = path
        self.verbose = verbose

    async def start(self):
        loop = asyncio.get_running_loop()
        try:
            await loop.create_datagram_endpoint(
                lambda: self, local_addr=("0.0.0.0", self.port)
            )
            self.running = True
            print(f"NTPspy Server started on {self.port}")
        except OSError as e:
            print(f"Failed to bind to port {self.port}: {e}")
            return
        asyncio.create_task(self.process_incoming())
        asyncio.create_task(self.process_outgoing())

    def connection_made(self, transport):
        print(f"Transport initialized: {transport}")
        self.transport = transport

    def datagram_received(self, data, addr):
        print(f"Received {len(data)} bytes from {addr}")
        self.incoming_queue.put_nowait((data, addr))

    async def process_incoming(self):
        print("process_incoming task started")
        while self.running:
            data, addr = await self.incoming_queue.get()

            try:
                ntp_msg = NTPdatagram.from_bytes(data)
            except ValueError as e:
                print(f"Invalid NTP message from {addr}: {e}")
                continue

            if ntp_msg.is_ntpspy(self.magic):
                spy_msg = NTPspyMessage.from_ntp(ntp_msg)
                if self.verbose:
                    print(f"Received NTPspy message from {addr}: {vars(spy_msg)}")
                response = self.handle_ntpspy(spy_msg)
                self.outgoing_queue.put_nowait((response, addr))
            else:
                if self.verbose:
                    print(f"Received standard NTP message from {addr}: {vars(ntp_msg)}")

    async def process_outgoing(self):
        print("process_outgoing task started")
        while self.running:
            response, addr = await self.outgoing_queue.get()
            if response is None:
                break
            self.transport.sendto(response.to_bytes(), addr)

    def handle_ntpspy(self, spy_msg):
        response = NTPspyMessage(
            status=0, function=spy_msg.function, version=spy_msg.version,
            magic=self.magic, session_id=spy_msg.session_id,
            sequence_number=spy_msg.sequence_number + 1, payload=0, length=0
        )
        return response.to_ntp()

    def stop(self):
        self.running = False
        self.outgoing_queue.put_nowait((None, None))
        if self.transport:
            self.transport.close()
        print("Server stopped.")

# Only runs if executed directly, not in REPL or when imported
if __name__ == "__main__" and not sys.flags.interactive:
    async def main():
        server = NTPspyServer()
        await server.start()
        while server.running:  
            try:
                await asyncio.sleep(1)
            except KeyboardInterrupt:
                server.stop()

    asyncio.run(main())

# REPL mode (debug/testing)
if sys.flags.interactive:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("\nEvent loop initialized.")
    print("To start the server, use: loop.run_until_complete(server.start())")