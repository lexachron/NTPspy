import unittest
import csv

from ntpspyserver import NTPspyServer
from ntpdatagram import NTPdatagram
from timestampgen import MockTimestampGenerator
from storageprovider import MemoryStorageProvider

TESTDATA_NTP = "ntpspy_testdata/test_handle_ntp.csv"
#TESTDATA_SPY = "ntpspy_testdata/test_handle_spy.csv"

class TestNTPspyServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ntp_test_cases = cls.load_test_cases(TESTDATA_NTP)
 #       cls.spy_test_cases = cls.load_test_cases(TESTDATA_SPY)

    @staticmethod
    def load_test_cases(filepath):
        test_cases = []
        with open(filepath, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row_num, row in enumerate(reader, start=1):
                server_config = {}
                input_fields = {}
                expected_fields = {}

                for key, value in row.items():
                    base = 16 if value.startswith("0x") else 10
                    if key.startswith("server."):
                        server_config[key[7:]] = int(value, base)
                    elif key.startswith("in."):
                        input_fields[key[7:]] = int(value, base)
                    elif key.startswith("out."):
                        expected_fields[key[8:]] = int(value, base)
                test_cases.append((row_num, server_config, input_fields, expected_fields))

        return test_cases

    def test_handle_ntp(self):
        """test NTP request handling"""
        mocktimestamp = MockTimestampGenerator()
        addr = ("127.1.1.1", 6667)
        for row_num, server_config, input_fields, expected_fields in self.ntp_test_cases:
            with self.subTest(row=row_num):
                storage = MemoryStorageProvider()
                server_config["storage_provider"] = storage  
                server = NTPspyServer(**server_config)
                server.timestampgen = mocktimestamp
                incoming = NTPdatagram(**input_fields)
                expected = NTPdatagram(**expected_fields)
                actual = server.handle_ntp(incoming, addr)
                self.assertEqual(actual, expected)