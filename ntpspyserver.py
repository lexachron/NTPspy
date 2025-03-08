import socket

from ntpdatagram import NTPdatagram
from ntpspy import UNIX_TO_NTP
from ntpspymessage import NTPspyMessage

DEFAULT_PATH = "./"
DEFAULT_MAGIC = 0xdeadbeef
NTPSPY_VERSION = 1
UNIX_TO_NTP = 2208988800

class NTPspyServer:
    def __init__(self, port=123, path=DEFAULT_PATH, magic=DEFAULT_MAGIC, version=NTPSPY_VERSION, verbose=False):
        self.port = port
        self.path = path
        self.magic = magic
        self.verbose = verbose
        self.version = version

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            if self.verbose:
                print(f"NTPspy version {NTPSPY_VERSION} listening on port {self.port}, storing files in {self.path}, magic number: 0x{self.magic:x}")
            sock.bind(("", self.port))
            while True:
                data, (addr, port) = sock.recvfrom(1024)
                ntp = NTPdatagram.from_bytes(data)
                if self.verbose:
                    print(f"{addr}:{port} - {vars(ntp)}")
                if ntp.is_ntpspy(self.magic):
                    spy = NTPspyMessage.from_ntp(ntp)
                    if self.verbose:
                        print(f"{addr}:{port} - {vars(spy)}")
                    #spy_response = handle_ntpspy(spy)
                #ntp_response = handle_ntp(ntp)

                #if ntp.is_ntpspy(self.magic):
                #    response = spy_response.to_ntp(ntp_response)

    def handle_ntp(self, ntp: NTPdatagram):
        """process NTP fields IAW RFC"""
        pass

    def handle_ntpspy(self, spy: NTPspyMessage):
        """process NTPspy functions"""
        pass
