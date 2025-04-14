from abc import ABC, abstractmethod
import io
import zlib
import binascii
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
        self.files = {}

    def allocate_session(self) -> int:
        """get next available ID"""
        session_id = 1
        while session_id in self.sessions:
            session_id += 1
        self.sessions[session_id] = io.BytesIO()
        return session_id

    def write_chunk(self, session_id: int, sequence: int, data: bytes, length: int) -> None:
        """store length bytes at offset sequence * chunksize"""
        if session_id not in self.sessions:
            raise ValueError("Invalid session ID")
        buffer = self.sessions[session_id]
        buffer.seek(sequence * 4)
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
        """verify filename integrity"""
        if session_id not in self.filenames:
            raise ValueError("Invalid session ID")
        full_text = ''.join(self.filenames[session_id][seq].decode('utf-8') for seq in sorted(self.filenames[session_id]))
        return zlib.crc32(full_text.encode('utf-8'))

    def finalize_session(self, session_id: int, provided_checksum: int) -> bool:
        return self.check_data(session_id) == provided_checksum

    def finalize_filename(self, session_id: int, overwrite=False) -> bool:
        if session_id not in self.filenames:
            raise ValueError("Invalid session ID")

        # simulate `mv session_id.dat full_filename; rm session_id.txt`
        full_filename = ''.join(self.filenames[session_id][seq].decode('utf-8') for seq in sorted(self.filenames[session_id]))
        if full_filename in self.files and not overwrite:
            raise ValueError("File already exists")
        self.files[full_filename] = self.sessions.pop(session_id)
        del self.filenames[session_id]

        return True
    
    def print_session(self, session_id: int):
        if session_id not in self.sessions:
            raise ValueError("Invalid session ID")
        buffer = self.sessions[session_id]
        buffer.seek(0)
        data = buffer.read()
        #print(binascii.hexlify(data).decode('utf-8'))
        print(data)
    
    def get_filename(self, session_id: int):
        if session_id not in self.filenames:
            raise ValueError("Invalid session ID")
        full_text = ''.join(self.filenames[session_id][seq].decode('utf-8') for seq in sorted(self.filenames[session_id]))
        return full_text
    
    def print_filename(self, session_id: int):
        if session_id not in self.filenames:
            raise ValueError("Invalid session ID")
        print(self.get_filename(session_id))

    def list_sessions(self):
        for session_id in self.sessions:
            print(f"{session_id:08x}:{self.get_filename(session_id)}:{len(self.sessions[session_id].getbuffer())}")

    def print_file(self, filename: str):
        if filename not in self.files:
            raise ValueError("Invalid filename")
        buffer = self.files[filename]
        buffer.seek(0)
        data = buffer.read()
        #print(binascii.hexlify(data).decode('utf-8'))
        print(data)

    def print_files(self) -> None:
        for filename in self.files:
            print(f"Filename: {filename}, Length: {len(self.files[filename].getbuffer())}")
            self.print_file(filename)

    def list_files(self) -> None:
        for filename in self.files:
            length = len(self.files[filename].getbuffer())
            print(f"{length} {filename}")

    def delete_session(self, session_id: int) -> None:
        if session_id in self.sessions:
            del self.sessions[session_id]
        if session_id in self.filenames:
            del self.filenames[session_id]
    
    def purge_sessions(self) -> None:
        self.sessions.clear()
        self.filenames.clear()

    def remove_file(self, filename: str) -> None:
        if filename in self.files:
            del self.files[filename]

    def purge_files(self) -> None:
        self.files.clear()