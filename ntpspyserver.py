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
    def __init__(self, path, host=None, port=None, magic_number=None, storage_provider=None, verbose=0, version=2, timestampgen=None, allow_overwrite=False):
        self.host = host or "0.0.0.0"
        self.port = port or 1234
        self.magic_number = magic_number or 0xdeadbeef
        self.path = path or "."
        self.version = version
        self.killswitch = False
        self.allow_overwrite = allow_overwrite
        self.transport = None

        self.running = True if not sys.flags.interactive else False
        self.loop = None
        self.logger = logging.getLogger(type(self).__name__)
        self.logger.addHandler(logconsole)
        self.storage_provider = storage_provider or DiskStorageProvider(path)
        self.storage_provider.logger.addHandler(logconsole)
        self.timestampgen = timestampgen or OperationalTimestampGenerator()
        self.set_verbose(verbose)

    def handle_packet(self, ntp):
        """process all packets as NTP, then as NTPspy only if magic num detected"""
        ntp_reply = self.handle_ntp_request(ntp)
        if ntp.is_ntpspy(self.magic_number):
            spy = NTPspyMessage.from_ntp(ntp)
            spy_reply = self.handle_ntpspy_message(spy) 
            ntp_reply = spy_reply.to_ntp(ntp_reply) 
        return ntp_reply 

    def handle_ntp_request(self, datagram: NTPdatagram) -> NTPdatagram:
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

    def handle_ntpspy_message(self, msg: NTPspyMessage) -> NTPspyMessage:
        """dispatch NTPspy message to appropriate function handler"""
        if self.killswitch:
            reply = msg
            reply.status = NTPspyStatus.ERROR
            return reply
        match msg.function:
            case NTPspyFunction.PROBE:
                return self.probe(msg)
            case NTPspyFunction.XFER_DATA:
                return self.transfer_data(msg)
            case NTPspyFunction.CHECK_DATA:
                return self.verify_data(msg)
            case NTPspyFunction.XFER_TEXT:
                return self.transfer_text(msg)
            case NTPspyFunction.CHECK_TEXT:
                return self.verify_text(msg)
            case NTPspyFunction.RENAME:
                return self.rename(msg)
            case NTPspyFunction.ABORT:
                return self.abort(msg)
            case _:
                return NTPspyMessage(status=NTPspyStatus.FATAL_ERROR)  # cease fire

    def probe(self, msg: NTPspyMessage) -> NTPspyMessage:
        """handle version query"""
        self.logger.info(f"Handling version probe. Client: {msg.version}, Server: {self.version}")
        reply = msg
        reply.version = self.version
        return reply
    
    def transfer_data(self, msg: NTPspyMessage) -> NTPspyMessage:
        """handle file transfer"""
        reply = msg
        if msg.session_id == 0:
            # allocate new session
            session_id = self.storage_provider.allocate_session()
            reply.session_id = session_id
            self.logger.info(f"Sending new session ID: {session_id:x}")
        else:
            # write data to existing session
            data_bytes = msg.payload.to_bytes(4, byteorder='big')[:msg.length]
            self.logger.debug(f"Writing data to session ID: {msg.session_id}, seq: {msg.sequence_number}, len: {msg.length}, data: {data_bytes}")
            try:
                self.storage_provider.write(BufferType.DATA, msg.session_id, msg.sequence_number, data_bytes)
                self.logger.debug(f"Data written to session ID: {msg.session_id}, sequence: {msg.sequence_number}")
            except ValueError:
                reply.status = NTPspyStatus.ERROR
                self.logger.error(f"Failed to write data to session ID: {msg.session_id}")

        return reply

    def verify_data(self, msg: NTPspyMessage) -> NTPspyMessage:
        """handle checksum verification"""
        self.logger.info(f"Verifying data for session ID: {msg.session_id}")
        reply = msg
        try:
            checksum = self.storage_provider.check(BufferType.DATA, msg.session_id)
            if checksum != msg.payload:
                reply.status = NTPspyStatus.ERROR
                self.logger.warning(f"CRC failed for session: {msg.session_id}, expected: {msg.payload:x}, actual: {checksum:x}")
            reply.payload = checksum
            self.logger.info(f"CRC match for session: {msg.session_id}: {checksum:x}")
        except ValueError:
            reply.status = NTPspyStatus.ERROR
            self.logger.error(f"Failed to verify data for session ID: {msg.session_id}")
            reply.payload = reply.length = 0
        return reply

    def transfer_text(self, msg: NTPspyMessage) -> NTPspyMessage:
        """handle text transfer"""
        self.logger.debug(f"Handling text transfer for session ID: {msg.session_id}")
        reply = msg
        if msg.session_id == 0:  # invalid session ID
            reply.status = NTPspyStatus.ERROR
            self.logger.error("Invalid session ID for text transfer")
            return reply
        else:
            # write text to existing session
            try:
                text_bytes = msg.payload.to_bytes(4, byteorder='big')[:msg.length]
                self.storage_provider.write(BufferType.TEXT, msg.session_id, msg.sequence_number, text_bytes)
                self.logger.debug(f"Text written to session ID: {msg.session_id:x}, sequence: {msg.sequence_number}")
            except ValueError:
                reply.status = NTPspyStatus.ERROR
                self.logger.error(f"Failed to write text to session ID: {msg.session_id:x}")
        return reply

    def verify_text(self, msg: NTPspyMessage) -> NTPspyMessage:
        """handle text verification"""
        self.logger.info(f"Verifying text for session ID: {msg.session_id:x}")
        reply = msg

        try:
            text_checksum = self.storage_provider.check(BufferType.TEXT, msg.session_id)
            if text_checksum != msg.payload:
                reply.status = NTPspyStatus.ERROR
                self.logger.warning(f"CRC failed for session: {msg.session_id}, expected: {text_checksum:x}, actual: {msg.payload:x}")
            reply.data = text_checksum
            self.logger.info(f"CRC match for session: {msg.session_id}: {text_checksum:x}")
        except ValueError:
            reply.status = NTPspyStatus.ERROR
            self.logger.error(f"Failed to verify text for session ID: {msg.session_id:x}")
            reply.data = reply.length = 0
        return reply

    def rename(self, msg: NTPspyMessage) -> NTPspyMessage:
        """handle file rename"""
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
        """Shutdown background event loop."""
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
        """cancel all tasks pending tasks"""
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
        try:
            ntp_packet = NTPdatagram.from_bytes(data)
            self.incoming_queue.put_nowait((ntp_packet, addr))
            #self.logger.debug(f"Received {len(data)} bytes from {addr}")
        except ValueError:
            pass  # ignore malformed packets

    async def _transmit_loop(self):
        """auto send outgoing packets"""
        while True:
            response, addr = await self.outgoing_queue.get()
            self.transport.sendto(response.to_bytes(), addr)

    async def _dispatch_loop(self):
        """process incoming packets automatically (disable in REPL mode)"""
        while True:
            if self.running:
                await self.dispatch_one()
            await asyncio.sleep(0.01)

    async def dispatch_one(self):
        """process single packet"""
        if not self.incoming_queue.empty():
            ntp_packet, addr = await self.incoming_queue.get()
            response = self.handle_packet(ntp_packet)
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
    server = NTPspyServer(".")
    server.start_background()
    server.running = True
    server.set_verbose(1)
    