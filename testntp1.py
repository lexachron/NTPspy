import test
from ntpspy import NTPpacket, NTPspyMessage
import sys
import csv

# csv test payload headers
# memo,xmit.ntpspy.version,xmit.ntpspy.magic,xmit.ntpspy.session_id,xmit.ntpspy.sequence_num,xmit.ntpspy.payload,xmit.ntpspy.length,xmit.ntpspy.function,xmit.ntpspy.status,xmit.ntp.LI,xmit.ntp.VN,xmit.ntp.mode,xmit.ntp.stratum,xmit.ntp.poll,xmit.ntp.precision,xmit.ntp.rootdelay,xmit.ntp.rootdispersion,xmit.ntp.refid,xmit.ntp.reftime_sec,xmit.ntp.reftime_frac,xmit.ntp.origtime_sec,xmit.ntp.origtime_frac,xmit.ntp.transtime_sec,xmit.ntp.transtime_frac,xmit.raw

def parse_test(csvrow):
    test = {}
    test["memo"] = csvrow["memo"]
    test["xmit"] = {}
    test["xmit"]["raw"] = csvrow["xmit.raw"]
    test["xmit"]["ntpspy"] = NTPspyMessage()
    test["xmit"]["ntp"] = NTPpacket()
    for key, value in csvrow.items():
        # if key does not startwith either ('xmit' or 'recv'), continue
        if not (key.startswith("xmit") or key.startswith("recv")):
            continue
        if key.split(".")[1] == "raw":
            continue
        direction, format, field = key.split(".")
        if value.startswith("0x"):
            value = int(value, 16)
        else:
            #print(f"key: {key}, value: {value}")
            value = int(value)
        setattr(test[direction][format], field, value)
            
    # TODO: for expected response to xmit (phase 2 testing)
    test["recv"] = {}
    # test["recv"]["raw"] = csvrow["recv.raw"]
    # test["recv"]["ntpspy"] = NTPspyMessage()
    # test["recv"]["ntp"] = NTPpacket()
    return test

def read_test_data(csvfile):
    tests = []
    with open(csvfile, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            test = parse_test(row)
            tests.append(test)
    return tests

def test_raw2ntp(raw, ntp):
    raw = bytes.fromhex(raw)
    actual = NTPpacket(raw)
    for field in vars(ntp).keys():
        expected_value = getattr(ntp, field)
        actual_value = getattr(actual, field)
        if expected_value != actual_value:
            print(f"{field}: expected {expected_value}, got {actual_value}")
            return False
    return True

def test_ntp2ntpspy(ntp, ntpspy):
    actual = NTPspyMessage(ntp)
    for field in vars(ntpspy).keys():
        expected_value = getattr(ntpspy, field)
        actual_value = getattr(actual, field)
        if expected_value != actual_value:
            print(f"{field}: expected {expected_value}, got {actual_value}")
            return False
    return True

def test_ntpspy2ntp(ntpspy, ntp):
    pass

def test_ntp2raw(ntp, raw):
    actual = ntp.pack()
    expected = bytes.fromhex(raw)
    if actual != expected:
        print(f"actual: {actual}, expected: {expected}")
        return False
    return True

def run_tests(test):
    test_ntp2raw(test["xmit"]["ntp"], test["xmit"]["raw"])
    test_raw2ntp(test["xmit"]["raw"], test["xmit"]["ntp"])
    test_ntp2ntpspy(test["xmit"]["ntp"], test["xmit"]["ntpspy"])
    # test_ntpspy2ntp(test["xmit"]["ntpspy"], test["xmit"]["ntp"])

if "__main__" == __name__:
    tests = read_test_data(sys.argv[1])
    for i, test in enumerate(tests):
        print(f"Running test {i+1}")
        run_tests(test)