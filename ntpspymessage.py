from enum import IntEnum
from ntpdatagram import NTPdatagram

class NTPspyFunction(IntEnum):
    PROBE = 0
    XFER_DATA = 1
    CHECK_DATA = 2
    XFER_TEXT = 3
    CHECK_TEXT = 4
    RENAME = 5
    ABORT = 9

class NTPspyStatus(IntEnum):
    NORMAL = 0
    SUCCESS = 1
    FATAL_ERROR = 2
    ERROR = 3

# NTPspy messages are encapsulated within standard NTP datagrams

class NTPspyMessage:
    def __init__(self,
                 status=0,
                 function=NTPspyFunction.PROBE,
                 version=1,
                 magic=0,
                 session_id=0,
                 sequence_number=0,
                 payload=0,
                 length=0
                 ):
        self.status = status # ntp.leap
            # 1: first chunk of new transfer
            # 2: last chunk of this session
            # 3: fatal error, abort session
        self.function = function # ntp.poll
        self.version = version #ntp.precision
            # ntpspy protocol version, valid range 1-15
        self.magic = magic # ntp.rootdelay
            # magic number to distinguish ntpspy messages from standard ntp requests
            # valid range 1-0xFFFFFFFF (higher the better to avoid collision)
        self.session_id = session_id # ntp.refid
            # used to collate message payloads with same session into single file, valid range 1-0xFFFFFFFF
        self.sequence_number = sequence_number # ntp.reftime_frac
            # sequence number of this message within session, valid range 0-0xFFFFFFFF
        self.payload = payload # ntp.xmt_frac
            # message payload, 32 bit, zero padded, valid range 0-0xFFFFFFFF
        self.length = length # ntp.rootdispersion
            # length of ntpspy.payload in bytes, valid range 0-4

    @classmethod
    def from_ntp(cls, ntp: NTPdatagram):
        return cls(
            status=ntp.leap,
            function=NTPspyFunction(ntp.poll),
            version=ntp.precision,
            magic=ntp.rootdelay,
            session_id=ntp.refid,
            sequence_number=ntp.reftime_frac,
            payload=ntp.xmt_frac,
            length=ntp.rootdispersion
        )
    
    def to_ntp(self, ntp: NTPdatagram=None) -> NTPdatagram:
        if ntp is None:
            ntp = NTPdatagram()
        ntp.leap = self.status
        ntp.poll = self.function.value
        ntp.precision = self.version
        ntp.rootdelay = self.magic
        ntp.refid = self.session_id
        ntp.reftime_frac = self.sequence_number
        if isinstance(self.payload, bytes):
            if len(self.payload) > 4:
                raise ValueError("Payload length exceeds 4 bytes.")
            ntp.xmt_frac = int.from_bytes(self.payload.ljust(4, b'\x00'), byteorder='big')
        else:
            ntp.xmt_frac = int(self.payload)
        ntp.rootdispersion = self.length
        return ntp