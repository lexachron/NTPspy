from storageprovider import MemoryStorageProvider, BufferType
import logging
import zlib

provider = MemoryStorageProvider()

formatter = logging.Formatter(
    fmt='%(asctime)s - %(levelname)s - %(name)s.%(funcName)s - %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logconsole = logging.StreamHandler()
logconsole.setLevel(logging.DEBUG)
logconsole.setFormatter(formatter)

provider.logger.addHandler(logconsole)
provider.logger.setLevel(logging.DEBUG)

files = [
    {"filename": "readme.txt", "content": b"This is a test file for MemoryStorageProvider."},
    {"filename": "data.bin", "content": b"Binary data simulation for testing purposes."},
    {"filename": "notes.md", "content": b"Markdown notes for the project documentation."},
    {"filename": "tiny.png", "content": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x00IEND\xaeB`\x82"},
    {"filename": "", "content": b"#!/usr/bin/env python3\n# This is a simple Python script for testing."},
]

chunk_size = 4
session_ids = []

for file in files:
    filename = file["filename"].encode()
    content = file["content"]

    content_chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
    filename_chunks = [filename[i:i+chunk_size] for i in range(0, len(filename), chunk_size)]

    session_id = provider.allocate_session()
    session_ids.append(session_id)

    for sequence, chunk in enumerate(filename_chunks):
        provider.write(BufferType.TEXT, session_id, sequence, chunk)

    if filename:
        expected = zlib.crc32(filename)
        actual = provider.check(BufferType.TEXT, session_id)
        assert expected == actual, f"CRC failed for {file['filename']}: expected {expected:08x}, got {actual:08x}"

    for sequence, chunk in enumerate(content_chunks):
        provider.write(BufferType.DATA, session_id, sequence, chunk)

    expected = zlib.crc32(content)
    actual = provider.check(BufferType.DATA, session_id)
    assert expected == actual, f"CRC failed for {file['filename']}: expected {expected:08x}, got {actual:08x}"

    provider.finalize_session(session_id)

    provider.delete_session(session_id)