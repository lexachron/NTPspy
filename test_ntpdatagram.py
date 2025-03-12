import unittest
import csv
from ntpdatagram import NTPdatagram, NTPmode

TESTDATA = "test_ntpdatagram.csv"

class TestNTPdatagram(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_cases = []
        with open(TESTDATA, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row_num, row in enumerate(reader, start=1):
                ntp_fields = {}
                for key, value in row.items():
                    if key.startswith("ntp."):
                        if value.startswith("0x"):
                            ntp_fields[key[4:]] = int(value, 16)
                        else:
                            ntp_fields[key[4:]] = int(value)
                ntp_fields['mode'] = NTPmode(ntp_fields['mode'])
                raw_bytes = bytes.fromhex(row["raw_bytes"])
                cls.test_cases.append((row_num, ntp_fields, raw_bytes))

    def test_from_bytes(self):
        """bytestring -> from_bytes() -> NTPdatagram"""
        for row_num, ntp_fields, raw_bytes in self.test_cases:
            with self.subTest(row=row_num):
                ntp_packet = NTPdatagram.from_bytes(raw_bytes)
                for field in ntp_fields.keys():
                    actual = getattr(ntp_packet, field)
                    expected = ntp_fields[field]
                    self.assertEqual(actual, expected, f"row {row_num}, mismatch field {field}")
        for i in range(NTPdatagram._SIZE):
            with self.subTest(length=i):
                with self.assertRaises(ValueError, msg=f"invalid datagram size allowed: {i}"):
                    NTPdatagram.from_bytes(b"\x00" * i)

    def test_to_bytes(self):
        """NTPdatagram -> to_bytes() -> bytestring"""
        for row_num, ntp_fields, raw_bytes in self.test_cases:
            with self.subTest(row=row_num):
                ntp_packet = NTPdatagram(**ntp_fields)
                actual = ntp_packet.to_bytes()
                expected = raw_bytes
                bitmask = bytes(a ^ b for a, b in zip(actual, expected))
                bitmask_split = ' '.join([bitmask[i:i+4].hex() for i in range(0, len(bitmask), 4)])
                self.assertEqual(actual, expected, f"mismatch in bits: {bitmask_split}")

    def test_boundary_values(self):
        """test range boundary on each field"""
        for field, (min_val, max_val) in NTPdatagram._RANGES.items():
            with self.subTest(field=field, value=min_val):
                kwargs = {field: min_val}
                ntp_packet = NTPdatagram(**kwargs)
                self.assertEqual(getattr(ntp_packet, field), min_val, f"{field} min value")

            with self.subTest(field=field, value=max_val):
                kwargs = {field: max_val}
                ntp_packet = NTPdatagram(**kwargs)
                self.assertEqual(getattr(ntp_packet, field), max_val, f"{field} max value")

            with self.subTest(field=field, value=min_val - 1):
                kwargs = {field: min_val - 1}
                with self.assertRaises(ValueError, msg=f"{field} allowed below mininum"):
                    NTPdatagram(**kwargs)

            with self.subTest(field=field, value=max_val + 1):
                kwargs = {field: max_val + 1}
                with self.assertRaises(ValueError, msg=f"{field} allowed above maximum"):
                    NTPdatagram(**kwargs)

if __name__ == "__main__":
    unittest.main()
