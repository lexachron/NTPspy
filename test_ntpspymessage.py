import unittest
import csv

from ntpdatagram import NTPdatagram, NTPmode
from ntpspymessage import NTPspyMessage, NTPspyFunction

TESTDATA = "ntpspy_testdata/test_ntpspymessage.csv"

class TestNTPspymessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_cases = []
        with open(TESTDATA, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row_num, row in enumerate(reader, start=1):
                spy_fields, ntp_fields = {}, {}
                for key, value in row.items():
                    base = 16 if value.startswith("0x") else 10
                    if key.startswith("spy."):
                        spy_fields[key[4:]] = int(value, base)
                    elif key.startswith("ntp."):
                        ntp_fields[key[4:]] = int(value, base)
                spy_fields['function'] = NTPspyFunction(spy_fields['function'])
                cls.test_cases.append((row_num, spy_fields, ntp_fields))

    def test_from_ntp(self) -> NTPspyMessage:
        """NTPdatagram -> from_ntp() -> NTPspymessage"""
        for row_num, spy_fields, ntp_fields in self.test_cases:
            with self.subTest(row=row_num):
                ntp = NTPdatagram(**ntp_fields)
                spy = NTPspyMessage.from_ntp(ntp)
                for field, value in spy_fields.items():
                    actual = getattr(spy, field)
                    expected = value
                    self.assertEqual(actual, expected, f"row {row_num}, mismatch field {field}")

    def test_to_ntp(self) -> NTPdatagram:
        """NTPspymessage -> to_ntp() -> NTPdatagram"""
        for row_num, spy_fields, ntp_fields in self.test_cases:
            with self.subTest(row=row_num):
                spy = NTPspyMessage(**spy_fields)
                expected = NTPdatagram(**ntp_fields)
                actual = spy.to_ntp()
                for field, value in ntp_fields.items():
                    actual = value
                    expected = ntp_fields[field]
                    self.assertEqual(actual, expected, f"row {row_num}, mismatch field {field}")

if __name__ == "__main__":
    unittest.main()