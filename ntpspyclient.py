import socket
import logging
import time
import zlib
from ntpdatagram import NTPdatagram
from ntpspymessage import NTPspyFunction, NTPspyMessage, NTPspyStatus
from timestampgen import UNIX_TO_NTP

formatter = logging.Formatter(
    fmt='%(asctime)s - %(levelname)s - %(name)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logconsole = logging.StreamHandler()
logconsole.setLevel(logging.DEBUG)
logconsole.setFormatter(formatter)

class NTPspyClient:
    def __init__(self, remote="localhost", port=1234, magic_number=0xDEADBEEF, timeout=5, verbose=False, version=3, session_id=None, interval=0):
        self.verbose = verbose
        self.server_addr = (remote, port)
        self.timeout = timeout
        self.magic_number = magic_number
        self.version = version
        self.session_id = session_id
        self.max_retry = 5
        self.progress_interval = 10 # seconds, between progress messages
        self.interval = interval # delay between transmissions (seconds)

        self.logger = logging.getLogger(type(self).__name__)
        self.logger.addHandler(logconsole)
        self.set_loglevel(logging.DEBUG if verbose else logging.INFO)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)
        self.logger.info(f"Client socket initialized for {self.server_addr}")

    def send_ntp(self, ntp_msg: NTPdatagram) -> NTPdatagram:
        try:
            ntp_msg.xmt_whole = int(time.time()) + UNIX_TO_NTP
            self.sock.sendto(ntp_msg.to_bytes(), self.server_addr)

            data, addr = self.sock.recvfrom(1024)
            response = NTPdatagram.from_bytes(data)
            return response
        except socket.timeout:
            self.logger.error("Timeout waiting for response.")
            return None

    def send_ntpspy(self, spy_msg: NTPspyMessage):
        ntp_msg = spy_msg.to_ntp()
        reply = self.send_ntp(ntp_msg)
        if not reply:
            self.logger.error("No response from server.")
            return None
        if reply.is_ntpspy(self.magic_number):
            return NTPspyMessage.from_ntp(reply)
        else:
            self.logger.error("Received non-NTPspy response.")
            return None

    def close(self):
        self.sock.close()
        self.logger.info("Client socket closed.")

    def transfer_file(self, filepath: str):
        """upload local file to by filename"""
        self.logger.info(f"Reading transfer source: {filepath}")
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
        except Exception as e:
            self.logger.error(e)
            return False
        filename = filepath.split('/')[-1]
        try:
            self.transfer_session(data, filename)
        except KeyboardInterrupt:
            self.logger.warning("Transfer interrupted.")
            if self.session_id:
                self.logger.info(f"Sending abort message for session: {self.session_id}")
                self.abort(self.session_id)
            return False
        return True
    
    def transfer_session(self, data: bytes, filename: str = None):
        """upload data block in chunks with optional name"""
        start_time = time.time()
        if len(data) == 0:
            self.logger.warning("No data to transfer. Aborting.")
            return False
        self.logger.info(f"Transferring {_readable_size(len(data))} of data with name: '{filename}'")

        # 1) verify presence of NTPspy and matching version
        if not self.check_server_version(self.version):
            self.logger.error("Server in blocked state or wrong version. Aborting transfer.")
            return False
                # 2) request new session ID if not manually assigned
        storage_required = len(data) + (len(filename) if filename else 0)
        self.session_id = self.get_session_id(storage_required)
        if not self.session_id:
            self.logger.error("Failed to obtain session ID. Aborting transfer.")
            return False
        # 3) transfer filename in chunks
        if filename:
            filename_bytes = filename.encode()
            filename_crc = zlib.crc32(filename_bytes)
            self.logger.info(f"Session: {self.session_id} - Transferring filename: '{filename}' ({len(filename_bytes)} bytes)")
            if not self.transfer_data(self.session_id, filename_bytes, NTPspyFunction.XFER_TEXT):
                return False
            # 3.b) verify filename integrity
            if not self.verify(self.session_id, NTPspyFunction.CHECK_TEXT, filename_crc):
                self.logger.error("Filename verification failed. Aborting transfer.")
                return False
            self.logger.info("Filename verification passed.")            
        # 4) transfer data in chunks
        length = len(data)
        self.logger.info(f"Session: {self.session_id} - Transferring {length} bytes with name: '{filename}'")
        if not self.transfer_data(self.session_id, data, NTPspyFunction.XFER_DATA):
            self.logger.error("Data transfer failed. Aborting transfer.")
            self.abort(self.session_id)
            return False
        # 5) verify data integrity
        data_crc = zlib.crc32(data)
        if not self.verify(self.session_id, NTPspyFunction.CHECK_DATA, data_crc):
            self.logger.error("Data verification failed. Aborting transfer.")
            self.abort(self.session_id)
            return False
        # 6) finalize session
        if not self.rename(self.session_id):
            self.logger.error(f"Failed to rename file. Check server temporary store for session: {self.session_id}")
            return False

        current_time = time.time()
        total_transfer_size = len(data) + (len(filename) if filename else 0)
        elapsed_time = current_time - start_time
        transfer_rate = total_transfer_size / elapsed_time
        self.logger.info(f"Session complete - {_readable_size(total_transfer_size)} in {elapsed_time:.2f} secs ({transfer_rate:.2f} B/s)")
        self.session_id = None
        return True

    def transfer_data(self, session_id: int, data: bytes, type: NTPspyFunction) -> bool:
        """transfer block of data (or text) in chunks"""
        chunk_size = 4  # bytes
        chunk_count = len(data) // chunk_size
        current_time = last_progress = time.time()
        for sequence, offset in enumerate(range(0, len(data), chunk_size)):
            chunk = data[offset:offset + chunk_size]
            if not self.transfer_chunk(session_id, type, sequence, chunk, len(chunk), chunk_count):
                self.logger.error(f"Session {session_id} Failed to {type.name} chunk {sequence}. Aborting transfer.")
                self.abort(session_id)
                return False
            if self.interval > 0:
                time.sleep(self.interval)
            current_time = time.time()
            if current_time - last_progress >= self.progress_interval:
                progress = (sequence + 1) / chunk_count * 100
                self.logger.info(f"Session: {self.session_id} - Progress: {progress:.2f}% ({sequence + 1}/{chunk_count})")
                last_progress = current_time
        self.logger.info(f"Session: {session_id} - {type.name} transfer completed")
        return True

    def probe(self):
        """query server for NTPspy presence and version"""
        self.logger.info(f"Sending probe message to the server. Magic: 0x{self.magic_number:X}, Version: {self.version}")
        msg = NTPspyMessage(
            function=NTPspyFunction.PROBE, 
            magic=self.magic_number, 
            version=self.version
        )
        return self.send_ntpspy(msg)

    def check_server_version(self, local_version: int) -> bool:
        """check server version"""
        probe = self.probe()
        if not probe:
            self.logger.error("No response from server.")
            return False
        self.logger.debug(probe)
        if probe.status == NTPspyStatus.ERROR or probe.status == NTPspyStatus.FATAL_ERROR:
            self.logger.error("Server in error state.")
            return False
        remote_version = probe.version
        if local_version != remote_version:
            self.logger.error(f"Version mismatch. Client: {local_version}, Server: {remote_version}")
            return False
        self.logger.debug(f"Version check passed. Client: {local_version}, Server: {remote_version}")
        return True

    def get_session_id(self, storage_required: int) -> int:
        session_request = NTPspyMessage(
            function=NTPspyFunction.NEW_SESSION,
            magic=self.magic_number,
            session_id=0,
            payload=storage_required,
        )
        for attempt in range(self.max_retry):
            self.logger.info(f"Requesting new session ID. Attempt {attempt + 1}/{self.max_retry}")
            response = self.send_ntpspy(session_request)
            if response and response.status != NTPspyStatus.FATAL_ERROR:
                new_session = response.session_id
                self.logger.info(f"Received session ID: {new_session:x}")
                return new_session
            self.logger.warning("Failed to obtain session ID. Retrying...")
        self.logger.error("Exceeded maximum retries. Server denied session request.")
        return None


    def transfer_chunk(self, session_id: int, type: NTPspyFunction, sequence: int, data: bytes, length: int, chunkcount: int):
        """upload single chunk, data or text, to server"""
        msg = NTPspyMessage(
            status = type,
            function = type,
            magic = self.magic_number,
            session_id = session_id,
            sequence_number = sequence,
            payload = data[:length],
            length = len(data)
        )
        for attempt in range(self.max_retry):
            self.logger.debug(f"Session: {session_id} Chunk: {sequence}/{chunkcount} Attempt: {attempt + 1}/{self.max_retry} Data: {data}")
            response = self.send_ntpspy(msg)
            if not response:
                self.logger.warning(f"No response from server for chunk {sequence}. Retrying...")
                continue  # Retry on no response
            if response.status == NTPspyStatus.FATAL_ERROR:
                self.logger.error(f"Server returned fatal error for chunk {sequence}. Aborting transfer.")
                return False  # Abort on server error
            return True
        self.logger.error(f"Failed to transfer chunk {sequence} for session {session_id}.")
        return False

    def verify(self, session_id: int, type: NTPspyFunction, expected_crc: int):
        """verify filename integrity"""
        request = NTPspyMessage(
            function=type,
            magic=self.magic_number,
            session_id=session_id,
            payload=expected_crc.to_bytes(4, 'big')
        )
        for attempt in range(self.max_retry):
            self.logger.info(f"Session: {session_id} - {type.name} - Attempt CRC check: {expected_crc:08x}")
            response = self.send_ntpspy(request)

            if not response:
                self.logger.error("No response from server.")
                continue
            if response.status == NTPspyStatus.ERROR:
                self.logger.error("Server in error state. Retrying.")
                continue
            if response.status == NTPspyStatus.FATAL_ERROR:
                self.logger.error("Server reported fatal error.")
                return False
            if response.payload != expected_crc:
                self.logger.error(f"CRC failure. Expected: {expected_crc:x}, Received: {response.payload:x}")
                return False
            else:
                self.logger.info(f"{type.name} passed for session: {session_id}")
                return True
        self.logger.error(f"{type.name} Failed to verify session {session_id}")
        return False

    def rename(self, session_id):
        """instruct server to rename file and finalize session"""
        msg = NTPspyMessage(
            function=NTPspyFunction.RENAME, 
            magic=self.magic_number, 
            session_id=session_id
        )
        for attempt in range(self.max_retry):
            self.logger.info(f"Sending rename message for session ID: {session_id}. Attempt {attempt + 1}/{self.max_retry}")
            response = self.send_ntpspy(msg)
            if response:
                if response.status == NTPspyStatus.NORMAL:
                    self.logger.info(f"File renamed successfully for session ID: {session_id}.")
                    return True
                elif response.status == NTPspyStatus.ERROR:
                    self.logger.error("Server reported error. File already exists?")
                    self.abort(session_id)
                    return False
            self.logger.warning("Rename attempt failed. Retrying...")
        self.logger.error(f"Failed to rename file after {self.max_retry} attempts for session ID: {session_id}.")
        return False

    def abort(self, session_id: int):
        """notify server to discontinue and purge session"""
        if not self.session_id:
            self.logger.error("No session ID assigned. Nothing to abort")
            return False
        self.logger.info(f"Sending abort request for session: {session_id}.")
        request = NTPspyMessage(
            function=NTPspyFunction.ABORT,
            magic=self.magic_number,
            session_id=session_id
        )
        response = self.send_ntpspy(request)
        self.session_id = None
        if not response:
            self.logger.error("No response from server.")
            return False
        if response.status == NTPspyStatus.ERROR:
            self.logger.error("Server failed to confirm abort. Invalid session id?")
            return False
        if response.status == NTPspyStatus.NORMAL:
            self.logger.info(f"Server acknowledged abort message for session {session_id}.")
            return True

    def set_loglevel(self, level):
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)

def _readable_size(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            fmt_size = f"{size}" if isinstance(size, int) else f"{size:.2f}"
            fmt_size = int(float(fmt_size)) if fmt_size.endswith('.00') else fmt_size
            return f"{fmt_size} {unit}"
        size /= 1024
    fmt_size = size if isinstance(size, int) else f"{size:.2f}"
    return f"{fmt_size} GB"

if __name__ == "__main__":
    client = NTPspyClient()
