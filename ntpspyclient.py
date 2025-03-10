import socket
from ntpdatagram import NTPdatagram
from ntpspymessage import NTPspyMessage

NTPSPY_VERSION = 1
DEFAULT_MAGIC = 0xdeadbeef
DEFAULT_PORT = 123

class NTPspyClient:
    def __init__(self, server, port=DEFAULT_PORT, magic=DEFAULT_MAGIC, version=NTPSPY_VERSION, verbose=False):
        self.server = server
        self.port = port
        self.magic = magic
        self.version = version
        self.verbose = verbose
        self.session_id = 0
        self.interval = 50 # TODO
        self.obfuscate = False # TODO
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, ntp: NTPdatagram):
        self.sock.sendto(ntp.to_bytes(), (self.server, self.port))

    def query(self):
        """probe for ntpspy presence and version"""
        pass

    def transfer(self, filename):
        """send file to ntpspy server"""
        pass

    def timesync(self):
        """emulate standard ntp client to test server compatibility"""
        pass

