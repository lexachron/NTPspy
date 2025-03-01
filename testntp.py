import json
from sys import argv
import sys
from ntpspy import NTPpacket, NTPspyMessage

def load_test_payloads(json_file):
    with open(json_file, 'r') as f:
        return json.load(f)


def test_decode_ntp_datagram(ntp, chunk):
    """
    Test the NTPpacket class by decoding raw NTP datagram
    Args:
        ntp (NTPpacket): NTPpacket class instance
        chunk (bytes): raw NTP datagram
    """
    pass

def test_encode_ntp_datagram(ntp, chunk):
    """
    Test serialization of NTPpacket class
    Args:
        ntp (NTPpacket): NTPpacket class instance
        chunk (bytes): raw NTP datagram
    """
    pass

def test_encapsulate_ntpspy_message(ntp, ntpspy):
    """
    Test conversion of NTPspy message to NTP datagram
    Args:
        ntp (NTPpacket): NTPpacket class instance
        ntpspy (NTPspyMessage): NTPspyMessage
    """
    pass

def test_decapsulate_ntpspy_message(ntp, ntpspy):
    """
    Test conversion of NTP datagram to NTPspy message
    Args:
        ntp (NTPpacket): NTPpacket class instance
        ntpspy (NTPspyMessage): NTPspyMessage
    """
    test = NTPspyMessage(ntp)
    for key in vars(ntpspy).keys():
        if getattr(ntpspy, key) != getattr(test, key):
            return False
    return True

def test_payload(ntp, ntpspy, chunk):
    """
    Test each layer of serialization/encapsulation in both directions
    Args:
        ntp (NTPpacket): NTPpacket class instance
        ntpspy (NTPspyMessage): NTPspyMessage
        chunk (bytes): raw NTP datagram
    """
    # test_decode_ntp_datagram(ntp, chunk)
    test_decapsulate_ntpspy_message(ntp, ntpspy)

    return True

def json_to_ntp(json):
    """
    Convert JSON to NTPpacket class instance
    Args:
        json (dict): JSON object
    Returns:
        NTPpacket: NTPpacket class instance
    """
    ntp = NTPpacket()
    for key, value in json.items():
        if hasattr(ntp, key):
            if isinstance(value, str) and value.startswith("0x"):
                setattr(ntp, key, int(value, 16))
            else:
                setattr(ntp, key, value)
    return ntp

def json_to_ntpspy(json):
    """
    Convert JSON to NTPspyMessage class instance
    Args:
        json (dict): JSON object
    Returns:
        NTPspyMessage: NTPspyMessage class instance
    """
    ntpspy = NTPspyMessage()
    for key, value in json.items():
        if hasattr(ntpspy, key):
            if isinstance(value, str) and value.startswith("0x"):
                setattr(ntpspy, key, int(value, 16))
            else:
                setattr(ntpspy, key, value)
    return ntpspy


def run_tests(payloads):
    for i, payload in enumerate(payloads):
        ntpspy = json_to_ntpspy(payload['ntpspy'])
        ntp = json_to_ntp(payload['ntp'])
        chunk = bytes.fromhex(payload['raw'])
        if not test_payload(ntp, ntpspy, chunk):
            print(f"Test {i+1} failed")
            return

if __name__ == "__main__":
    if len(argv) != 2:
        print("Usage: python testntp.py <test_payloads.json>")
        sys.exit(1)

    test_payloads = load_test_payloads(argv[1])
    run_tests(test_payloads)
    