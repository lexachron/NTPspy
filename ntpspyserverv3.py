import asyncio
import threading
import logging
import sys

from ntpdatagram import NTPdatagram
from ntpspymessage import NTPspyMessage
# from storageprovider import FileStorageProvider # TODO
# from timestampgen import TimestampGenerator # TODO

class NTPspyServer(asyncio.DatagramProtocol):
    def __init__(self, host="0.0.0.0", port=1234, magic_number=0xDEADBEEF, storage_provider=None, verbose=False):
        self.host = host
        self.port = port
        self.magic_number = magic_number
        self.transport = None
        self.incoming_queue = asyncio.Queue()
        self.outgoing_queue = asyncio.Queue()
        self.storage_provider = storage_provider # or FileStorageProvider() # TODO
        self.running = False
        self.loop = None
        self.logger = logging.getLogger("__name__")
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        self.interactive = sys.flags.interactive


    def start_background(self):
        """start server in background thread, keeping the REPL free."""
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_event_loop, daemon=True).start()

    def _run_event_loop(self):
        """run asyncio event loop in a separate thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.start()) 
        self.loop.run_forever()

    def stop(self):
        """shutdown background event loop"""
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.logger.info("Server shutdown")

    async def start(self):
        """normal server start"""
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(lambda: self, local_addr=(self.host, self.port))
        asyncio.create_task(self._transmit_loop())
        self.logger.info(f"NTPspy Server started on {self.host}:{self.port}")
        if not self.interactive:
            asyncio.create_task(self._dispatch_loop())

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        """enqueue incoming UDP packets"""
        try:
            ntp_packet = NTPdatagram.from_bytes(data)
            self.incoming_queue.put_nowait((ntp_packet, addr))
            self.logger.debug(f"Received {len(data)} bytes from {addr}")
        except ValueError:
            pass  # ignore malformed packets

    async def _transmit_loop(self):
        """auto send outgoing packets"""
        while True:
            response, addr = await self.outgoing_queue.get()
            self.transport.sendto(response.to_bytes(), addr)

    async def _dispatch_loop(self):
        """process incoming packets automatically (disable in REPL mode)"""
        while self.running:
            await self.dispatch_one()

    async def dispatch_one(self):
        """process single packet"""
        if not self.incoming_queue.empty():
            ntp_packet, addr = await self.incoming_queue.get()
            response = self.handle_packet(ntp_packet)
            self.outgoing_queue.put_nowait((response, addr))

    def handle_packet(self, ntp):
        """process all packets as NTP, then as NTPspy only if detected"""
        ntp_reply = self.handle_ntp_request(ntp)
        
        if ntp.is_ntpspy(self.magic_number):
            spy = NTPspyMessage.from_ntp(ntp)
            spy_reply = self.handle_ntpspy_message(spy) 
            ntp_reply = spy_reply.to_ntp(ntp_reply) 
        
        return ntp_reply 

    def handle_ntpspy_message(self, msg: NTPspyMessage) -> NTPspyMessage:
        """dispatch NTPspy message to appropriate function handler"""
        # TODO define a enum class for the function numbers
        #if msg.function == 0:
        #    return self.function_query(msg)
        #if msg.function == 1:  
        #    self.storage_provider.write_chunk(msg.session_id, msg.sequence_number, msg.payload.to_bytes(4, 'big'))
        #if msg.function == 2:
        #    return self.function_verify(msg)
        return NTPspyMessage(status=0, function=msg.function, session_id=msg.session_id)  # Placeholder 

    def handle_ntp_request(self, datagram: NTPdatagram) -> NTPdatagram:
        """process standard NTP fields IAW RFC 1305"""
        reply = datagram
        reply.mode = NTPdatagram.MODE_SERVER
        return reply  

    def purge_queues(self):
        self.incoming_queue = asyncio.Queue()
        self.outgoing_queue = asyncio.Queue()

    def dump_queue(self):
        print(f"Incoming: {self.incoming_queue.qsize()} packets")
        print(f"Outgoing: {self.outgoing_queue.qsize()} packets")
