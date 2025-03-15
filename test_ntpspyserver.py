import unittest
import csv

from ntpspyserver import NTPspyServer
from ntpspymessage import NTPspyMessage, NTPspyFunction
from ntpdatagram import NTPdatagram, NTPmode
from timestampgen import MockTimestampGenerator

TESTDATA_NTP = "ntpspy_testdata/test_ntpspyserver_ntp.csv"
#TESTDATA_SPY = "ntpspy_testdata/test_ntpspyserver_spy.csv"

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
