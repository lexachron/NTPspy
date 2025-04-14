import socket
import logging
import time
import zlib
from ntpdatagram import NTPdatagram
from ntpspymessage import NTPspyFunction, NTPspyMessage, NTPspyStatus

formatter = logging.Formatter(
    fmt='%(asctime)s - %(levelname)s - %(name)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logconsole = logging.StreamHandler()
logconsole.setLevel(logging.DEBUG)
logconsole.setFormatter(formatter)

class NTPspyClient:
    def __init__(self, remote="127.0.0.1", port=1234, magic_number=0xDEADBEEF, timeout=5, verbose=False, version=2, session_id=None, interval=0):
        self.verbose = verbose
        self.server_addr = (remote, port)
        self.timeout = timeout
        self.magic_number = magic_number
        self.version = version
        self.session_id = session_id
        self.max_retry = 3
        self.interval = interval # delay between transmissions (seconds)

        self.logger = logging.getLogger(type(self).__name__)
        self.logger.addHandler(logconsole)
        self.set_loglevel(logging.DEBUG if verbose else logging.INFO)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)
        self.logger.info(f"Client socket initialized for {self.server_addr}")

    def send_ntp(self, ntp_msg: NTPdatagram) -> NTPdatagram:
        try:
            #self.logger.debug(f"Sending NTPdatagram to {self.server_addr}")
            self.sock.sendto(ntp_msg.to_bytes(), self.server_addr)

            data, addr = self.sock.recvfrom(1024)
            response = NTPdatagram.from_bytes(data)
            #self.logger.debug(f"Received response from {addr}")
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
        """upload local file to server as data block"""
        self.logger.info(f"Reading transfer source: {filepath}")
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
        except Exception as e:
            self.logger.error(e)
            return False
        filename = filepath.split('/')[-1]
        try:
            self.transfer_data(data, filename)
        except KeyboardInterrupt:
            self.logger.warning("Transfer interrupted.")
            if self.session_id:
                self.logger.info("Sending abort message for session: {self.session_id}")
                self.abort(self.session_id)
            return False
        return True
    
    def transfer_data(self, data: bytes, filename: str):
        """upload data block to server in chunks"""
        chunk_size = 4 # bytes
        length = len(data)
        chunkcount = length // chunk_size

        # 1) verify presence of NTPspy and matching version
        probe_response = self.probe()
        if not probe_response:
            self.logger.error("Probe failed.")
            return False
        if probe_response.status == NTPspyStatus.ERROR:
            self.logger.error("Server in error state.")
            return False
        if probe_response.version != self.version:
            self.logger.error(f"Server version mismatch. Client: {self.version}, Server: {probe_response.version}")
            return False
        
        # 2) request new session ID if not manually assigned
        if not self.session_id:
            self.logger.info("Requesting new session ID.")
            session_request = NTPspyMessage(function=NTPspyFunction.XFER_DATA, magic=self.magic_number, session_id=0)
            response = self.send_ntpspy(session_request)
            if response.status == NTPspyStatus.ERROR:
                self.logger.error("Server in error state.")
                return False
            self.session_id = response.session_id
            self.logger.info(f"Received session ID: {self.session_id}")

        # 3) transfer data in chunks
        self.logger.info(f"Session: {self.session_id} - Transferring {length} bytes with name: '{filename}'")
        for sequence, offset in enumerate(range(0, len(data), chunk_size)):
            chunk = data[offset:offset + chunk_size]
            if not self.transfer_chunk(self.session_id, sequence, chunk, len(chunk), chunkcount):
                self.logger.error(f"Session {self.session_id} Failed to transfer chunk {sequence}. Aborting transfer.")
                self.abort(self.session_id)
                return False
            if self.interval > 0:
                time.sleep(self.interval)
        self.logger.info(f"Session: {self.session_id} - Data transfer completed")

        # 4) verify data integrity
        checksum = zlib.crc32(data)
        self.verify_data(self.session_id, checksum)

        # 5) transfer filename in chunks
        filename_bytes = filename.encode('utf-8')
        filename_crc = zlib.crc32(filename_bytes)
        chunkcount = len(filename_bytes) // chunk_size
        for sequence, offset in enumerate(range(0, len(filename_bytes), chunk_size)):
            chunk = filename_bytes[offset:offset + chunk_size]
            if not self.transfer_text(self.session_id, sequence, chunk, len(chunk), chunkcount):
                self.logger.error(f"Session {self.session_id} Failed to transfer chunk {sequence}. Aborting transfer.")
                self.abort(self.session_id)
                return False
            if self.interval > 0:
                time.sleep(self.interval)
        self.logger.info(f"Session: {self.session_id} - Text transfer completed")

        # 6) verify filename integrity
        if not self.verify_text(self.session_id, filename_crc):
            self.logger.error("Filename verification failed. Aborting transfer.")
            return False
        self.logger.info("Filename verification passed.")            

        # 7) finalize session
        self.rename(self.session_id)
        self.session_id = None

    def probe(self):
        """query server for NTPspy presence and version"""
        self.logger.info(f"Sending probe message to the server. Magic: 0x{self.magic_number:X}, Version: {self.version}")
        msg = NTPspyMessage(status=1, function=NTPspyFunction.PROBE, magic=self.magic_number, version=self.version)
        response = self.send_ntpspy(msg)
        if not response:
            self.logger.error("Probe failed.")
            return None
        if response.status == NTPspyStatus.ERROR:
            self.logger.error("Server in error state.")
            return None
        if response.version != self.version:
            self.logger.error(f"Server version mismatch. Client: {self.version}, Server: {response.version}")
        if response.version == self.version:
            self.logger.info(f"Received server reply version: {response.version}.")
        return response

    def transfer_chunk(self, session_id: int, sequence: int, data: bytes, length: int, chunkcount: int, type=NTPspyStatus.NORMAL):
        """upload single data chunk to server"""
        for attempt in range(self.max_retry):
            msg = NTPspyMessage(
                status=type,
                function=NTPspyFunction.XFER_DATA,
                magic=self.magic_number,
                session_id=session_id,
                sequence_number=sequence,
                payload=data[:length],
                length=length
            )
            self.logger.debug(f"Session: {session_id} Chunk: {sequence}/{chunkcount} Attempt: {attempt + 1}/{self.max_retry} Data: {data}")
            response = self.send_ntpspy(msg)
            if not response:
                self.logger.warning(f"No response from server for chunk {sequence}. Retrying...")
                continue  # Retry on no response
            if response.status == NTPspyStatus.ERROR:
                self.logger.error(f"Server returned fatal error for chunk {sequence}. Aborting transfer.")
                return False  # Abort on server error
            #response_bytes = bytes(response.payload)
            #if response_bytes != data[:length]:
            #    self.logger.warning(f"Payload mismatch for chunk {sequence}. Expected: {data[:length]}, Received: {response_bytes}.")
            #    continue  # Retry on payload mismatch

            self.logger.debug(f"Session: {session_id} Chunk: {sequence} transferred {length} bytes")
            return True

        self.logger.error(f"Failed to transfer chunk {sequence} for session {session_id}.")
        return False

    def verify_data(self, session_id: int, expected_crc: int):
        """verify file integrity"""
        request = NTPspyMessage(
            function=NTPspyFunction.CHECK_DATA,
            magic=self.magic_number,
            session_id=session_id,
            payload=expected_crc.to_bytes(4, 'big')
        )
        self.logger.info(f"Session: {session_id} - Sending CRC check: {expected_crc:08x}")
        response = self.send_ntpspy(request)

        if not response:
            self.logger.error("No response from server.")
            return False
        if response.status == NTPspyStatus.ERROR:
            self.logger.error("Server in error state.")
            return False
        if response.payload != expected_crc:
            self.logger.error(f"CRC failure. Expected: {expected_crc:x}, Received: {response.payload:x}")
            return False
        self.logger.info(f"Data check passed, session {session_id}.")
        return True

    def transfer_text(self, session_id: int, sequence: int, data: bytes, length: int, chunkcount:int):
        """send filename to server in chunks"""
        for attempt in range(self.max_retry):
            msg = NTPspyMessage(
                status=NTPspyStatus.NORMAL,
                function=NTPspyFunction.XFER_TEXT,
                magic=self.magic_number,
                session_id=session_id,
                sequence_number=sequence,
                payload=data[:length],
                length=length
            )
            self.logger.debug(f"Session: {session_id} Chunk: {sequence}/{chunkcount} Attempt: {attempt + 1}/{self.max_retry} Data: {data}")
            response = self.send_ntpspy(msg)
            if not response:
                self.logger.warning(f"No response from server for text chunk {sequence}. Retrying...")
                continue  # Retry on no response
            if response.status == NTPspyStatus.ERROR:
                self.logger.error(f"Server returned fatal error for text chunk {sequence}. Aborting transfer.")
                return False  # Abort on server error
#            response_bytes = bytes(response.payload)
#            if response_bytes != data[:length]:
#                self.logger.warning(f"Payload mismatch for text chunk {sequence}. Expected: {data[:length]}, Received: {response_bytes}. Retrying...")
#                continue  # Retry on payload mismatch

            self.logger.debug(f"Session: {session_id} Chunk: {sequence} transferred {length} bytes")
            return True

        self.logger.error(f"Failed to transfer text chunk {sequence} for session {session_id}.")
        return False

    def verify_text(self, session_id: int, expected_crc: int):
        """verify filename integrity"""
        request = NTPspyMessage(
            function=NTPspyFunction.CHECK_TEXT,
            magic=self.magic_number,
            session_id=session_id,
            payload=expected_crc.to_bytes(4, 'big')
        )
        self.logger.info(f"Session: {session_id} - Sending CRC check: {expected_crc:08x}")
        response = self.send_ntpspy(request)

        if not response:
            self.logger.error("No response from server.")
            return False
        if response.status == NTPspyStatus.ERROR:
            self.logger.error("Server in error state.")
            return False
        if response.payload != expected_crc:
            self.logger.error(f"CRC failure. Expected: {expected_crc:x}, Received: {response.payload:x}")
            return False
        
        self.logger.info(f"Text check passed for session: {session_id}.")
        return True

    def rename(self, session_id):
        """instruct server to rename file and finalize session"""
        self.logger.info(f"Sending rename message for session ID: {session_id}")
        msg = NTPspyMessage(function=NTPspyFunction.RENAME, magic=self.magic_number, session_id=session_id)
        response = self.send_ntpspy(msg)
        if not response:
            self.logger.error("Rename failed.")
            return False
        if response.status == NTPspyStatus.ERROR:
            self.logger.error("Server reported error. File already exists?")
            self.abort(session_id)
            return False
        if response.status == NTPspyStatus.NORMAL:
            self.logger.info(f"File renamed successfully for session ID: {session_id}.")
            return True

    def abort(self, session_id: int):
        """notify server to discontinue and purge session"""
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

if __name__ == "__main__":
    client = NTPspyClient()
