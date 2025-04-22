import asyncio
import threading
import logging
import sys
import copy
import signal

from ntpdatagram import NTPdatagram, NTPmode
from ntpspymessage import NTPspyMessage, NTPspyFunction, NTPspyStatus
from timestampgen import OperationalTimestampGenerator
from storageprovider import DiskStorageProvider, MemoryStorageProvider, BufferType, StorageError, FatalStorageError

formatter = logging.Formatter(
    fmt='%(asctime)s - %(levelname)s - %(name)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logconsole = logging.StreamHandler()
logconsole.setLevel(logging.DEBUG)
logconsole.setFormatter(formatter)

class NTPspyServer(asyncio.DatagramProtocol):
    def __init__(self, path=None, host=None, port=None, magic_number=None, storage_provider=None, verbose=0, version=3, timestampgen=None, allow_overwrite=False):
        self.host = host or "0.0.0.0"
        self.port = port or 1234
        self.magic_number = magic_number or 0xdeadbeef
        self.path = path or "."
        self.version = version
        # temporarily reject all new sessions, cause client to abort current sessions
        self.blocked = False
        # if overwrite disabled, storage provider either silently renames or fails on name collision
        self.allow_overwrite = allow_overwrite
        self.transport = None

        # automatic processing incoming/outgoing message queues
        self.running = True if not sys.flags.interactive else False
        self.loop = None

        self.logger = logging.getLogger(type(self).__name__)
        self.logger.addHandler(logconsole)
        self.storage_provider = storage_provider or DiskStorageProvider(path)
        self.storage_provider.logger.addHandler(logconsole)
        self.timestampgen = timestampgen or OperationalTimestampGenerator()
        self.set_verbose(verbose)

    def handle_datagram(self, datagram, addr):
        """discard non-ntp traffic, process rest as ntp, then ntpspy if applicable"""
        client = addr[0]
        try:
            ntp_in = NTPdatagram.from_bytes(datagram)
        except ValueError:
            self.logger.debug(f"{client}: Dropped non-ntp datagram")
            return None
        ntp_out = self.handle_ntp(ntp_in, addr)
        if ntp_in.is_ntpspy(self.magic_number):
            try:
                spy_in = NTPspyMessage.from_ntp(ntp_in)
            except ValueError:
                self.logger.error(f"{client}: Invalid NTPspy message")
            spy_out = self.handle_ntpspy(spy_in, addr)
            ntp_out = spy_out.to_ntp(ntp_out)
        return ntp_out


    def handle_ntp(self, datagram: NTPdatagram, addr) -> NTPdatagram:
        """simulate NTP server response, ref: RFC 1305"""
        reply = copy.copy(datagram)
        reply.mode = NTPmode.SERVER
        reply.stratum = 15
        reply.poll = 0  # 2^0 = 1 second
        reply.precision = -5  # ~50ms
        reply.rootdelay = 0x1000  # ~1 second
        reply.rootdispersion = 0x1000
        reply.refid = 0x4C4F434C  # 'LOCL' = "undisciplined local clock"
        self.timestampgen.apply_timestamps(datagram, reply)
        return reply  

    def handle_ntpspy(self, msg: NTPspyMessage, addr) -> NTPspyMessage:
        """dispatch NTPspy message to appropriate function handler"""
        if self.blocked:
            reply = msg
            reply.status = NTPspyStatus.FATAL_ERROR
            return reply

        handlers = {
            NTPspyFunction.PROBE: lambda: self.probe(msg, addr),
            NTPspyFunction.NEW_SESSION: lambda: self.session_init(msg, addr),
            NTPspyFunction.XFER_DATA: lambda: self.transfer(msg, BufferType.DATA),
            NTPspyFunction.CHECK_DATA: lambda: self.verify(msg, BufferType.DATA),
            NTPspyFunction.XFER_TEXT: lambda: self.transfer(msg, BufferType.TEXT),
            NTPspyFunction.CHECK_TEXT: lambda: self.verify(msg, BufferType.TEXT),
            NTPspyFunction.RENAME: lambda: self.rename(msg),
            NTPspyFunction.ABORT: lambda: self.abort(msg),
        }

        handler = handlers.get(msg.function)
        if handler:
            return handler()
        else:
            return NTPspyMessage(
                status=NTPspyStatus.FATAL_ERROR,
                version=self.version,
                magic=self.magic_number,
            )  # cease fire
        
    def probe(self, msg: NTPspyMessage, addr) -> NTPspyMessage:
        """handle version query"""
        client = addr[0]
        reply = msg
        reply.version = self.version
        self.logger.info(f"{client}: Handling version probe. Client: {msg.version}, Server: {self.version}, Status: {NTPspyStatus(reply.status).name}")
        return reply
    
    def session_init(self, msg: NTPspyMessage, addr) -> NTPspyMessage:
        """assign new session ID"""
        reply = msg
        storage_required = int(msg.payload)
        client = addr[0]
        self.logger.info(f"{client}: Requested new session for {storage_required:,} bytes")
        if self.blocked:
            reply.status = NTPspyStatus.FATAL_ERROR
            self.logger.warning("Denied new session request while in blocked state")
            return reply
        try:
            new_session = self.storage_provider.allocate_session()
            reply.session_id = new_session
            self.logger.info(f"{client}: Sending new session ID: {new_session:x}")
        except StorageError:
            reply.status = NTPspyStatus.FATAL_ERROR
            self.logger.error(f"Failed to allocate new session ID: {msg.session_id}")
            reply.payload = 0
        return reply

    def transfer(self, msg: NTPspyMessage, type: BufferType) -> NTPspyMessage:
        """handle data or text transfer"""
        reply = msg
        if msg.session_id == 0:
            reply.status = NTPspyStatus.FATAL_ERROR
            self.logger.error("Invalid session ID for transfer")
        else:
            # write data to existing session
            data = msg.payload.to_bytes(4, byteorder='big')[:msg.length]
            self.logger.debug(f"Received {len(data)} bytes {type.value} for session ID: {msg.session_id:x}")
            try:
                self.storage_provider.write(type, msg.session_id, msg.sequence_number, data)
            except ValueError:
                reply.status = NTPspyStatus.ERROR
                self.logger.error(f"Failed to write data to session ID: {msg.session_id}")
        return reply

    def verify(self, msg: NTPspyMessage, type: BufferType) -> NTPspyMessage:
        """handle integrity check"""
        self.logger.info(f"Received {type.value} integrity check for session ID: {msg.session_id:x}")
        reply = msg
        try:
            checksum = self.storage_provider.check(type, msg.session_id)
            if checksum != msg.payload:
                reply.status = NTPspyStatus.ERROR
                self.logger.warning(f"CRC failed for session: {msg.session_id} {type.value}, expected: {msg.payload:x}, actual: {checksum:x}")
            reply.payload = checksum
            self.logger.info(f"CRC match for session: {msg.session_id} {type.value}")
        except ValueError:
            reply.status = NTPspyStatus.FATAL_ERROR
            self.logger.error(f"Failed to verify data for session ID: {msg.session_id}")
            reply.payload = reply.length = 0
        return reply

    def rename(self, msg: NTPspyMessage) -> NTPspyMessage:
        """handle file rename/session finalization"""
        self.logger.info(f"Received rename request for session: {msg.session_id:x}")
        reply = msg

        if msg.session_id == 0:
            reply.status = NTPspyStatus.FATAL_ERROR
            self.logger.error("Invalid session ID for file rename")
            return reply
        try:
            filename = self.storage_provider.finalize_session(msg.session_id, overwrite=self.allow_overwrite)
            self.logger.info(f"Renamed session {msg.session_id:x} to '{filename}'")
            self.storage_provider.delete_session(msg.session_id)
        except FatalStorageError:
            reply.status = NTPspyStatus.ERROR
            self.logger.error(f"Failed to rename file for session ID: {msg.session_id:x}")
            reply.payload = reply.length = 0
        return reply
    
    def abort(self, msg: NTPspyMessage) -> NTPspyMessage:
        """handle session abort request"""
        self.logger.info(f"Received abort for session: {msg.session_id:x}")
        reply = msg

        if msg.session_id == 0:
            reply.status = NTPspyStatus.FATALERROR
            self.logger.error("Invalid session ID for abort")
            return reply

        try:
            self.storage_provider.delete_session(msg.session_id)
            self.logger.info(f"Session ID {msg.session_id:x} purged.")
        except ValueError:
            reply.status = NTPspyStatus.ERROR
            self.logger.error(f"Failed to abort session ID: {msg.session_id:x}")
        return reply

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
            # resolve stop_event future if it exists and not already done
            if hasattr(self, "stop_event") and not self.stop_event.done():
                try:
                    self.logger.debug("Resolving stop_event future...")
                    self.loop.call_soon_threadsafe(self.stop_event.set_result, None)
                except asyncio.InvalidStateError:
                    self.logger.warning("stop_event was already resolved or canceled.")
            if self.transport:
                self.logger.debug("Closing transport...")
                self.loop.call_soon_threadsafe(self.transport.close)
            # allow event loop to process stop_event resolution
            self.loop.call_soon_threadsafe(self._cancel_tasks)

    def _cancel_tasks(self):
        """cancel all pending tasks"""
        tasks = asyncio.all_tasks(self.loop)
        self.logger.debug(f"Cancelling {len(tasks)} pending tasks...")
        for task in tasks:
            task.cancel()
        self.loop.call_soon_threadsafe(self._stop_event_loop)

    def _stop_event_loop(self):
        self.logger.debug("Stopping the event loop...")
        self.loop.stop()

    async def start(self):
        """normal server start"""
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(lambda: self, local_addr=(self.host, self.port))
        self.incoming_queue = asyncio.Queue()
        self.outgoing_queue = asyncio.Queue()
        asyncio.create_task(self._transmit_loop())
        asyncio.create_task(self._dispatch_loop())
        self.logger.info(f"Server started on {self.host}:{self.port}")

        self.stop_event = loop.create_future()
        self.logger.debug("Created stop_event future.")

        def shutdown():
            self.logger.info("Received termination signal.")
            if not self.stop_event.done():
                self.logger.debug("Resolving stop_event future")
                self.stop_event.set_result(None)

        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGINT, lambda sig, frame: shutdown())
                signal.signal(signal.SIGTERM, lambda sig, frame: shutdown())
            except ValueError:
                self.logger.warning("Signal handling is not supported in this context.")

        try:
            await self.stop_event
        except asyncio.CancelledError:
            self.logger.info("Server shutting down.")
        finally:
            self.logger.info("Shutdown complete.")

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        """enqueue incoming UDP packets"""
        self.incoming_queue.put_nowait((data, addr))

    async def _transmit_loop(self):
        """auto send outgoing packets"""
        while True:
            response, addr = await self.outgoing_queue.get()
            self.transport.sendto(response.to_bytes(), addr)

    async def _dispatch_loop(self):
        """process incoming datagrams automatically"""
        while True:
            try:
                if self.running:
                    await self.dispatch_one()
                await asyncio.sleep(0.01)
            except Exception as e:
                self.logger.error(f"Unhandled exception: {e}", exc_info=True)
                break

    async def dispatch_one(self):
        """process single incoming datagram"""
        if not self.incoming_queue.empty():
            datagram, addr = await self.incoming_queue.get()
            response = self.handle_datagram(datagram, addr)
            if response:
                self.outgoing_queue.put_nowait((response, addr))

    def purge_queues(self):
        self.incoming_queue = asyncio.Queue()
        self.outgoing_queue = asyncio.Queue()

    def dump_queue(self):
        print(f"Incoming: {self.incoming_queue.qsize()} packets")
        print(f"Outgoing: {self.outgoing_queue.qsize()} packets")

    def set_verbose(self, level):
        level_config = {
            0: {"server": logging.INFO, "storage": logging.WARNING},
            1: {"server": logging.INFO, "storage": logging.INFO},
            2: {"server": logging.DEBUG, "storage": logging.INFO},
            3: {"server": logging.DEBUG, "storage": logging.DEBUG},
        }
        config = level_config.get(level, level_config[0])
        self.logger.setLevel(config["server"])
        self.storage_provider.logger.setLevel(config["storage"])


if __name__ == "__main__":
    storage = MemoryStorageProvider()
    server = NTPspyServer(storage_provider=storage, verbose=3)
    server.start_background()
    server.running = True

    