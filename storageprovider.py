from abc import ABC, abstractmethod
import io
import zlib
from collections import defaultdict

class StorageProvider(ABC):
    @abstractmethod
    def allocate_session(self) -> int:
        pass

    @abstractmethod
    def write_chunk(self, session_id: int, sequence: int, data: bytes, length: int) -> None:
        pass

    @abstractmethod
    def write_text(self, session_id: int, sequence: int, text: str, length: int) -> None:
        pass

    @abstractmethod
    def finalize_session(self, session_id: int, provided_checksum: str) -> bool:
        pass

    @abstractmethod
    def finalize_filename(self, session_id: int, provided_checksum: str) -> bool:
        pass

    @abstractmethod
    def check_data(self, session_id: int) -> str:
        pass

    @abstractmethod
    def check_text(self, session_id: int) -> str:
        pass

class MemoryStorageProvider(StorageProvider):
    def init(self):
        self.sessions = {}  # {session_id: BytesIO() for binary data}
        self.filenames = defaultdict(dict)  # {session_id: {sequence: text}}
        self.session_counter = 1  

    def allocate_session(self) -> int:
        """get next available ID"""
        session_id = self.session_counter
        self.session_counter += 1
        self.sessions[session_id] = io.BytesIO()
        return session_id

    def write_chunk(self, session_id: int, sequence: int, data: bytes, length: int) -> None:
        """store length bytes at offset sequence * maxlength"""
        if session_id not in self.sessions:
            raise ValueError("Invalid session ID")
        buffer = self.sessions[session_id]
        buffer.seek(sequence * length)
        buffer.write(data[:length])

    def write_text(self, session_id: int, sequence: int, text: str, length: int) -> None:
        self.filenames[session_id][sequence] = text[:length]

    def check_data(self, session_id: int) -> int:
        """verify file integrity"""
        if session_id not in self.sessions:
            raise ValueError("Invalid session ID")
        buffer = self.sessions[session_id]
        buffer.seek(0)
        return zlib.crc32(buffer.read())

    def check_text(self, session_id: int) -> int:
        if session_id not in self.filenames:
            raise ValueError("Invalid session ID")
        full_text = ''.join(self.filenames[session_id][seq] for seq in sorted(self.filenames[session_id]))
        return zlib.crc32(full_text.encode('utf-8'))

    def finalize_session(self, session_id: int, provided_checksum: int) -> bool:
        return self.check_data(session_id) == provided_checksum

    def finalize_filename(self, session_id: int, provided_checksum: int) -> bool:
        """rename file if valid"""
        if self.check_text(session_id) != provided_checksum:
            return False

        full_filename = ''.join(self.filenames[session_id][seq] for seq in sorted(self.filenames[session_id]))

        # simulate `mv session_id.dat full_filename; rm session_id.txt`
        if session_id in self.sessions:
            self.files[full_filename] = self.sessions.pop(session_id)
        del self.filenames[session_id]

        return True
