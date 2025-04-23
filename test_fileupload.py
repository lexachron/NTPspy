from time import sleep
from ntpspyclient import NTPspyClient
from ntpspyserver import NTPspyServer
from storageprovider import MemoryStorageProvider
import unittest

files = [
    {"filename": "readme.txt", "content": b"This is a test file for MemoryStorageProvider."},
    {"filename": "tiny.png", "content": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x00IEND\xaeB`\x82"},
    {"filename": None, "content": b"anonymous data without filename."},
]

magic_numbers = [
    0x12345678,
    0xcafebabe,
    0xffffffff
]

ports = [
    1111,
    6667,
    12345,
]

class TestFileUpload(unittest.TestCase):
    def test_file_upload(self):
        for port in ports:
            for magic_number in magic_numbers:
                with self.subTest(port=port, magic_number=magic_number):
                    storage = MemoryStorageProvider()
                    server = NTPspyServer(storage_provider=storage, port=port, magic_number=magic_number, verbose=2)
                    server.start_background()
                    server.running = True
                    client = NTPspyClient(port=port, magic_number=magic_number)

                    try:
                        for file in files:
                            filename = file["filename"]
                            content = file["content"]
                            client.transfer_session(content, filename)

                            if filename:
                                self.assertIn(filename, storage.files)
                                self.assertEqual(storage.files[filename].getvalue(), content)
                            else:
                                self.assertTrue(any(buffer.getvalue() == content for buffer in storage.files.values()))
                    finally:
                        client.close()
                        server.stop()
                        sleep(1) # time for OS to release port, increase if port errors

class TestFileOverwrite(unittest.TestCase):
    def test_overwrite(self):
        port = ports[0]
        magic_number = magic_numbers[0]
        file = files[0]
        filename = file["filename"]
        content = file["content"]
        storage = MemoryStorageProvider()
        server = NTPspyServer(storage_provider=storage, port=port, magic_number=magic_number, allow_overwrite=True, verbose=2)
        client = NTPspyClient(port=port, magic_number=magic_number)
        server.start_background()
        server.running = True

        #check overwrite allowed
        try:
            client.transfer_session(content, filename)
            self.assertIn(filename, storage.files)
            self.assertEqual(storage.files[filename].getvalue(), content)

            new_content = b"im in ur file overitening ur data"
            client.transfer_session(new_content, filename)
            self.assertEqual(storage.files[filename].getvalue(), new_content)
        finally:
            client.close()
            server.stop()
            sleep(1)

    def test_no_overwrite(self):
        port = ports[0]
        magic_number = magic_numbers[0]
        file = files[0]
        filename = file["filename"]
        content = file["content"]
        storage = MemoryStorageProvider()
        server = NTPspyServer(storage_provider=storage, port=port, magic_number=magic_number, allow_overwrite=False, verbose=2)
        client = NTPspyClient(port=port, magic_number=magic_number)
        server.start_background()
        server.running = True

        #check overwrite not allowed
        try:
            client.transfer_session(content, filename)
            self.assertIn(filename, storage.files)
            self.assertEqual(storage.files[filename].getvalue(), content)

            new_content = b"im in ur file overitening ur data"
            client.transfer_session(new_content, filename)
            self.assertEqual(storage.files[filename].getvalue(), content) # 1st upload still intact
            self.assertEqual(len(storage.files), 2) # 2nd upload saved to deconflicted name
        finally:
            client.close()
            server.stop()
            sleep(1)

if __name__ == "__main__":
    unittest.main()

