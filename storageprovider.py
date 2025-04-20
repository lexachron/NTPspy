import datetime
import io
import threading
import zlib
import logging
import os
from abc import ABC, abstractmethod
from enum import Enum

# each StorageProvider provides storage for 2 data streams: 
#   'data' (NTPspy payload) and 'text' (original filename of payload - optional)
# provider receives payload in chunks <= 4 bytes
# incoming chunks are identified by 
#   type ('data' | 'text')
#   session ID (1-0xFFFFFFFF)
#   sequence number (0-0xFFFFFFFF)
# at the end of the transfer, the integrity of both buffers is checked (i.e. CRC32)
# if the integrity check passes
#   the content of the 'text' buffer (if provided) becomes the permanent handle of the 'data' buffer
#   if no filename is provided, the permanent handle is based on date + session ID
# finally the session ID is released for reuse

class BufferType(Enum):
    DATA = "data"
    TEXT = "text"

class StorageProvider(ABC):
    def __init__(self):
        self.logger = logging.getLogger(type(self).__name__)
        self.logger.setLevel(logging.DEBUG)

    @abstractmethod
    def allocate_session(self, session_id: int = None) -> int:
        """reserve the requested session ID if provided and available, 
           else allocate the lowest available ID"""
        pass

    @abstractmethod
    def write(self, type: str, session_id: int, sequence: int, data: bytes, length: int) -> bool:
        """write `length` bytes at index `sequence` to buffer `type` associated with `session_id`"""
        pass

    @abstractmethod
    def check(self, type: str, session_id: int) -> int:
        """return a hash, checksum, or CRC of the buffer `type` associated with `session_id`"""
        pass

    @abstractmethod
    def finalize_session(self, session_id: int) -> bool:
        """associate the contents of 'data' buffer with its permanent handle
           i.e. contents of 'text' buffer if available, else date + session ID"""
        pass

    @abstractmethod
    def delete_session(self, session_id: int) -> bool:
        """flush all buffers associated with `session_id` and release ID for reuse"""
        pass

    @abstractmethod
    def purge_sessions(self) -> None:
        """delete all active sessions"""
        pass

class StorageError(Exception):
    """Base class for storage-related errors."""
    pass

class FatalStorageError(StorageError):
    """Indicates a fatal error that requires session termination."""
    pass

class DiskStorageProvider(StorageProvider):
    def __init__(self, base_path: str):
        super().__init__()
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)
        self.sessions = {}
        self.lock = threading.Lock()
        self.max_chunksize = 4 # bytes

        # clean up orphaned buffer files
        for file_name in os.listdir(self.base_path):
            file_path = os.path.join(self.base_path, file_name)
            if os.path.isfile(file_path):
                if not any(file_name.endswith(ext) for ext in [".dat", ".txt"]):
                    continue #skip non-buffer file extensions
                basename = file_name.split('.')[0]
                try:
                    _ = int(basename, 16)
                except ValueError:
                    continue  #skip buffer extensions with not hex filename
                if len(basename) != 8:
                    continue #skip hex.dat or .txt but not 8 digits
                os.remove(file_path)
                self.logger.info(f"Removed orphaned file: {file_name}")

    def allocate_session(self, session_id: int = None) -> int:
        with self.lock:
            while True:
                if session_id is None:
                    session_id = max(self.sessions.keys(), default=0) + 1
                if session_id in self.sessions:
                    self.logger.error(f"Session ID {session_id:x} already in use")
                    raise FatalStorageError("Session ID already in use")
                
                data_file = os.path.join(self.base_path, f"{session_id:08x}.dat")
                text_file = os.path.join(self.base_path, f"{session_id:08x}.txt")
                if os.path.exists(data_file) or os.path.exists(text_file):
                    self.logger.warning(f"Files for session ID {session_id:x} already exist, skipping")
                    session_id += 1
                    continue
                
                self.sessions[session_id] = {"data": f"{session_id:08x}.dat", "text": f"{session_id:08x}.txt"}
                for buffer_type in [BufferType.DATA, BufferType.TEXT]:
                    file_path = os.path.join(self.base_path, self.sessions[session_id][buffer_type.value])
                    with open(file_path, "wb"):
                        pass # `touch file_path`
                
                self.logger.info(f"Allocated session ID: {session_id:x}")
                return session_id

    def write(self, type: BufferType, session_id: int, sequence: int, data: bytes) -> bool:
        with self.lock:
            if session_id not in self.sessions:
                self.logger.error(f"Invalid session ID: {session_id:x}")
                raise FatalStorageError("Invalid session ID")
            try:
                file_path = os.path.join(self.base_path, self.sessions[session_id][type.value])
                with open(file_path, "ab") as f:
                    f.seek(sequence * self.max_chunksize)
                    f.write(data)
                self.logger.debug(f"Wrote {len(data)} bytes to session {session_id:x} {type.value} buffer @ {(sequence * self.max_chunksize):x}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to write to session {session_id:x}: {e}")
                return False

    def check(self, type: BufferType, session_id: int) -> int:
        with self.lock:
            if session_id not in self.sessions:
                self.logger.error(f"Invalid session ID: {session_id:x}")
                raise FatalStorageError("Invalid session ID")
            
            file_path = os.path.join(self.base_path, self.sessions[session_id][type.value])
            try:
                with open(file_path, "rb") as f:
                    data = f.read()
                checksum = zlib.crc32(data)
                self.logger.debug(f"Calculated CRC32 for {type.value} buffer of session {session_id:x}: {checksum:08x}")
                return checksum
            except Exception as e:
                self.logger.error(f"Failed to calculate CRC32 for session {session_id:x}: {e}")
                raise FatalStorageError("Failed to calculate CRC32")

    def finalize_session(self, session_id: int, overwrite: bool = False) -> str:
        with self.lock:
            if session_id not in self.sessions:
                self.logger.error(f"Invalid session ID: {session_id:x}")
                raise FatalStorageError("Invalid session ID")

            # recover original filename from text buffer if available
            handle = self._read_filename(session_id)

            # directory traversal mitigation
            if handle and not self._check_path(handle):
                self.logger.warning(f"Discarding path '{handle}' outside base directory.")
                handle = None

            # autogenerated filename if none provided or invalidated
            if not handle:
                handle = self._generate_filename(session_id)
                self.logger.info(f"Using generated filename: {handle}")

            # filename collision mitigation
            path = os.path.join(self.base_path, handle)
            final_path = self._resolve_collision(path, overwrite)

            # double check no writing outside base path
            if not self._check_path(final_path):
                self.logger.error(f"Final path '{final_path}' is outside base directory.")
                raise FatalStorageError("Invalid final path")

            data_file = os.path.join(self.base_path, self.sessions[session_id][BufferType.DATA.value])
            try:
                os.rename(data_file, final_path)
                filename = os.path.relpath(final_path, self.base_path)
                self.logger.info(f"Finalized session {session_id:x} to '{filename}'")
                return filename
            except Exception as e:
                self.logger.error(f"Failed to finalize session {session_id:x}: {e}")
                raise FatalStorageError("Failed to finalize session")

    def _check_path(self, target_path: str) -> bool:
        abs_path = os.path.abspath(self.base_path)
        target_path = os.path.abspath(os.path.join(abs_path, target_path))
        return target_path.startswith(abs_path)
    
    def _read_filename(self, session_id: int) -> str:
        text_file = os.path.join(self.base_path, self.sessions[session_id][BufferType.TEXT.value])
        if os.path.exists(text_file):
            with open(text_file, "r") as f:
                return f.read().strip()
        return None

    def _generate_filename(self, session_id: int) -> str:
        timestamp = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
        return f"{timestamp}-{session_id:08x}"
    
    def _resolve_collision(self, final_path: str, overwrite: bool) -> str:
        base, ext = os.path.splitext(final_path)
        suffix = 0
        while os.path.exists(final_path) and not overwrite:
            suffix += 1
            final_path = f"{base}_{suffix:03d}{ext}"
        if suffix > 0:
            self.logger.warning(f"Filename deconflict:'{base}{ext}' -> '{final_path}'")
        return final_path

    def delete_session(self, session_id: int) -> None:
        with self.lock:
            if session_id not in self.sessions:
                self.logger.error(f"Invalid session ID: {session_id:x}")
                raise FatalStorageError("Invalid session ID")

            for buffer_type in [BufferType.DATA, BufferType.TEXT]:
                file_path = os.path.join(self.base_path, self.sessions[session_id][buffer_type.value])
                if os.path.exists(file_path):
                    os.remove(file_path)
                    self.logger.info(f"Deleted {buffer_type.value} buffer for session {session_id:x}")

            del self.sessions[session_id]
            self.logger.info(f"Released session ID: {session_id:x}")

    def purge_sessions(self) -> None:
        with self.lock:
            dead_sessions = list(self.sessions.keys())
            for session_id in dead_sessions:
                for buffer_type in [BufferType.DATA, BufferType.TEXT]:
                    file_path = os.path.join(self.base_path, self.sessions[session_id][buffer_type.value])
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        self.logger.info(f"Deleted {buffer_type.value} buffer for session {session_id:x}")
                del self.sessions[session_id]
        self.logger.info(f"Purged all active sessions: {', '.join(f'{id:x}' for id in dead_sessions)}")

    def list_sessions(self) -> None:
        with self.lock:
            for session_id, buffers in self.sessions.items():
                data_file = os.path.join(self.base_path, buffers[BufferType.DATA.value])
                data_length = os.path.getsize(data_file)
                print(f"{session_id:08x}: {data_length}")


class MemoryStorageProvider(StorageProvider):
    def __init__(self):
        super().__init__()
        self.sessions = {}
        self.files = {}
        self.lock = threading.Lock()
        self.max_chunksize = 4 # bytes

    def allocate_session(self, session_id: int = None) -> int:
        with self.lock:
            if session_id is None:
                session_id = max(self.sessions.keys(), default=0) + 1
            if session_id in self.sessions:
                self.logger.error(f"Session ID {session_id:x} already in use")
                raise FatalStorageError("Session ID already in use")
            self.sessions[session_id] = {"data": io.BytesIO(), "text": io.BytesIO()}
            self.logger.info(f"Allocated session ID: {session_id:x}")
            return session_id

    def write(self, type: BufferType, session_id: int, sequence: int, data: bytes) -> bool:
        with self.lock:
            if session_id not in self.sessions:
                self.logger.error(f"Invalid session ID: {session_id:x}")
                raise FatalStorageError("Invalid session ID")
            try:
                buffer = self.sessions[session_id][type.value]
                buffer.seek(sequence * self.max_chunksize)
                buffer.write(data)
                return True
            except Exception as e:
                self.logger.error(f"Failed write to session {session_id:x}: {e}")
                return False

    def check(self, type: BufferType, session_id: int) -> int:
        with self.lock:
            if session_id not in self.sessions:
                self.logger.error(f"Invalid session ID: {session_id:x}")
                raise FatalStorageError("Invalid session ID")
            buffer = self.sessions[session_id][type.value]
            buffer.seek(0)
            crc32 = zlib.crc32(buffer.read())
            self.logger.debug(f"Calculating CRC32 for session {session_id:x} ({type.value}): {crc32:08x}")
            return crc32

    def finalize_session(self, session_id: int, overwrite: bool = False) -> str:
        with self.lock:
            if session_id not in self.sessions:
                self.logger.error(f"Invalid session ID: {session_id:x}")
                raise FatalStorageError("Invalid session ID")

            text_buffer = self.sessions[session_id][BufferType.TEXT.value]
            text_buffer.seek(0)
            handle = text_buffer.read().decode()
            if not handle:
                timestamp = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
                handle = f"{timestamp}-{session_id:08x}"

            if handle in self.files and not overwrite:
                self.logger.error(f"File '{handle}' already exists and overwrite is disabled")
                raise FatalStorageError(f"Cannot overwrite '{handle}'")

            self.files[handle] = self.sessions[session_id][BufferType.DATA.value]
            length = len(self.files[handle].getbuffer())
            self.logger.info(f"Saved session {session_id:x} to '{handle}' ({length} bytes)")
            return handle
        
    def delete_session(self, session_id: int) -> None:
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                self.logger.info(f"Released session ID: {session_id:x}")
            else:
                self.logger.error(f"Invalid session ID: {session_id:x}")
                raise FatalStorageError("Invalid session ID")

    def purge_sessions(self) -> None:
        with self.lock:
            self.sessions.clear()
            self.logger.info("Purged all active sessions")

#ifdef DEBUG
    def list_sessions(self) -> None:
        with self.lock:
            for session_id, buffers in self.sessions.items():
                data_length = len(buffers[BufferType.DATA.value].getbuffer())
                filename = buffers[BufferType.TEXT.value].getvalue().decode() or None
                print(f"{session_id:08x}: {data_length} ({filename})")

    def print_session(self, session_id: int) -> None:
        with self.lock:
            if session_id in self.sessions:
                print(self.sessions[session_id][BufferType.DATA.value].getvalue())
            else:
                print(f"Session ID {session_id:x} not found")

    def list_files(self) -> None:
        with self.lock:
            for filename, buffer in self.files.items():
                length = len(buffer.getbuffer())
                print(f"{length} {filename}")

    def print_file(self, filename: str) -> None:
        with self.lock:
            if filename in self.files:
                print(self.files[filename].getvalue())
            else:
                print(f"File '{filename}' not found")
    
    def delete_file(self, filename: str) -> bool:
        with self.lock:
            if filename in self.files:
                del self.files[filename]
                self.logger.info(f"Removed file '{filename}'")
                return True
            else:
                self.logger.error(f"File '{filename}' not found")
                return False
    
    def purge_files(self) -> None:
        with self.lock:
            self.files.clear()
            self.logger.info("Purged all files")
#endif